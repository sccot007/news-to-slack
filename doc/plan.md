# 작업 계획: 지정 사이트 최신 뉴스 → 요약/번역 → Slack 발송

## 1. 목표

사용자가 지정한 사이트(URL) 목록에서 최신 뉴스/글/블로그 글을 주기적으로 수집하여
한국어로 요약·번역한 뒤 Slack으로 발송한다. 이미 발송한 항목은 제목/핵심 키워드
기준으로 중복 판단하여 다시 보내지 않는다. 카테고리별 쿼터를 적용해 특정 소스에
편중되지 않도록 균형 잡힌 큐레이션을 유지한다.

## 2. 확정된 결정 사항

| 항목 | 결정 |
|---|---|
| 발송 채널 | Slack (Incoming Webhook, 채널: 김희주) |
| 개발 언어 | Python |
| 수집 방식 | RSS/Atom 우선, 없으면 HTML 스크래핑으로 폴백 |
| 실행 방식 | Raspberry Pi 4에서 crontab으로 하루 1회 실행 후 종료 — 상시 실행 데몬 아님 |
| 사이트별 확인 개수 | 사이트당 최신 10개를 후보로 수집 (`ITEMS_PER_SITE`) |
| 하루 발송 한도 | 카테고리 쿼터 합계 57건 (`sites.json`의 `total_limit`) |
| 요약/번역 | Gemini 우선 호출, 실패 시 Anthropic 폴백 |
| 전문 번역 페이지 | `full_translate: true` 사이트(CNCF Blog)는 전문을 번역해 GitHub Pages에 배포, Slack 제목이 그 페이지로 연결 |
| 사이트 설정 저장 | `source/data/sites.json` |
| 중복 방지 저장소 | `source/data/sent_history.json` (가벼운 JSON, DB 아님) |

필요 시 위 표는 언제든 갱신한다.

## 3. 카테고리 쿼터 및 등록 사이트

하루 57개 슬롯을 카테고리별로 미리 배정한다. 카테고리 안에서는 최신순으로 채우고,
비는 슬롯은 다른 카테고리 잉여분(쿼터 초과분)에서 최신순으로 재분배한다.

| 카테고리 | 슬롯 | 등록 사이트 | 상태 |
| --- | --- | --- | --- |
| `domestic` | 20 | 우아한형제들 기술블로그, 카카오 기술블로그, 네이버 D2, AI타임스 | 우아한형제들은 Cloudflare가 `requests`를 차단해 curl 폴백 사용 (§7) |
| `cn-official` | 10 | Kubernetes Blog | CNCF Blog는 `cncf-blog` 카테고리로 이동 (아래) |
| `ai-primary` | 8 | OpenAI News, Google DeepMind Blog | Anthropic News는 RSS 없음 + JS 렌더링이라 제외 (§7 참고) |
| `cn-deep` | 7 | The New Stack, InfoQ Cloud | |
| `cncf-blog` | 7 | CNCF Blog | `full_translate: true` — 요약이 아니라 전문 번역 페이지로 발송 (§4.3, §7) |
| `ai-curation` | 5 | Simon Willison's Weblog | The Batch(deeplearning.ai)는 RSS 피드를 찾지 못해 제외 |

AI타임스(`aitimes`)는 `domestic` 카테고리로 재등록했다. 발행 빈도가 다른 국내 사이트보다
훨씬 높아서, "카테고리 안 최신순" 규칙상 `domestic` 슬롯 대부분을 AI타임스가 차지할 수 있다.
사이트별 배분이 필요해지면 selector에 카테고리 내 사이트별 서브쿼터를 추가하는 방향을 검토한다.

## 4. 데이터 스키마

### 4.1 `sites.json` (수집 대상 + 쿼터)

