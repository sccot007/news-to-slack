"""RSS/Atom 피드 수집."""
import calendar
import subprocess
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# 요약 생성용 프롬프트에 넣을 발췌 최대 길이
DESCRIPTION_MAX_LENGTH = 500


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(separator=" ", strip=True)


def _to_iso(struct_time) -> str | None:
    """feedparser의 *_parsed(UTC 기준 struct_time)를 ISO 문자열로 변환. selector의 최신순 정렬에 사용."""
    if not struct_time:
        return None
    return datetime.fromtimestamp(calendar.timegm(struct_time), tz=timezone.utc).isoformat()


def _fetch_via_curl(feed_url: str) -> bytes:
    """requests가 403으로 막힐 때(Cloudflare 등 TLS 핑거프린팅 차단)의 폴백.

    curl은 requests(urllib3)와 TLS 핸드셰이크 방식이 달라 일부 사이트에서
    requests만 차단되는 경우가 있다 (예: techblog.woowahan.com). 시스템에 curl이
    설치되어 있어야 한다 (Raspberry Pi OS/Debian 기본 포함, 없으면 `apt install curl`).
    """
    result = subprocess.run(
        ["curl", "-s", "-L", "--max-time", str(REQUEST_TIMEOUT), "-A", USER_AGENT, feed_url],
        capture_output=True,
        timeout=REQUEST_TIMEOUT + 5,
        check=True,
    )
    return result.stdout


def fetch_rss(feed_url: str, limit: int) -> list[dict]:
    """피드에서 최신 항목을 최대 limit개 가져온다.

    각 항목은 {"title", "link", "published", "published_at", "description"} 형태.
    - published: 원문 그대로의 발행일 문자열 (표시/디버깅용)
    - published_at: UTC ISO 8601로 정규화된 발행일. 없으면 None (selector가 가장 오래된 것으로 취급)
    - description: 요약 생성 시 참고할 발췌 (HTML 태그 제거, 길이 제한)
    """
    try:
        response = requests.get(
            feed_url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        content = response.content
    except requests.exceptions.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 403:
            raise
        content = _fetch_via_curl(feed_url)

    parsed = feedparser.parse(content)

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
                "published_at": _to_iso(entry.get("published_parsed")),
                "description": description,
            }
        )
    return items
