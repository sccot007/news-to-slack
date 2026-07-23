# 작업 계획: 지정 사이트 최신 뉴스 → Slack 발송

## 1. 목표

사용자가 지정한 사이트(URL) 목록에서 최신 뉴스/글/블로그 글을 주기적으로 수집하여
Slack으로 발송한다. 이미 발송한 항목은 제목/핵심 키워드 기준으로 중복 판단하여
다시 보내지 않는다.

## 2. 확정된 결정 사항

| 항목 | 결정 |
|---|---|
| 발송 채널 | Slack (Incoming Webhook, 채널: 김희주) |
| 개발 언어 | Python |
| 수집 방식 | RSS/Atom 우선, 없으면 HTML 스크래핑으로 폴백 |
| 실행 방식 | Raspberry Pi 4에서 crontab으로 하루 1회 실행 후 종료 — 상시 실행 데몬 아님 |
| 수집 대상 | CNCF Blog(RSS), AI타임스(RSS) |
| 사이트별 확인 개수 | 최신 10개 |
| 사이트 설정 저장 | `source/data/sites.json` |
| 중복 방지 저장소 | `source/data/sent_history.json` (가벼운 JSON, DB 아님) |

필요 시 위 표는 언제든 갱신한다.

## 3. 데이터 스키마

### 3.1 `sites.json` (수집 대상)

```json
{
  "sites": [
    {
      "id": "example-tech-blog",
      "name": "Example Tech Blog",
      "url": "https://example.com",
      "type": "rss",
      "feed_url": "https://example.com/rss.xml",
      "enabled": true
    },
    {
      "id": "example-news-html",
      "name": "Example News (HTML)",
      "url": "https://news.example.com/latest",
      "type": "html",
      "enabled": true,
      "selectors": {
        "item": "ul.article-list li",
        "title": "a.title",
        "link": "a.title",
        "link_attr": "href"
      }
    }
  ]
}
```

- `type`: `"rss"` 또는 `"html"`.
- `type: html`일 때만 `selectors`가 필요하다 (사이트마다 CSS 셀렉터가 다름).
- 새 사이트 추가는 이 파일에 항목만 추가하면 되고, 코드 수정이 필요 없어야 한다.

### 3.2 `sent_history.json` (발송 이력 / 중복 방지)

로컬 "DB" 역할. 테이블의 컬럼에 해당하는 필드로 제목/키워드를 대조한다.

```json
{
  "entries": [
    {
      "site_id": "example-tech-blog",
      "title": "원본 제목",
      "normalized_title": "정규화된 제목(공백/특수문자 제거, 소문자)",
      "keywords": ["keyword1", "keyword2"],
      "link": "https://example.com/post/123",
      "sent_at": "2026-07-23T10:00:00+09:00"
    }
  ]
}
```

- 중복 판단: 같은 `site_id` 내에서 `normalized_title` 완전/유사 일치 OR `keywords` 자카드 유사도가
  임계값(예: 0.6) 이상이면 중복으로 간주하고 발송하지 않는다.
- 항목이 과도하게 늘어나지 않도록 오래된 항목(예: 90일 이상)은 정리(prune)한다.

## 4. 모듈 설계 (`source/`)

```
source/
  main.py            # 진입점: 사이트 순회 → 수집 → 중복 필터 → Slack 발송 → 이력 저장
  config.py          # 설정 로드 (.env, sites.json 경로 등)
  fetcher/
    __init__.py
    rss_fetcher.py   # feedparser 기반 RSS 수집
    html_fetcher.py  # requests + BeautifulSoup 기반 스크래핑
  dedup.py           # 제목 정규화, 키워드 추출, 유사도 비교, sent_history 조회/기록
  notifier/
    slack_notifier.py # Slack Incoming Webhook으로 메시지 전송
  data/
    sites.json
    sent_history.json
  requirements.txt
  .env.example       # SLACK_WEBHOOK_URL=... (실제 .env는 커밋하지 않음)
```

## 5. 처리 흐름 (main.py)

1. `sites.json` 로드, `enabled: true`인 사이트만 순회.
2. 사이트별로 `type`에 따라 RSS 또는 HTML fetcher 호출 → 항목 목록(제목, 링크, 게시일 등) 획득.
3. 각 항목에 대해 `dedup.py`로 `sent_history.json`과 대조.
4. 신규 항목만 모아 Slack 메시지로 포맷 (사이트명, 제목, 링크).
5. Slack Webhook으로 발송 (실패 시 재시도 로직 최소 1회).
6. 발송 성공한 항목만 `sent_history.json`에 append.
7. 오래된 이력 정리 후 저장.

## 6. Slack 연동

Incoming Webhook URL 발급 완료, `source/.env`(커밋 제외)에 `SLACK_WEBHOOK_URL`로 저장됨.
실제 발송 테스트 완료 (CNCF Blog 10건 + AI타임스 10건 발송, 재실행 시 0건으로 중복 방지 확인).

## 7. 마일스톤

- [x] M1. 프로젝트 스캐폴딩: `requirements.txt`, `.env.example`, `sites.json`/`sent_history.json` 초기 파일, 기본 폴더 구조
- [x] M2. RSS fetcher 구현 + 실제 사이트(CNCF Blog, AI타임스)로 동작 확인
- [x] M3. dedup 로직 구현 (정규화 + 키워드 유사도)
- [x] M4. Slack notifier 구현 + 실제 발송 테스트
- [x] M5. main.py로 전체 파이프라인 연결
- [ ] M6. HTML 스크래핑 fetcher 추가 (`html_fetcher.py`는 구현됨, RSS 없는 신규 사이트 등록 시 실전 검증 필요)
- [ ] M7. Raspberry Pi 4에 배포 및 crontab 등록 (하루 1회, `0 8 * * *`)
- [ ] M8. (선택) 로그 파일 로테이션, 수집 실패 시 Slack 알림, 이력 정리(prune) 동작 장기 검증

## 8. 참고 사항

- Raspberry Pi 배포 시 `source/` 전체를 복사한 뒤 `pip3 install -r requirements.txt`,
  `.env.example`을 `.env`로 복사해 `SLACK_WEBHOOK_URL` 등 값을 채운다 (`.env`는 git에 커밋하지 않음).
- 개발 중 수시 테스트는 `python3 main.py --dry-run`(발송 없이 콘솔 확인) 또는
  `python3 main.py --force`(중복 무시하고 강제 발송)로 한다.
- crontab 등록 예시는 [CLAUDE.md](../CLAUDE.md)의 "실행 방법" 참고.
