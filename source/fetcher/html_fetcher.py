"""RSS가 없는 사이트를 위한 HTML 스크래핑 수집.

sites.json의 site["selectors"] 설정을 사용한다:
{
  "item": "ul.article-list li",   # 각 글 항목을 감싸는 요소
  "title": "a.title",             # item 내부에서 제목 텍스트가 있는 요소 (item 자신이면 생략 가능)
  "link": "a.title",               # item 내부에서 링크가 있는 요소 (item 자신이면 생략 가능)
  "link_attr": "href"              # 링크 속성명 (기본 href)
}
"""
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_html(url: str, selectors: dict, limit: int) -> list[dict]:
    response = requests.get(
        url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    item_sel = selectors["item"]
    title_sel = selectors.get("title")
    link_sel = selectors.get("link")
    link_attr = selectors.get("link_attr", "href")

    items = []
    for node in soup.select(item_sel)[:limit]:
        title_node = node.select_one(title_sel) if title_sel else node
        link_node = node.select_one(link_sel) if link_sel else node

        if title_node is None or link_node is None:
            continue

        title = title_node.get_text(strip=True)
        raw_link = link_node.get(link_attr)
        if not title or not raw_link:
            continue

        items.append(
            {
                "title": title,
                "link": urljoin(url, raw_link),
                "published": None,
                "published_at": None,
                "description": "",
            }
        )
    return items
