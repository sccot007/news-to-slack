# ITnews

지정한 웹사이트(URL 목록)의 최신 뉴스/글을 주기적으로 수집해서 Slack으로 발송하는 프로그램.
이미 보낸 글은 제목/키워드 기준으로 중복 판단하여 재발송하지 않는다.

## 폴더 구조

- `doc/` — 작업 계획 문서(md). 새 작업을 시작하기 전에 관련 계획 문서를 먼저 확인한다.
- `source/` — 실제 애플리케이션 코드.

## 아키텍처 개요

```
sites.json (수집 대상 URL 목록, 설정)
      │
      ▼
  [fetcher] ── RSS 우선, 없으면 HTML 스크래핑
      │
      ▼
  [dedup] ── sent_history.json 과 대조 (제목/키워드 기준)
      │
      ▼
  [notifier] ── Slack Webhook으로 신규 항목만 발송
      │
      ▼
  sent_history.json 갱신
```

자세한 설계/일정은 [doc/plan.md](doc/plan.md) 참고.

## 요약/번역

각 신규 글은 Slack 발송 전 `summarizer.py`를 거쳐 한국어 요약(100자 이내)을 붙인다.
영문(또는 비한국어) 기사는 `display_title`을 "한국어 번역 제목 (원제)" 형식으로 만든다.
Gemini(`GEMINI_API_KEY`)를 우선 호출하고 실패 시 Anthropic(`ANTHROPIC_API_KEY`)으로 폴백하며,
둘 다 실패하면 원문 제목/발췌를 그대로 사용한다 (`summarizer.py`의 `_error` 키로 로그에 남음).

## 핵심 데이터 파일 (source/data/)

- `sites.json` — 수집 대상 사이트 목록과 설정 (이름, URL, RSS 여부/셀렉터 등)
- `sent_history.json` — 발송 이력. 중복 방지용 로컬 저장소 (title, 정규화된 키워드, 발송 시각, 링크)

## 실행 방법

```
cd source
pip3 install -r requirements.txt   # 최초 1회
cp .env.example .env               # SLACK_WEBHOOK_URL 등 실제 값 채우기
python3 main.py                    # 실제 발송
python3 main.py --dry-run          # 발송 없이 콘솔 출력만 (개발 중 수시 테스트용)
python3 main.py --force            # 중복 여부 무시하고 강제 발송 (테스트용)
python3 main.py --limit 2          # 전체 대상 글을 N건으로 제한 (테스트용, --force와 함께 자주 사용)
```

운영 환경은 Raspberry Pi 4이며 crontab으로 하루 1회 등록해서 사용한다.

```
# crontab -e
0 8 * * * cd /home/pi/ITnews/source && /usr/bin/python3 main.py >> /home/pi/ITnews/logs/cron.log 2>&1
```

## 개발 규칙

- 신규 사이트 추가/수집 규칙 변경은 `sites.json`만 수정하면 되도록 유지한다 (코드 변경 없이 설정으로 확장 가능해야 함).
- 중복 판단 로직은 제목 정규화(공백/특수문자 제거, 소문자화) + 핵심 키워드 비교를 사용한다. 임계값이나 로직 변경 시 `doc/plan.md`에도 반영한다.
- Slack Webhook URL 등 민감 정보는 `.env` 또는 `source/config.local.json` 같은 커밋 제외 파일에 두고, 저장소에는 예시 파일만 남긴다.
- 외부 사이트 스크래핑은 사이트 구조 변경에 취약하므로, RSS가 있으면 RSS를 우선 사용한다.
