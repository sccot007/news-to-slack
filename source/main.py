"""진입점: 사이트 순회 -> 수집 -> 중복 필터 -> 요약/번역 -> Slack 발송 -> 이력 저장."""
import argparse
import json
import sys
from datetime import datetime

from config import SITES_FILE, ITEMS_PER_SITE
from fetcher import fetch_rss, fetch_html
from dedup import load_history, save_history, prune_old_entries, is_duplicate, make_entry
from summarizer import summarize_item
from notifier import send_digest


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr)


def load_sites() -> list[dict]:
    with open(SITES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [site for site in data.get("sites", []) if site.get("enabled", True)]


def fetch_site_items(site: dict) -> list[dict]:
    if site["type"] == "rss":
        return fetch_rss(site["feed_url"], ITEMS_PER_SITE)
    if site["type"] == "html":
        return fetch_html(site["url"], site["selectors"], ITEMS_PER_SITE)
    raise ValueError(f"알 수 없는 site type: {site['type']}")


def collect_candidates(sites: list[dict], history: list[dict], force: bool) -> list[dict]:
    """사이트를 순회해 중복이 아닌 항목만 {"site": site, "item": item} 형태로 모은다."""
    candidates = []
    for site in sites:
        try:
            items = fetch_site_items(site)
        except Exception as exc:  # noqa: BLE001 - 사이트 하나 실패해도 나머지는 계속 진행
            log(f"[{site['id']}] 수집 실패: {exc}")
            continue

        kept = [
            item
            for item in items
            if force or not is_duplicate(history, site["id"], item["title"], item["link"])
        ]
        log(f"[{site['id']}] 수집 {len(items)}건 중 신규 {len(kept)}건")
        candidates.extend({"site": site, "item": item} for item in kept)

    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="지정 사이트 최신 글을 요약해 Slack으로 발송")
    parser.add_argument(
        "--dry-run", action="store_true", help="Slack 발송/이력 저장 없이 콘솔에만 출력"
    )
    parser.add_argument(
        "--force", action="store_true", help="중복 여부와 무관하게 이번 실행에서 발견한 글을 모두 대상으로 함"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="전체 대상 글 개수를 N건으로 제한 (테스트용)"
    )
    args = parser.parse_args()

    sites = load_sites()
    history = load_history()

    candidates = collect_candidates(sites, history, args.force)
    if args.limit is not None:
        candidates = candidates[: args.limit]

    new_items_by_site = {}
    newly_sent_entries = []

    for candidate in candidates:
        site = candidate["site"]
        item = candidate["item"]

        enriched = summarize_item(item["title"], item.get("description", ""), site.get("lang", "ko"))
        if "_error" in enriched:
            log(f"[{site['id']}] 요약 실패, 원문으로 대체: {enriched['_error']}")
        item_out = {**item, **enriched}

        new_items_by_site.setdefault(site["name"], []).append(item_out)
        newly_sent_entries.append(make_entry(site["id"], item["title"], item["link"]))

    send_digest(new_items_by_site, dry_run=args.dry_run)

    if not args.dry_run and newly_sent_entries:
        updated_history = prune_old_entries(history + newly_sent_entries)
        save_history(updated_history)
        log(f"이력 저장 완료 (총 {len(updated_history)}건)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
