# ITnews

지정한 웹사이트(URL 목록)의 최신 뉴스/글을 주기적으로 수집해서 Slack으로 발송하는 프로그램.
이미 보낸 글은 제목/키워드 기준으로 중복 판단하여 재발송하지 않는다.
카테고리별 쿼터를 적용하여 특정 소스에 편중되지 않도록 균형 잡힌 큐레이션을 유지한다.

## 폴더 구조

- `doc/` — 작업 계획 문서(md). 새 작업을 시작하기 전에 관련 계획 문서를 먼저 확인한다.
- `source/` — 실제 애플리케이션 코드.

## 아키텍처 개요

```
sites.json (수집 대상 URL 목록, 카테고리, 쿼터 설정)
      │
      ▼
  [fetcher] ── RSS 우선, 없으면 HTML 스크래핑
      │
      ▼
  [dedup] ── sent_history.json 과 대조 (제목/키워드 기준)
      │
      ▼
  [selector] ── 카테고리 쿼터에 따라 상위 N건 선별 (최신순)
      │
      ▼
  [summarizer] ── 선별된 글만 요약/번역 (API 비용 절감)
      │
      ▼
  [notifier] ── Slack Webhook으로 발송
      │
      ▼
  sent_history.json 갱신
```

**중요**: `summarizer`는 반드시 `selector` 뒤에 위치해야 한다.
발송하지 않을 글까지 요약하면 Gemini/Anthropic API 호출 비용이 3~5배로 증가한다.

자세한 설계/일정은 [doc/plan.md](doc/plan.md) 참고.

## 카테고리 쿼터

하루 20개 슬롯을 카테고리별로 미리 배정한다.
카테고리 안에서는 최신순으로 채우고, 비는 슬롯은 다른 카테고리 잉여분에서 최신순으로 재분배한다.

| 카테고리        | 슬롯 | 등록 사이트                                |
| --------------- | ---- | ------------------------------------------ |
| `domestic`      | 7   | 우아한형제들, 카카오, 네이버 D2            |
| `cn-official`   | 7    | CNCF Blog, Kubernetes Blog                 |
| `ai-primary`    | 3    | Anthropic, OpenAI, Google DeepMind         |
| `ai-curation`   | 1    | The Batch, Simon Willison                  |
| `cn-deep`       | 2    | The New Stack, InfoQ Cloud                 |


## sites.json 스키마

```json
{
  "quotas": {
    "ai-primary": 3,
    "ai-curation": 1,
    "cn-official": 7,
    "cn-deep": 2,
    "domestic": 7
  },
  "total_limit": 20,
  "sites": [
    {
      "id": "anthropic",
      "name": "Anthropic",
      "url": "https://www.anthropic.com/news",
      "type": "rss",
      "feed_url": "https://www.anthropic.com/rss.xml",
      "lang": "en",
      "category": "ai-primary",
      "enabled": true
    }
  ]
}
```

**필드 규칙**

- `quotas`: 카테고리별 슬롯 배정. 각 값의 합계가 `total_limit`을 초과하면 안 된다.
- `total_limit`: 하루 최대 발송 건수 (기본 10)2
- `category`: 각 사이트가 속한 카테고리. `quotas` 키와 반드시 일치해야 한다.
- `enabled: false`인 사이트는 fetcher가 건너뛴다.

## 선별 로직 (selector)

카테고리 안에서는 발행일 최신순으로 채우고,
비는 슬롯은 다른 카테고리의 잉여분(쿼터 초과분) 전체를 다시 최신순으로 모아 재분배한다.

```python
from collections import defaultdict

def select_articles(articles, quotas, total_limit=10):
    grouped = defaultdict(list)
    for a in articles:
        grouped[a.category].append(a)
    for cat in grouped:
        grouped[cat].sort(key=lambda x: x.published_at, reverse=True)

    selected = []
    leftover = 0
    for cat, quota in quotas.items():
        picked = grouped[cat][:quota]
        selected.extend(picked)
        leftover += (quota - len(picked))

    if leftover > 0:
        pool = []
        for cat, quota in quotas.items():
            pool.extend(grouped[cat][quota:])
        pool.sort(key=lambda x: x.published_at, reverse=True)
        selected.extend(pool[:leftover])

    return selected[:total_limit]
```

## 요약/번역

각 신규 글은 Slack 발송 전 `summarizer.py`를 거쳐 한국어 요약(100자 이내)을 붙인다.
영문(또는 비한국어) 기사는 `display_title`을 "한국어 번역 제목 (원제)" 형식으로 만든다.
Gemini(`GEMINI_API_KEY`)를 우선 호출하고 실패 시 Anthropic(`ANTHROPIC_API_KEY`)으로 폴백하며,
둘 다 실패하면 원문 제목/발췌를 그대로 사용한다 (`summarizer.py`의 `_error` 키로 로그에 남음).

`selector`가 상위 N건을 선별한 뒤에만 호출되므로,
전체 수집 건수가 100건이어도 API는 최대 `total_limit` 건만 호출한다.

## 핵심 데이터 파일 (source/data/)

- `sites.json` — 수집 대상 사이트 목록, 카테고리, 쿼터 설정
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

`--dry-run` 실행 시 `selector` 결정 근거를 콘솔에 남긴다:

```
[selector] ai-primary 2/3 → cn-deep 잉여분에서 1건 보충
[selector] final picks 10 (ai-primary:2 ai-curation:2 cn-official:2 cn-deep:3 domestic:1)
```

이 로그는 쿼터 튜닝 및 특정 카테고리의 발행량 편차를 파악하는 데 사용한다.

운영 환경은 Raspberry Pi 4이며 crontab으로 하루 1회 등록해서 사용한다.

```
# crontab -e
0 8 * * * cd /home/pi/ITnews/source && /usr/bin/python3 main.py >> /home/pi/ITnews/logs/cron.log 2>&1
```

## 개발 규칙

- 신규 사이트 추가/수집 규칙 변경은 `sites.json`만 수정하면 되도록 유지한다 (코드 변경 없이 설정으로 확장 가능해야 함).
- 신규 사이트 추가 시 반드시 `category` 필드를 지정해야 하며, `quotas`에 존재하는 카테고리여야 한다.
- 신규 카테고리 도입 시 `quotas` 블록에도 슬롯을 배정하고, 슬롯 합계가 `total_limit`을 초과하지 않도록 검증한다.
- `selector`는 반드시 `summarizer` 앞에 위치시켜 불필요한 API 호출을 방지한다.
- 중복 판단 로직은 제목 정규화(공백/특수문자 제거, 소문자화) + 핵심 키워드 비교를 사용한다. 임계값이나 로직 변경 시 `doc/plan.md`에도 반영한다.
- Slack Webhook URL 등 민감 정보는 `.env` 또는 `source/config.local.json` 같은 커밋 제외 파일에 두고, 저장소에는 예시 파일만 남긴다.
- 외부 사이트 스크래핑은 사이트 구조 변경에 취약하므로, RSS가 있으면 RSS를 우선 사용한다.
- 각 소스의 `feed_url`은 등록 시 반드시 curl 등으로 200 응답과 XML 파싱 여부를 검증한다.