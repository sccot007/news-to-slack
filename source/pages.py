"""번역 전문 페이지 생성 및 GitHub Pages(repo의 docs/)로 배포.

full_translate 사이트(예: CNCF Blog)의 글은 Slack에서 제목을 클릭하면 이 모듈이 만든
정적 페이지(번역 전문)로 이동하고, 원문은 페이지 안의 별도 링크로 연결한다.
GitHub 저장소 Settings > Pages에서 Source를 "main 브랜치 / docs 폴더"로 미리 설정해둬야 한다.
"""
import hashlib
import html
import os
import re
import subprocess
import time
from datetime import datetime, timezone

from config import ARTICLES_DIR, ARTICLES_RETENTION_DAYS, PAGES_BASE_URL, REPO_ROOT

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    return slug[:60] or "article"


def _slug_for(original_link: str, original_title: str) -> str:
    """원문 링크 해시 + 원문 제목 기반 슬러그. 같은 글은 항상 같은 슬러그가 나오도록 결정적으로 만든다."""
    link_hash = hashlib.sha1(original_link.encode("utf-8")).hexdigest()[:8]
    return f"{_slugify(original_title)}-{link_hash}"


def page_url_for(original_link: str, original_title: str) -> str:
    return f"{PAGES_BASE_URL}/articles/{_slug_for(original_link, original_title)}.html"


def _page_path_for(original_link: str, original_title: str) -> str:
    return os.path.join(ARTICLES_DIR, f"{_slug_for(original_link, original_title)}.html")


_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Pretendard, sans-serif;
    max-width: 720px;
    margin: 0 auto;
    padding: 2rem 1.25rem 4rem;
    line-height: 1.7;
    color: #1a1a1a;
    background: #fff;
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ color: #e6e6e6; background: #121212; }}
    a {{ color: #7db8ff; }}
    .meta {{ color: #999; }}
    .original-link {{ border-color: #333; }}
  }}
  h1 {{ font-size: 1.6rem; line-height: 1.4; margin-bottom: 0.5rem; }}
  .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }}
  p {{ margin: 1.1em 0; }}
  .original-link {{
    display: inline-block;
    margin-top: 2.5rem;
    padding-top: 1.25rem;
    border-top: 1px solid #ddd;
  }}
  a {{ color: #0b66c3; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="meta">{site_name} · {published}<br>이 페이지는 Gemini/Anthropic으로 자동 번역되었습니다.</div>
{body_html}
<div class="original-link"><a href="{original_link}" target="_blank" rel="noopener">원문 보기 →</a></div>
</body>
</html>
"""


def render_page(
    translated_title: str,
    translated_body: str,
    original_link: str,
    site_name: str,
    published_at: str | None,
) -> str:
    paragraphs = [p.strip() for p in translated_body.split("\n\n") if p.strip()]
    body_html = "\n".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
    published = (
        published_at[:10] if published_at else datetime.now(timezone.utc).date().isoformat()
    )
    return _TEMPLATE.format(
        title=html.escape(translated_title),
        site_name=html.escape(site_name),
        published=published,
        body_html=body_html,
        original_link=html.escape(original_link, quote=True),
    )


def write_page(
    original_title: str,
    original_link: str,
    translated_title: str,
    translated_body: str,
    site_name: str,
    published_at: str | None,
) -> tuple[str, str]:
    """페이지 파일을 쓰고 (파일 경로, 공개 URL)을 반환한다. git 커밋/푸시는 하지 않는다."""
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    path = _page_path_for(original_link, original_title)
    content = render_page(translated_title, translated_body, original_link, site_name, published_at)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path, page_url_for(original_link, original_title)


def list_stale_pages(retention_days: int = ARTICLES_RETENTION_DAYS) -> list[str]:
    """retention_days보다 오래된(파일 수정시각 기준) 페이지 경로 목록을 반환한다. 삭제는 하지 않는다."""
    if not os.path.isdir(ARTICLES_DIR):
        return []
    cutoff = time.time() - retention_days * 86400
    return [
        os.path.join(ARTICLES_DIR, name)
        for name in os.listdir(ARTICLES_DIR)
        if name.endswith(".html") and os.path.getmtime(os.path.join(ARTICLES_DIR, name)) < cutoff
    ]


def prune_old_pages(retention_days: int = ARTICLES_RETENTION_DAYS) -> list[str]:
    """retention_days보다 오래된 페이지를 로컬에서 삭제하고 삭제된 경로 목록을 반환한다.

    git add/commit/push는 하지 않는다 (publish_pages가 처리). 파일 수정시각(mtime)을 기준으로 판단하므로,
    저장소를 새로 clone하는 경우처럼 mtime이 초기화되는 상황에서는 실제보다 "최신"으로 오판되어
    삭제가 미뤄질 수 있다 (삭제 누락 방향이라 데이터 유실 위험은 없다).
    """
    stale = list_stale_pages(retention_days)
    for path in stale:
        os.remove(path)
    return stale


def publish_pages(written_paths: list[str], deleted_paths: list[str]) -> None:
    """새로 쓴 페이지 + 삭제된 페이지를 한 번에 git add -A/commit/push한다.

    실패 시 RuntimeError를 던진다 (호출부가 잡아서 로그만 남기고 파이프라인은 계속 진행할지 결정).
    내용이 이전과 동일해 커밋할 것이 없으면 조용히 넘어간다.
    """
    if not written_paths and not deleted_paths:
        return

    subprocess.run(
        ["git", "add", "-A", "--", ARTICLES_DIR], cwd=REPO_ROOT, check=True, capture_output=True
    )

    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if not staged.stdout.strip():
        return

    parts = []
    if written_paths:
        parts.append(f"{len(written_paths)}건 추가")
    if deleted_paths:
        parts.append(f"{len(deleted_paths)}건 정리(기간 경과)")
    message = "번역 페이지 " + ", ".join(parts)

    try:
        subprocess.run(
            ["git", "commit", "-m", message], cwd=REPO_ROOT, check=True, capture_output=True
        )
        subprocess.run(["git", "push"], cwd=REPO_ROOT, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr)
        raise RuntimeError(f"번역 페이지 git 배포 실패: {stderr[:500]}") from exc
