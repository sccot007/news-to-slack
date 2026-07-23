"""RSS/Atom 피드 수집."""
import feedparser
import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT

USER_AGENT = "ITnews-bot/1.0 (+https://github.com/)"

# 요약 생성용 프롬프트에 넣을 발췌 최대 길이
DESCRIPTION_MAX_LENGTH = 500


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(separator=" ", strip=True)


def fetch_rss(feed_url: str, limit: int) -> list[dict]:
    """피드에서 최신 항목을 최대 limit개 가져온다.

    각 항목은 {"title": str, "link": str, "published": str | None, "description": str} 형태.
    description은 요약 생성 시 참고할 발췌(HTML 태그 제거, 길이 제한)이다.
    """
    response = requests.get(
        feed_url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()

    parsed = feedparser.parse(response.content)

    items = []
    for entry in parsed.entries[:limit]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue
        description = _strip_html(entry.get("summary", ""))[:DESCRIPTION_MAX_LENGTH]
        items.append(
            {
                "title": title,
                "link": link,
                "published": entry.get("published", None),
                "description": description,
            }
        )
    return items
