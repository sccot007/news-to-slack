"""기사 제목/발췌를 받아 한국어 요약(100자 이내)과 표시용 제목을 생성.

Gemini를 우선 호출하고, 실패하면 Anthropic으로 폴백한다.
영문 기사는 "번역 제목 (원제)" 형식으로, 한국어 기사는 원제를 그대로 표시한다.

`translate_full_article`은 full_translate 사이트(예: CNCF Blog)를 위한 전문(全文) 번역용으로,
같은 Gemini→Anthropic 폴백 구조를 사용하되 훨씬 큰 max_tokens로 호출한다.
"""
import json
import re

import requests
from bs4 import BeautifulSoup

from config import GEMINI_API_KEY, ANTHROPIC_API_KEY, REQUEST_TIMEOUT

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

SUMMARY_MAX_TOKENS = 300
FULL_TRANSLATE_MAX_TOKENS = 8192

# 짧은 요약은 REQUEST_TIMEOUT(15초)로 충분하지만, 전문 번역은 응답 토큰이 훨씬 많아
# 생성 시간이 길어지므로 별도로 넉넉한 타임아웃을 둔다.
FULL_TRANSLATE_TIMEOUT = 120

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


def _extract_paragraphs(content_html: str) -> str:
    """본문 HTML에서 블록 단위 텍스트를 문단 구분(빈 줄)을 유지해 추출한다."""
    if not content_html:
        return ""
    soup = BeautifulSoup(content_html, "html.parser")
    blocks = soup.find_all(["p", "h1", "h2", "h3", "h4", "li", "blockquote", "pre"])
    if not blocks:
        return soup.get_text(separator="\n\n", strip=True)
    paragraphs = [block.get_text(separator=" ", strip=True) for block in blocks]
    return "\n\n".join(p for p in paragraphs if p)


def _build_translate_prompt(title: str, content_html: str, lang: str) -> str:
    body_text = _extract_paragraphs(content_html)
    return (
        "다음은 기술 블로그 글의 원문이다. 한국어로 자연스럽게 전문 번역해줘. "
        "아래 JSON 형식으로만 응답하고, 다른 설명이나 코드블록 없이 순수 JSON만 출력해. "
        "JSON 문자열 안의 줄바꿈은 반드시 \\n으로 이스케이프해.\n\n"
        f"원문 제목: {title}\n"
        f"원문 언어: {lang}\n"
        f"원문 본문:\n{body_text}\n\n"
        "요구사항:\n"
        "- translated_title: 원문 제목을 자연스러운 한국어로 번역\n"
        "- translated_body: 본문 전체를 문단 구분(빈 줄 \\n\\n)을 유지하며 한국어로 번역. "
        "기술 용어/고유명사는 필요하면 괄호로 원어를 병기\n"
        "- summary: 핵심 내용을 한국어로 100자 이내 요약\n\n"
        '출력 형식 예시: {"translated_title": "...", "translated_body": "...", "summary": "..."}'
    )


def _parse_json_response(text: str, required_fields: tuple[str, ...]) -> dict:
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        raise ValueError(f"응답에서 JSON을 찾을 수 없음: {text[:200]!r}")
    data = json.loads(match.group(0))
    missing = [field for field in required_fields if field not in data]
    if missing:
        raise ValueError(f"필수 필드 누락({missing}): {str(data)[:200]!r}")
    return data


def _call_gemini(
    prompt: str, required_fields: tuple[str, ...], max_output_tokens: int, timeout: int
) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않음")
    response = requests.post(
        GEMINI_URL,
        params={"key": GEMINI_API_KEY},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_output_tokens},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_json_response(text, required_fields)


def _call_anthropic(
    prompt: str, required_fields: tuple[str, ...], max_tokens: int, timeout: int
) -> dict:
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
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    text = data["content"][0]["text"]
    return _parse_json_response(text, required_fields)


def _call_with_fallback(
    prompt: str, required_fields: tuple[str, ...], max_tokens: int, timeout: int = REQUEST_TIMEOUT
) -> dict:
    try:
        return _call_gemini(prompt, required_fields, max_tokens, timeout)
    except Exception as gemini_exc:  # noqa: BLE001 - LLM 실패는 폴백으로 흡수
        try:
            return _call_anthropic(prompt, required_fields, max_tokens, timeout)
        except Exception as anthropic_exc:  # noqa: BLE001
            raise RuntimeError(f"gemini={gemini_exc}; anthropic={anthropic_exc}") from anthropic_exc


def summarize_item(title: str, description: str, lang: str) -> dict:
    """{"display_title": str, "summary": str} 반환. 둘 다 실패하면 원문 기반 기본값 반환."""
    prompt = _build_prompt(title, description, lang)
    try:
        return _call_with_fallback(prompt, ("display_title", "summary"), SUMMARY_MAX_TOKENS)
    except RuntimeError as exc:
        return {
            "display_title": title,
            "summary": (description or title)[:100],
            "_error": str(exc),
        }


def translate_full_article(title: str, content_html: str, lang: str) -> dict:
    """{"translated_title", "translated_body", "summary"} 반환.

    본문이 길어 SUMMARY_MAX_TOKENS/REQUEST_TIMEOUT으로는 부족하므로 각각
    FULL_TRANSLATE_MAX_TOKENS/FULL_TRANSLATE_TIMEOUT을 사용한다.
    둘 다 실패하면 원문 그대로를 담은 기본값을 반환한다 (호출부가 "_error" 유무로 실패를 감지).
    """
    prompt = _build_translate_prompt(title, content_html, lang)
    required = ("translated_title", "translated_body", "summary")
    try:
        return _call_with_fallback(prompt, required, FULL_TRANSLATE_MAX_TOKENS, FULL_TRANSLATE_TIMEOUT)
    except RuntimeError as exc:
        body_text = _extract_paragraphs(content_html) or title
        return {
            "translated_title": title,
            "translated_body": body_text,
            "summary": body_text[:100],
            "_error": str(exc),
        }
