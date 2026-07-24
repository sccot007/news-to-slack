"""카테고리 쿼터 기반 선별. dedup 이후, summarizer 이전에 위치한다.

전체 수집 건수가 많아도 요약/번역 API는 최종 선별된 건수만큼만 호출되어야 하므로,
main.py는 반드시 select_candidates()를 거친 결과만 summarizer에 넘겨야 한다.
"""
from collections import defaultdict
from datetime import datetime, timezone

_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)


def _published_at(candidate: dict) -> datetime:
    value = candidate["item"].get("published_at")
    if not value:
        return _EPOCH
    return datetime.fromisoformat(value)


def select_candidates(
    candidates: list[dict], quotas: dict, total_limit: int, log=None
) -> list[dict]:
    """candidates: [{"site": site_dict, "item": item_dict}, ...]

    1) 카테고리별로 묶어 발행일 최신순 정렬 후 쿼터만큼 선택
    2) 쿼터를 못 채운 카테고리의 부족분(leftover)만큼, 나머지 카테고리의 쿼터 초과분을
       모아 최신순으로 재분배
    3) total_limit으로 최종 truncate
    """
    grouped = defaultdict(list)
    for candidate in candidates:
        grouped[candidate["site"]["category"]].append(candidate)
    for items in grouped.values():
        items.sort(key=_published_at, reverse=True)

    selected = []
    picked_count = {}
    leftover_slots = 0

    for category, quota in quotas.items():
        picked = grouped[category][:quota]
        picked_count[category] = len(picked)
        selected.extend(picked)

        shortfall = quota - len(picked)
        if shortfall > 0:
            leftover_slots += shortfall
            if log:
                log(f"[selector] {category} {len(picked)}/{quota} (부족 {shortfall}건)")
        elif log:
            log(f"[selector] {category} {len(picked)}/{quota}")

    if leftover_slots > 0:
        surplus_pool = []
        for category, quota in quotas.items():
            surplus_pool.extend(grouped[category][quota:])
        surplus_pool.sort(key=_published_at, reverse=True)

        bonus = surplus_pool[:leftover_slots]
        for candidate in bonus:
            category = candidate["site"]["category"]
            picked_count[category] = picked_count.get(category, 0) + 1
        selected.extend(bonus)

        if log and bonus:
            log(f"[selector] 잉여분에서 {len(bonus)}건 보충")

    selected = selected[:total_limit]

    if log:
        summary = " ".join(f"{cat}:{picked_count.get(cat, 0)}" for cat in quotas)
        log(f"[selector] final picks {len(selected)} ({summary})")

    return selected
