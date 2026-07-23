"""중복 판단 및 발송 이력(sent_history.json) 관리.

같은 site_id 내에서 다음 중 하나라도 해당하면 중복으로 간주한다:
  1. 링크가 완전히 같음
  2. 정규화된 제목이 완전히 같음
  3. 제목 키워드 집합의 자카드 유사도가 임계값 이상
"""
import json
import re
from datetime import datetime, timedelta, timezone

from config import SENT_HISTORY_FILE, DEDUP_KEYWORD_THRESHOLD, HISTORY_RETENTION_DAYS

_NON_WORD_RE = re.compile(r"[^\w]", re.UNICODE)


def normalize_title(title: str) -> str:
    return _NON_WORD_RE.sub("", title).lower()


def extract_keywords(title: str) -> list[str]:
    tokens = re.split(r"\s+", title.strip())
    keywords = set()
    for token in tokens:
        cleaned = _NON_WORD_RE.sub("", token).lower()
        if len(cleaned) >= 2:
            keywords.add(cleaned)
    return sorted(keywords)


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def load_history() -> list[dict]:
    try:
        with open(SENT_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return data.get("entries", [])


def save_history(entries: list[dict]) -> None:
    with open(SENT_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump({"entries": entries}, f, ensure_ascii=False, indent=2)


def prune_old_entries(entries: list[dict], retention_days: int = HISTORY_RETENTION_DAYS) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    kept = []
    for entry in entries:
        try:
            sent_at = datetime.fromisoformat(entry["sent_at"])
        except (KeyError, ValueError):
            kept.append(entry)
            continue
        if sent_at >= cutoff:
            kept.append(entry)
    return kept


def is_duplicate(entries: list[dict], site_id: str, title: str, link: str) -> bool:
    normalized = normalize_title(title)
    keywords = set(extract_keywords(title))

    for entry in entries:
        if entry.get("site_id") != site_id:
            continue
        if entry.get("link") == link:
            return True
        if entry.get("normalized_title") == normalized:
            return True
        existing_keywords = set(entry.get("keywords", []))
        if _jaccard(keywords, existing_keywords) >= DEDUP_KEYWORD_THRESHOLD:
            return True
    return False


def make_entry(site_id: str, title: str, link: str) -> dict:
    return {
        "site_id": site_id,
        "title": title,
        "normalized_title": normalize_title(title),
        "keywords": extract_keywords(title),
        "link": link,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
