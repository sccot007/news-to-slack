# ITnews

지정한 웹사이트(RSS/HTML)의 최신 글을 카테고리 쿼터에 따라 선별하고, 한국어로
요약·번역해서 Slack으로 발송하는 개인용 뉴스 알리미.

## 주요 기능

- **다중 사이트 수집**: `source/data/sites.json`에 사이트만 추가하면 코드 수정 없이 확장 (RSS 우선, 없으면 HTML 스크래핑 폴백)
- **카테고리 쿼터 선별**: 하루 50개 슬롯을 카테고리별로 미리 배정하고, 남는 슬롯은 다른 카테고리 잉여분에서 최신순으로 재분배 (`selector.py`)
- **중복 발송 방지**: 링크/정규화된 제목/키워드 유사도를 기준으로 이미 보낸 글은 다시 보내지 않음 (`source/data/sent_history.json`)
- **자동 요약·번역**: 선별된 글마다 100자 이내 한국어 요약을 생성. 영문(비한국어) 기사는 `번역 제목 (원제)` 형식으로 표시
  - Gemini를 우선 호출하고 실패 시 Anthropic으로 폴백, 둘 다 실패하면 원문을 그대로 사용
  - selector가 먼저 대상을 추려내므로, 전체 수집 건수가 많아도 API는 최종 선별분만 호출한다
- **Slack 발송**: Incoming Webhook으로 발송, 클릭 시 원문 기사로 이동
- **전문(全文) 번역 페이지**: `full_translate: true`로 등록된 사이트(현재 CNCF Blog)는 제목을 클릭하면
  요약 대신 GitHub Pages에 자동 배포되는 번역 전문 페이지로 이동하고, 원문은 별도 링크로 제공 (`pages.py`)
  - `ARTICLES_RETENTION_DAYS`(기본 30일)보다 오래된 페이지는 실행할 때마다 자동으로 삭제되고
    git으로 커밋/push된다 (오래된 Slack 링크는 이후 404가 될 수 있음)

## 등록된 사이트 (카테고리별)

| 카테고리 | 슬롯 | 사이트 |
| --- | --- | --- |
| `domestic` | 20 | 우아한형제들 기술블로그, 카카오 기술블로그, 네이버 D2, AI타임스 |
| `cn-official` | 10 | Kubernetes Blog |
| `ai-primary` | 8 | OpenAI News, Google DeepMind Blog |
| `cn-deep` | 7 | The New Stack, InfoQ Cloud |
| `cncf-blog` | 7 | CNCF Blog (전문 번역, GitHub Pages 링크) |
| `ai-curation` | 5 | Simon Willison's Weblog |

## 폴더 구조

```
.
├── CLAUDE.md          # 개발 규칙 및 아키텍처 요약 (Claude Code용)
├── doc/               # 작업 계획 문서
│   └── plan.md
├── docs/              # GitHub Pages로 배포되는 번역 전문 페이지 (자동 생성)
│   └── articles/
└── source/            # 애플리케이션 코드
    ├── main.py        # 진입점
    ├── config.py
    ├── selector.py    # 카테고리 쿼터 기반 선별
    ├── summarizer.py  # 요약/번역 (Gemini → Anthropic 폴백)
    ├── pages.py       # 번역 전문 페이지 렌더링 + GitHub Pages 배포
    ├── dedup.py
    ├── fetcher/       # RSS / HTML 수집
    ├── notifier/      # Slack 발송
    └── data/
        ├── sites.json         # 수집 대상 + 카테고리 쿼터 설정 (git 추적)
        └── sent_history.json  # 발송 이력(중복 방지) — .gitignore 처리, 로컬 전용 (git push 안 됨)
```

## 설치 및 실행

```bash
cd source
pip3 install -r requirements.txt
cp .env.example .env   # 아래 환경변수 값 채우기
python3 main.py
```

curl이 시스템에 설치되어 있어야 한다 (일부 사이트가 Cloudflare로 `requests`를 차단할 때 폴백으로 사용).
Raspberry Pi OS/Debian에는 기본 포함되어 있고, 없으면 `apt install curl`.

