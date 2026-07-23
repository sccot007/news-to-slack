"""기사 제목/발췌를 받아 한국어 요약(100자 이내)과 표시용 제목을 생성.

Gemini를 우선 호출하고, 실패하면 Anthropic으로 폴백한다.
영문 기사는 "번역 제목 (원제)" 형식으로, 한국어 기사는 원제를 그대로 표시한다.
"""
import json
import re

import requests

from config import GEMINI_API_KEY, ANTHROPIC_API_KEY, REQUEST_TIMEOUT

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _build_prompt(title: str, description: str, lang: str) -> str:
    return (
        "다음 뉴스 기사 정보를 보고 아래 JSON 형식으로만 응답해. "
        "다른 설명이나 코드블록 없이 순수 JSON 한 줄만 출력해.\n\n"
        f"원문 제목: {title}\n"
        f"기사 언어: {lang}\n"
        f"기사 요약/발췌: {description or '(없음)'}\n\n"
        "요구사항:\n"
        "- summary: 기사 핵심 내용을 한국어로 100자 이내로 요약\n"
        "- display_title: 기사 언어가 한국어(ko)면 원제 그대로, 그 외 언어면 "
        '"한국어 번역 제목 (원제)" 형식으로 작성\n\n'
        '출력 형식 예시: {"display_title": "...", "summary": "..."}'
    )


def _parse_json_response(text: str) -> dict:
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        raise ValueError(f"응답에서 JSON을 찾을 수 없음: {text[:200]!r}")
    data = json.loads(match.group(0))
    if "display_title" not in data or "summary" not in data:
        raise ValueError(f"필수 필드 누락: {data!r}")
    return data


def _call_gemini(prompt: str) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않음")
    response = requests.post(
        GEMINI_URL,
        params={"key": GEMINI_API_KEY},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_json_response(text)


def _call_anthropic(prompt: str) -> dict:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되지 않음")
    response = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    text = data["content"][0]["text"]
    return _parse_json_response(text)


def summarize_item(title: str, description: str, lang: str) -> dict:
    """{"display_title": str, "summary": str} 반환. 둘 다 실패하면 원문 기반 기본값 반환."""
    prompt = _build_prompt(title, description, lang)
    try:
        return _call_gemini(prompt)
    except Exception as gemini_exc:  # noqa: BLE001 - LLM 실패는 폴백으로 흡수
        try:
            return _call_anthropic(prompt)
        except Exception as anthropic_exc:  # noqa: BLE001
            return {
                "display_title": title,
                "summary": (description or title)[:100],
                "_error": f"gemini={gemini_exc}; anthropic={anthropic_exc}",
            }
