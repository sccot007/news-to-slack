# ITnews

지정한 웹사이트(RSS/HTML)의 최신 글을 주기적으로 수집해서 Slack으로 요약·발송하는 개인용 뉴스 알리미.

## 주요 기능

- **다중 사이트 수집**: `source/data/sites.json`에 사이트만 추가하면 코드 수정 없이 확장 (RSS 우선, 없으면 HTML 스크래핑 폴백)
- **중복 발송 방지**: 링크/정규화된 제목/키워드 유사도를 기준으로 이미 보낸 글은 다시 보내지 않음 (`source/data/sent_history.json`)
- **자동 요약·번역**: 신규 글마다 100자 이내 한국어 요약을 생성. 영문(비한국어) 기사는 `번역 제목 (원제)` 형식으로 표시
  - Gemini를 우선 호출하고 실패 시 Anthropic으로 폴백, 둘 다 실패하면 원문을 그대로 사용
- **Slack 발송**: Incoming Webhook으로 발송, 클릭 시 원문 기사로 이동

## 폴더 구조

```
.
├── CLAUDE.md          # 개발 규칙 및 아키텍처 요약 (Claude Code용)
├── doc/               # 작업 계획 문서
│   └── plan.md
└── source/            # 애플리케이션 코드
    ├── main.py        # 진입점
    ├── config.py
    ├── dedup.py
    ├── summarizer.py
    ├── fetcher/       # RSS / HTML 수집
    ├── notifier/      # Slack 발송
    └── data/
        ├── sites.json         # 수집 대상 설정
        └── sent_history.json  # 발송 이력(중복 방지)
```

## 설치 및 실행

```bash
cd source
pip3 install -r requirements.txt
cp .env.example .env   # 아래 환경변수 값 채우기
python3 main.py
```

### 환경변수 (`source/.env`)

| 변수 | 설명 | 필수 |
|---|---|---|
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL | O |
| `GEMINI_API_KEY` | 요약/번역용 Gemini API 키 (우선 사용) | O |
| `ANTHROPIC_API_KEY` | Gemini 실패 시 폴백으로 사용할 Anthropic API 키 | 권장 |
| `ITEMS_PER_SITE` | 사이트별로 확인할 최신 글 개수 (기본 10) | X |
| `DEDUP_KEYWORD_THRESHOLD` | 중복 판단 키워드 자카드 유사도 임계값 (기본 0.6) | X |
| `HISTORY_RETENTION_DAYS` | 발송 이력 보관 기간, 일 단위 (기본 90) | X |

`.env`는 `.gitignore`에 포함되어 있어 커밋되지 않는다. 저장소에는 `source/.env.example`만 유지한다.

### 테스트용 실행 옵션

```bash
python3 main.py --dry-run          # Slack 발송/이력 저장 없이 콘솔에만 출력
python3 main.py --force            # 중복 여부 무시하고 강제로 대상에 포함
python3 main.py --limit 2          # 전체 대상 글을 N건으로 제한
```

## 운영 배포 (Raspberry Pi + crontab)

```bash
crontab -e
# 매일 오전 8시 실행
0 8 * * * cd /home/pi/ITnews/source && /usr/bin/python3 main.py >> /home/pi/ITnews/logs/cron.log 2>&1
```

## 사이트 추가하기

`source/data/sites.json`에 항목을 추가한다. RSS가 있으면 `type: "rss"` + `feed_url`만 지정하면 되고,
RSS가 없는 사이트는 `type: "html"` + CSS 셀렉터(`selectors`)를 지정한다. 자세한 스키마는
[doc/plan.md](doc/plan.md#3-데이터-스키마) 참고.

## 문서

- [CLAUDE.md](CLAUDE.md) — 아키텍처 요약 및 개발 규칙
- [doc/plan.md](doc/plan.md) — 상세 설계, 데이터 스키마, 마일스톤
