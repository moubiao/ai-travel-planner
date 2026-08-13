"""行程冲突检测：校验方案的合理性，返回需要关注的问题列表

检测项：
1. 同一天跨区奔波（相邻景点距离过远）
2. 雨天安排户外景点
3. 预算偏差过大（估算费用 vs 总预算）
4. 门票费用占比过高
"""
from app.services import map_service


def _get_coord_by_id(knowledge: dict, source_id: str) -> list | None:
    """按 source_id 从知识库检索结果中找景点坐标"""
    for att in knowledge.get("attractions", []):
        if att["id"] == source_id:
            return att["metadata"].get("coordinates")
    return None


def _get_attraction_meta(knowledge: dict, source_id: str) -> dict:
    """按 source_id 找景点元数据"""
    for att in knowledge.get("attractions", []):
        if att["id"] == source_id:
            return att["metadata"]
    return {}


def _day_has_rain(weather: dict, date: str, city: str | None = None) -> bool:
    """判断某日期是否为雨天（多城市时按城市匹配）"""
    for day in weather.get("days", []):
        if day.get("date") != date:
            continue
        if city and day.get("city") and day.get("city") != city:
            continue
        return day.get("is_rain", False) or day.get("precip_prob", 0) >= 60
    return False


def check_plan_conflicts(plan: dict, knowledge: dict, weather: dict | None = None) -> list[dict]:
    """校验旅行方案，返回警告列表 [{level, message}]"""
    warnings = []
    weather = weather or {}

    daily_schedule = plan.get("daily_schedule", [])
    budget_breakdown = (plan.get("basic_info") or {}).get("budget_breakdown", {})
    total_budget = (plan.get("basic_info") or {}).get("total_budget", 0) or 0

    # 1. 同一天跨区奔波：当天相邻时段景点距离 > 30km
    for day in daily_schedule:
        day_coords = []
        for slot in ("morning", "afternoon", "evening"):
            slot_data = day.get(slot)
            if not isinstance(slot_data, dict):
                continue
            coord = _get_coord_by_id(knowledge, slot_data.get("source_id", ""))
            if coord:
                day_coords.append((slot_data.get("source_id"), coord))
        if len(day_coords) >= 2:
            for i in range(len(day_coords) - 1):
                dist = map_service.haversine(day_coords[i][1], day_coords[i + 1][1])
                if dist > 30:
                    warnings.append({
                        "level": "warning",
                        "message": f"Day{day.get('day','?')} 相邻景点相距约 {dist:.0f}km，跨区较奔波，建议调整行程顺序",
                    })

    # 2. 雨天安排户外景点（多城市时按当天所在城市匹配天气）
    if weather.get("days"):
        for day in daily_schedule:
            date = day.get("date", "")
            day_city = day.get("city", "") or None
            if not _day_has_rain(weather, date, day_city):
                continue
            for slot in ("morning", "afternoon", "evening"):
                slot_data = day.get(slot)
                if not isinstance(slot_data, dict):
                    continue
                meta = _get_attraction_meta(knowledge, slot_data.get("source_id", ""))
                if meta.get("indoor_outdoor") == "outdoor":
                    warnings.append({
                        "level": "warning",
                        "message": f"Day{day.get('day','?')}（{date}）有雨，{slot_data.get('activity','该行程')} 是户外景点，建议换成室内",
                    })

    # 3. 预算偏差：每日费用合计 vs 总预算
    total_cost = sum(
        float(slot_data.get("cost", 0) or 0)
        for day in daily_schedule
        for slot in ("morning", "afternoon", "evening")
        if isinstance(day.get(slot), dict) for slot_data in [day.get(slot)]
    )
    if total_budget > 0:
        diff_ratio = abs(total_cost - total_budget) / total_budget
        if diff_ratio > 0.3:
            warnings.append({
                "level": "info",
                "message": f"行程估算费用（¥{total_cost:.0f}）与总预算（¥{total_budget}）偏差 {diff_ratio*100:.0f}%，请注意实际消费",
            })

    # 4. 门票占比过高
    ticket_total = sum(
        float(_get_attraction_meta(knowledge, day.get(slot, {}).get("source_id", "")).get("ticket", 0) or 0)
        for day in daily_schedule for slot in ("morning", "afternoon", "evening")
    )
    if total_budget > 0 and ticket_total > 0 and ticket_total / total_budget > 0.4:
        warnings.append({
            "level": "info",
            "message": f"门票估算合计 ¥{ticket_total:.0f}，占预算 {ticket_total/total_budget*100:.0f}%，偏高，可考虑免费景点替代",
        })

    return warnings
