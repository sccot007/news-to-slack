"""Slack Incoming Webhook으로 신규 글 목록을 발송."""
import requests

from config import SLACK_WEBHOOK_URL, REQUEST_TIMEOUT

MAX_MESSAGE_LENGTH = 3800  # Slack 권장 한도(4000자) 대비 여유


def _format_message(new_items_by_site: dict) -> str:
    lines = ["*오늘의 새 글*"]
    for site_name, items in new_items_by_site.items():
        if not items:
            continue
        lines.append(f"\n*{site_name}*")
        for item in items:
            display_title = item.get("display_title") or item["title"]
            page_url = item.get("page_url")
            title_link = page_url or item["link"]
            lines.append(f"• <{title_link}|{display_title}>")
            summary = item.get("summary")
            if summary:
                lines.append(f"   {summary}")
            if page_url:
                lines.append(f"   (<{item['link']}|원문 보기>)")
    return "\n".join(lines)


def _chunk_message(text: str) -> list[str]:
    lines = text.split("\n")
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > MAX_MESSAGE_LENGTH:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def send_digest(new_items_by_site: dict, dry_run: bool = False) -> None:
    """new_items_by_site: {site_name: [{"title", "link", ...}, ...]}"""
    has_items = any(items for items in new_items_by_site.values())
    if not has_items:
        return

    message = _format_message(new_items_by_site)

    if dry_run:
        print("[dry-run] Slack로 발송될 내용:\n")
        print(message)
        return

    if not SLACK_WEBHOOK_URL:
        raise RuntimeError("SLACK_WEBHOOK_URL이 설정되지 않았습니다 (.env 확인).")

    for chunk in _chunk_message(message):
        response = requests.post(
            SLACK_WEBHOOK_URL, json={"text": chunk}, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
