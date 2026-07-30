"""진입점: 수집 -> 중복 필터 -> 카테고리 쿼터 선별 -> 요약/번역 -> Slack 발송 -> 이력 저장.

selector는 반드시 summarizer보다 앞에 위치한다. 발송하지 않을 글까지 요약하면
Gemini/Anthropic API 호출 비용이 크게 늘어나기 때문이다 (CLAUDE.md 참고).
"""
import argparse
import json
import sys
from datetime import datetime

from config import SITES_FILE, ITEMS_PER_SITE
from fetcher import fetch_rss, fetch_html
from dedup import load_history, save_history, prune_old_entries, is_duplicate, make_entry
from selector import select_candidates
from summarizer import summarize_item, translate_full_article
import pages
from notifier import send_digest


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr)


def load_config() -> dict:
    with open(SITES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    quotas = data.get("quotas", {})
    total_limit = data.get("total_limit", sum(quotas.values()))
    sites = [site for site in data.get("sites", []) if site.get("enabled", True)]

    _validate_config(quotas, total_limit, sites)
    return {"quotas": quotas, "total_limit": total_limit, "sites": sites}


def _validate_config(quotas: dict, total_limit: int, sites: list[dict]) -> None:
    quota_sum = sum(quotas.values())
    if quota_sum > total_limit:
        raise ValueError(f"quotas 합계({quota_sum})가 total_limit({total_limit})을 초과합니다")

    for site in sites:
        category = site.get("category")
        if category not in quotas:
            raise ValueError(
                f"[{site.get('id')}] category '{category}'가 quotas에 정의되어 있지 않습니다"
            )


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
    parser = argparse.ArgumentParser(description="지정 사이트 최신 글을 카테고리 쿼터에 따라 선별, 요약해 Slack으로 발송")
    parser.add_argument(
        "--dry-run", action="store_true", help="Slack 발송/이력 저장 없이 콘솔에만 출력"
    )
    parser.add_argument(
        "--force", action="store_true", help="중복 여부와 무관하게 이번 실행에서 발견한 글을 모두 대상으로 함"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="선별 후 최종 건수를 N건으로 추가 제한 (테스트용)"
    )
    args = parser.parse_args()

    config = load_config()
    history = load_history()

    candidates = collect_candidates(config["sites"], history, args.force)
    selected = select_candidates(candidates, config["quotas"], config["total_limit"], log=log)

    if args.limit is not None:
        selected = selected[: args.limit]

    new_items_by_site = {}
    newly_sent_entries = []
    written_page_paths = []

    for candidate in selected:
        site = candidate["site"]
        item = candidate["item"]

        if site.get("full_translate"):
            translated = translate_full_article(
                item["title"], item.get("content_html", ""), site.get("lang", "ko")
            )
            if "_error" in translated:
                log(f"[{site['id']}] 전문 번역 실패, 발췌로 대체: {translated['_error']}")

            if args.dry_run:
                page_url = pages.page_url_for(item["link"], item["title"])
            else:
                path, page_url = pages.write_page(
                    item["title"],
                    item["link"],
                    translated["translated_title"],
                    translated["translated_body"],
                    site["name"],
                    item.get("published_at"),
                )
                written_page_paths.append(path)

            item_out = {
                **item,
                "display_title": translated["translated_title"],
                "summary": translated["summary"],
                "page_url": page_url,
            }
        else:
            enriched = summarize_item(item["title"], item.get("description", ""), site.get("lang", "ko"))
            if "_error" in enriched:
                log(f"[{site['id']}] 요약 실패, 원문으로 대체: {enriched['_error']}")
            item_out = {**item, **enriched}

        new_items_by_site.setdefault(site["name"], []).append(item_out)
        newly_sent_entries.append(make_entry(site["id"], item["title"], item["link"]))

    if written_page_paths:
        try:
            pages.publish_pages(written_page_paths, len(written_page_paths))
            log(f"번역 페이지 {len(written_page_paths)}건 git 배포 완료")
        except RuntimeError as exc:
            log(f"번역 페이지 git 배포 실패 (Slack은 정상 발송 진행): {exc}")

    send_digest(new_items_by_site, dry_run=args.dry_run)

    if not args.dry_run and newly_sent_entries:
        updated_history = prune_old_entries(history + newly_sent_entries)
        save_history(updated_history)
        log(f"이력 저장 완료 (총 {len(updated_history)}건)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