```json
{
  "quotas": {
    "domestic": 20,
    "cn-official": 10,
    "ai-primary": 8,
    "cn-deep": 7,
    "ai-curation": 5,
    "cncf-blog": 7
  },
  "total_limit": 57,
  "sites": [
    {
      "id": "openai-news",
      "name": "OpenAI News",
      "url": "https://openai.com/news/",
      "type": "rss",
      "feed_url": "https://openai.com/news/rss.xml",
      "lang": "en",
      "category": "ai-primary",
      "enabled": true
    },
    {
      "id": "cncf-blog",
      "name": "CNCF Blog",
      "url": "https://www.cncf.io/blog/",
      "type": "rss",
      "feed_url": "https://www.cncf.io/blog/feed/",
      "lang": "en",
      "category": "cncf-blog",
      "full_translate": true,
      "enabled": true
    }
  ]
}
```

**필드 규칙**

- `quotas`: 카테고리별 슬롯 배정. 각 값의 합계가 `total_limit`을 초과하면 안 된다
  (`main.py`의 `_validate_config`가 시작 시 검증하고, 위반하면 예외를 던진다).
- `total_limit`: 하루 최대 발송 건수. 현재 57 (쿼터 합계와 동일).
- `category`: 사이트가 속한 카테고리. `quotas` 키와 반드시 일치해야 하며, 아니면
  `_validate_config`가 예외를 던진다.
- `lang`: `summarizer`가 번역 여부를 판단하는 데 사용 (`ko`가 아니면 "번역 제목 (원제)" 형식 적용).
- `full_translate`: `true`이면 요약 대신 본문 전체를 번역해 GitHub Pages 페이지로 만들고,
  Slack 제목이 그 페이지로 연결된다 (§4.3 참고). 기본값은 `false`(또는 필드 생략)로,
  기존처럼 요약 + 원문 링크 방식이다.
- `type: html`일 때만 `selectors`가 필요하다 (기존 `html_fetcher.py` 스키마와 동일).
- `enabled: false`인 사이트는 fetcher가 건너뛴다.

### 4.2 `sent_history.json` (발송 이력 / 중복 방지)

기존과 동일. 로컬 "DB" 역할이며, 테이블의 컬럼에 해당하는 필드로 제목/키워드를 대조한다.

```json
{
  "entries": [
    {
      "site_id": "cncf-blog",
      "title": "원본 제목",
      "normalized_title": "정규화된 제목(공백/특수문자 제거, 소문자)",
      "keywords": ["keyword1", "keyword2"],
      "link": "https://example.com/post/123",
      "sent_at": "2026-07-23T10:00:00+00:00"
    }
  ]
}
```

- 중복 판단: 같은 `site_id` 내에서 링크 완전 일치 OR `normalized_title` 완전 일치 OR
  `keywords` 자카드 유사도가 임계값(기본 0.6) 이상이면 중복으로 간주한다.
- **선별(quota)에서 탈락한 글은 기록하지 않는다.** 실제로 Slack에 발송된 글만
  `sent_history.json`에 남아야, 오늘 쿼터에 밀려난 글이 내일 다시 후보로 고려될 수 있다.
- 항목이 과도하게 늘어나지 않도록 오래된 항목(기본 90일 이상)은 정리(prune)한다.
- `full_translate` 사이트도 dedup 키(`site_id`/`title`/`link`)는 원문 기준 그대로 사용한다.
  번역 페이지 URL은 별도 필드(`page_url`)로만 다루고 이력 판단에는 관여하지 않는다.

### 4.3 전문 번역 페이지 (`docs/articles/*.html`)

`full_translate: true` 사이트는 요약 대신 본문 전체를 한국어로 번역해 정적 HTML 페이지로
만들고, 저장소의 `docs/` 폴더(GitHub Pages)에 배포한다.

- 파일명(슬러그)은 `원문 링크의 sha1 해시(8자) + 원문 제목 슬러그`로 결정적으로 생성된다
  (`pages.py`의 `_slug_for`). 같은 글을 다시 처리해도 항상 같은 파일 경로가 나온다.
- 공개 URL은 `{PAGES_BASE_URL}/articles/{slug}.html` (기본값
  `https://sccot007.github.io/news-to-slack/articles/...`).
- Slack 메시지는 제목을 이 URL로 링크하고, 그 아래에 원문 링크를 `(원문 보기)` 형태로
  별도 표기한다 (`notifier/slack_notifier.py`).