### 환경변수 (`source/.env`)

| 변수 | 설명 | 필수 |
|---|---|---|
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL | O |
| `GEMINI_API_KEY` | 요약/번역용 Gemini API 키 (우선 사용) | O |
| `ANTHROPIC_API_KEY` | Gemini 실패 시 폴백으로 사용할 Anthropic API 키 | 권장 |
| `ITEMS_PER_SITE` | 사이트별로 확인할 최신 글 후보 개수 (기본 10) | X |
| `DEDUP_KEYWORD_THRESHOLD` | 중복 판단 키워드 자카드 유사도 임계값 (기본 0.6) | X |
| `HISTORY_RETENTION_DAYS` | 발송 이력 보관 기간, 일 단위 (기본 30, `ARTICLES_RETENTION_DAYS`와 동일하게 유지) | X |
| `PAGES_BASE_URL` | 번역 전문 페이지가 배포되는 GitHub Pages 기본 URL | `full_translate` 사이트 사용 시 |

일일 발송 한도(57건)와 카테고리 쿼터는 `.env`가 아니라 `source/data/sites.json`의
`total_limit`/`quotas`로 관리한다.

`.env`는 `.gitignore`에 포함되어 있어 커밋되지 않는다. 저장소에는 `source/.env.example`만 유지한다.

### 테스트용 실행 옵션

```bash
python3 main.py --dry-run          # Slack 발송/이력 저장 없이 콘솔에만 출력 (selector 선별 근거도 함께 출력)
python3 main.py --force            # 중복 여부 무시하고 강제로 대상에 포함
python3 main.py --limit 2          # 쿼터 선별 후 최종 건수를 N건으로 추가 제한
```

## GitHub Pages 설정 (전문 번역 페이지용, 최초 1회)

`full_translate: true`인 사이트(CNCF Blog)의 번역 전문 페이지는 이 저장소의 `docs/` 폴더에
쌓이고 GitHub Pages로 배포된다. **저장소 Settings → Pages에서 Source를 "Deploy from a branch",
Branch를 `main` / `docs`로 한 번 설정**해야 링크가 실제로 열린다 (API/CLI로 자동화하지 않았으니
수동으로 켜야 함).

또한 `main.py`가 실행되는 머신(개발 PC 또는 Raspberry Pi)에서 해당 저장소로 `git push`가
비대화형으로 가능해야 한다 (SSH 배포 키 또는 자격증명이 캐시된 HTTPS PAT). push에 실패해도
파이프라인은 중단되지 않고 Slack 발송은 계속 진행되지만, 그 경우 번역 페이지 링크는 push가
성공할 때까지 404가 난다. GitHub Pages 빌드 자체도 push 후 반영까지 수십 초~1분 정도 걸릴 수 있다.

## 운영 배포 (Raspberry Pi + crontab)

```bash
crontab -e
# 매일 오전 8시 실행
0 8 * * * cd /home/pi/ITnews/source && /usr/bin/python3 main.py >> /home/pi/ITnews/logs/cron.log 2>&1
```

## 사이트 추가하기

`source/data/sites.json`의 `sites` 배열에 항목을 추가한다. RSS가 있으면 `type: "rss"` + `feed_url`만
지정하면 되고, RSS가 없는 사이트는 `type: "html"` + CSS 셀렉터(`selectors`)를 지정한다.
반드시 `category`를 지정해야 하며, 해당 값은 `quotas`에 이미 존재하는 키여야 한다
(없으면 시작 시 검증에서 예외 발생). 신규 카테고리를 만들려면 `quotas`에도 슬롯을 추가하고,
쿼터 합계가 `total_limit`을 넘지 않는지 확인한다.

자세한 스키마와 알려진 제약(Anthropic News/The Batch RSS 없음, 우아한형제들 Cloudflare 차단 등)은
[doc/plan.md](doc/plan.md) 참고.

## 문서

- [CLAUDE.md](CLAUDE.md) — 아키텍처 요약 및 개발 규칙
- [doc/plan.md](doc/plan.md) — 상세 설계, 데이터 스키마, 마일스톤, 알려진 제약 사항
