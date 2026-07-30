"""애플리케이션 설정 로드.

.env 파일과 sites.json 경로를 스크립트 위치 기준 절대 경로로 고정한다.
cron 등 외부 스케줄러가 다른 작업 디렉터리에서 실행해도 항상 동작해야 하기 때문이다.
"""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPO_ROOT = os.path.dirname(BASE_DIR)
DOCS_DIR = os.path.join(REPO_ROOT, "docs")
ARTICLES_DIR = os.path.join(DOCS_DIR, "articles")

SITES_FILE = os.path.join(DATA_DIR, "sites.json")
SENT_HISTORY_FILE = os.path.join(DATA_DIR, "sent_history.json")

load_dotenv(os.path.join(BASE_DIR, ".env"))

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

# 요약/번역용 LLM: Gemini를 우선 사용하고, 실패 시 Anthropic으로 폴백한다.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# 사이트별로 확인할 최신 글 개수
ITEMS_PER_SITE = int(os.environ.get("ITEMS_PER_SITE", "10"))

# 중복 판단: 키워드 자카드 유사도가 이 값 이상이면 같은 글로 간주
DEDUP_KEYWORD_THRESHOLD = float(os.environ.get("DEDUP_KEYWORD_THRESHOLD", "0.6"))

# 발송 이력 보관 기간 (일). 이보다 오래된 이력은 정리한다.
HISTORY_RETENTION_DAYS = int(os.environ.get("HISTORY_RETENTION_DAYS", "90"))

# HTTP 요청 타임아웃(초)
REQUEST_TIMEOUT = 15

# 전문 번역(full_translate) 페이지가 배포되는 GitHub Pages 기본 URL
PAGES_BASE_URL = os.environ.get(
    "PAGES_BASE_URL", "https://sccot007.github.io/news-to-slack"
)