- 페이지 파일은 매 실행마다 로컬에 쓰고, 이번 실행에서 새로 쓴 파일들만 모아 한 번에
  `git add && git commit && git push` 한다 (`pages.publish_pages`). 이미 커밋된 내용과
  동일하면(재실행 등) 조용히 스킵한다.
- **주의**: GitHub Pages 빌드는 push 후 반영까지 수십 초~1분 정도 걸릴 수 있어, Slack
  메시지가 도착한 직후 링크를 클릭하면 잠깐 404가 뜰 수 있다.
- git push가 실패해도(네트워크 문제, 인증 문제 등) 예외를 로그로만 남기고 파이프라인은
  계속 진행해 Slack 발송까지는 정상적으로 완료한다 — 다만 그 경우 페이지 링크는 다음 push
  전까지 계속 404 상태다.

## 5. 모듈 설계 (`source/`)

```
source/
  main.py            # 진입점: 수집 → 중복 필터 → 쿼터 선별 → 요약/번역 → Slack 발송 → 이력 저장
  config.py          # 설정 로드 (.env, sites.json 경로, API 키 등)
  fetcher/
    __init__.py
    rss_fetcher.py   # feedparser 기반 RSS 수집. requests 403(Cloudflare 등) 시 curl로 폴백
    html_fetcher.py  # requests + BeautifulSoup 기반 스크래핑 (정적 HTML만 가능, JS 렌더링 사이트 불가)
  selector.py        # 카테고리 쿼터 기반 상위 N건 선별 + 잉여분 재분배
  summarizer.py      # Gemini 우선 → Anthropic 폴백으로 요약/번역 생성 (+ 전문 번역)
  pages.py           # full_translate 사이트의 번역 전문 페이지 렌더링 + docs/에 git 배포
  dedup.py           # 제목 정규화, 키워드 추출, 유사도 비교, sent_history 조회/기록
  notifier/
    slack_notifier.py # Slack Incoming Webhook으로 메시지 전송
  data/
    sites.json
    sent_history.json
  requirements.txt
  .env.example       # SLACK_WEBHOOK_URL, GEMINI_API_KEY, ANTHROPIC_API_KEY, PAGES_BASE_URL 등
docs/                # GitHub Pages로 배포되는 번역 전문 페이지 (pages.py가 자동 생성/커밋)
  index.html
  articles/
```

## 6. 처리 흐름 (main.py)

```
sites.json 로드 + 쿼터/카테고리 검증
      │
      ▼
[fetcher] 사이트별 최신 ITEMS_PER_SITE건 수집 (RSS 우선, 실패 시 폴백)
      │
      ▼
[dedup] sent_history.json과 대조해 이미 보낸 글 제외
      │
      ▼
[selector] 카테고리 쿼터만큼 최신순으로 선별, 부족분은 잉여 카테고리에서 재분배
      │
      ▼
[summarizer] 선별된 글만 처리 (Gemini→Anthropic)
      ├─ 일반 사이트: 한국어 요약(100자 이내) + 번역 제목
      └─ full_translate 사이트: 본문 전체 번역 → [pages] docs/에 페이지 생성 → git commit/push
      │
      ▼
[notifier] Slack Webhook으로 발송 (full_translate 글은 제목이 번역 페이지로 링크, 원문은 별도 표기)
      │
      ▼
발송된 글만 sent_history.json에 기록
```

**중요**: `selector`는 반드시 `summarizer`보다 앞에 위치해야 한다. 발송하지 않을 글까지
요약하면 Gemini/Anthropic API 호출 비용이 크게 늘어난다 (전체 수집 건수가 100건이어도
API는 최종 선별된 `total_limit`건만 호출됨).

## 7. 알려진 제약 사항

- **Anthropic News**: 공식 RSS가 없고 페이지가 Next.js로 클라이언트 사이드 렌더링되어
  `html_fetcher.py`(정적 requests+BeautifulSoup)로도 수집 불가. 헤드리스 브라우저
  (Playwright 등) 도입이 필요한데, Raspberry Pi에 Chromium을 얹는 무거운 변경이라 보류.
  일단 제외하고 `ai-primary`는 OpenAI+DeepMind 2곳으로 운영.
- **The Batch (deeplearning.ai)**: RSS 후보 URL을 여러 개 시도했으나 전부 404/500으로
  발견하지 못함. `ai-curation`은 Simon Willison만 등록.
- **우아한형제들 기술블로그**: Cloudflare가 `requests`(urllib3) TLS 핑거프린트를 차단해
  403을 반환한다 (curl은 통과). `rss_fetcher.py`가 403을 감지하면 시스템 `curl` 명령으로
  폴백한다. Raspberry Pi OS에는 curl이 기본 포함되어 있으나, 없다면 `apt install curl` 필요.
- **GitHub Pages는 수동 설정 필요**: `gh` CLI/토큰이 없어 API로 자동 활성화하지 못했다.
  저장소 Settings → Pages에서 Source를 `main` 브랜치 / `docs` 폴더로 한 번 설정해야
  `full_translate` 페이지 링크가 실제로 열린다.
- **`main.py` 실행 머신에 git push 권한 필요**: `full_translate` 페이지를 커밋하려면
  실행 환경(Pi 또는 개발 PC)에서 이 저장소로 비대화형 `git push`가 가능해야 한다.
  실패해도 파이프라인 자체는 계속 진행되어 Slack은 정상 발송되지만, 페이지 링크는
  다음 성공한 push 전까지 404 상태로 남는다.

## 8. Slack 연동

Incoming Webhook URL 발급 완료, `source/.env`(커밋 제외)에 `SLACK_WEBHOOK_URL`로 저장됨.
요약/번역 포함 실제 발송 테스트 완료. 쿼터를 20건→50건(11개 사이트)으로 확장한 뒤에도
`--dry-run --force`로 selector가 정확히 `domestic:20 cn-official:10 ai-primary:8 cn-deep:7 ai-curation:5`
(합계 50)로 선별하고 요약까지 정상 처리하는 것을 확인했다.

## 9. 마일스톤

- [x] M1. 프로젝트 스캐폴딩
- [x] M2. RSS fetcher 구현
- [x] M3. dedup 로직 구현 (정규화 + 키워드 유사도)
- [x] M4. Slack notifier 구현 + 실제 발송 테스트
- [x] M5. main.py로 전체 파이프라인 연결
- [x] M6. 요약/번역(summarizer) 추가 — Gemini 우선, Anthropic 폴백
- [x] M7. 카테고리 쿼터 시스템(selector) 도입, 11개 사이트로 확장
- [x] M8. CNCF Blog 전문 번역 + GitHub Pages 배포(`pages.py`) 도입, `cncf-blog` 카테고리 신설
- [ ] M9. GitHub Pages 저장소 설정 활성화 (Settings → Pages, 수동, §7)
- [ ] M10. Raspberry Pi 4에 배포 및 crontab 등록 (하루 1회, `0 8 * * *`, git push 권한 포함)
- [ ] M11. (선택) Anthropic News/The Batch 대안 마련, 로그 파일 로테이션, 수집 실패 시 Slack 알림

## 10. 참고 사항

- Raspberry Pi 배포 시 `source/` 전체를 복사한 뒤 `pip3 install -r requirements.txt`,
  `.env.example`을 `.env`로 복사해 `SLACK_WEBHOOK_URL`/`GEMINI_API_KEY`/`ANTHROPIC_API_KEY` 등
  값을 채운다 (`.env`는 git에 커밋하지 않음). curl도 설치되어 있어야 한다.
- 개발 중 수시 테스트는 `python3 main.py --dry-run`(발송 없이 콘솔 확인),
  `python3 main.py --force`(중복 무시), `python3 main.py --limit N`(선별 후 N건으로 추가 제한)을 조합해 사용한다.
- crontab 등록 예시는 [CLAUDE.md](../CLAUDE.md)의 "실행 방법" 참고.
