"""方案质量评估服务：规则 + LLM 双引擎评分

评估维度（5 项）：
1. 预算符合度（规则）：费用分项合计 vs 总预算、总预算 vs 用户预算的偏差
2. 路线合理性（规则）：基于行程校验的跨区奔波警告数量
3. 引用真实率（规则）：source_id 与知识库的映射率 + 每日行程知识库覆盖率
4. 结构完整性（规则）：方案必要字段与每日时段齐全度
5. 需求贴合度（LLM）：需求（含意图）与方案的契合程度

总分 = 五维平均分。低于阈值时由 Agent 工作流触发带反馈重生成。
"""
import json

from app.services import llm_service, prompt_templates


def _ratio_score(ratio: float) -> int:
    """偏差比例 → 分数：偏差 ≤5% 为 100 分，每多 5% 扣 10 分，最低 40 分"""
    if ratio <= 0.05:
        return 100
    return max(40, 100 - int((ratio - 0.05) / 0.05 + 0.5) * 10 - 10)


def eval_budget(plan: dict, structured: dict) -> dict:
    """预算符合度：分项合计与总预算偏差 + 总预算与用户预算偏差"""
    basic = plan.get("basic_info") or {}
    breakdown = basic.get("budget_breakdown", {})
    total_budget = float(basic.get("total_budget", 0) or 0)
    user_budget = float(structured.get("budget", 0) or 0)
    issues = []
    score = 100

    if total_budget > 0:
        breakdown_sum = sum(float(v or 0) for v in breakdown.values() if isinstance(v, (int, float)))
        r1 = abs(breakdown_sum - total_budget) / total_budget
        if r1 > 0.05:
            issues.append(f"费用分项合计 ¥{breakdown_sum:.0f} 与总预算 ¥{total_budget:.0f} 偏差 {r1 * 100:.0f}%")
        score = min(score, _ratio_score(r1))

    if user_budget > 0 and total_budget > 0:
        over = (total_budget - user_budget) / user_budget
        if over > 0.05:
            issues.append(f"方案总预算超出用户预算 {over * 100:.0f}%")
            score = min(score, _ratio_score(over))
    elif user_budget <= 0:
        issues.append("用户未提供预算，无法精确核对费用贴合度")
        score = min(score, 80)

    return {
        "name": "预算符合度",
        "score": score,
        "detail": "；".join(issues) or "费用分配与预算一致",
    }


def eval_route(plan_warnings: list) -> dict:
    """路线合理性：统计跨区奔波警告"""
    cross = [w for w in plan_warnings if w.get("level") == "warning" and "跨区" in w.get("message", "")]
    count = len(cross)
    score = {0: 100, 1: 85, 2: 70}.get(count, 55)
    detail = f"行程校验发现 {count} 处跨区奔波问题" if count else "每日景点地理位置紧凑，无跨区奔波"
    return {"name": "路线合理性", "score": score, "detail": detail}


def eval_references(plan: dict, knowledge: dict) -> dict:
    """引用真实率：source_id 可映射率 + 知识库覆盖率"""
    source_map = {
        doc["id"]
        for doc in knowledge.get("attractions", []) + knowledge.get("foods", []) + knowledge.get("hotels", [])
    }
    all_ids = []
    slots_total = 0
    slots_with_ref = 0
    for day in plan.get("daily_schedule", []):
        for slot in ("morning", "afternoon", "evening"):
            sd = day.get(slot)
            if not isinstance(sd, dict):
                continue
            slots_total += 1
            sid = sd.get("source_id", "")
            if sid:
                slots_with_ref += 1
                all_ids.append(sid)
    for food in plan.get("food_recommendations", []):
        if food.get("source_id"):
            all_ids.append(food["source_id"])
    hotel = plan.get("hotel_recommendation") or {}
    if hotel.get("source_id"):
        all_ids.append(hotel["source_id"])

    if not all_ids:
        return {"name": "引用真实率", "score": 30, "detail": "方案未引用知识库（source_id 为空），存在虚构风险"}

    mapped = sum(1 for sid in all_ids if sid in source_map)
    real_rate = mapped / len(all_ids)
    cover_rate = slots_with_ref / slots_total if slots_total else 0
    score = int(real_rate * 70 + cover_rate * 30)
    detail = f"引用 {mapped}/{len(all_ids)} 条可映射到知识库；每日行程知识库覆盖 {slots_with_ref}/{slots_total} 个时段"
    return {"name": "引用真实率", "score": score, "detail": detail}


def eval_structure(plan: dict) -> dict:
    """结构完整性：必要字段与每日时段齐全度"""
    required = ["basic_info", "daily_schedule", "food_recommendations", "hotel_recommendation", "tips"]
    missing = [k for k in required if not plan.get(k)]
    days = plan.get("daily_schedule", [])
    day_ok = (
        all(isinstance(d.get("morning"), dict) and isinstance(d.get("afternoon"), dict) for d in days)
        if days else False
    )
    score = 100
    issues = []
    if missing:
        score -= 15 * len(missing)
        issues.append("缺少字段：" + "/".join(missing))
    if not days:
        score -= 20
        issues.append("无每日行程")
    elif not day_ok:
        score -= 10
        issues.append("部分日期时段不完整")
    return {"name": "结构完整性", "score": max(0, score), "detail": "；".join(issues) or "方案结构完整"}


def eval_llm_fit(structured: dict, plan: dict) -> dict:
    """需求贴合度：LLM 评估偏好/特殊需求/意图是否被满足"""
    summary = {
        "destination": (plan.get("basic_info") or {}).get("destination"),
        "trip_days": (plan.get("basic_info") or {}).get("trip_days"),
        "total_budget": (plan.get("basic_info") or {}).get("total_budget"),
        "themes": [d.get("theme") for d in plan.get("daily_schedule", [])],
        "activities": [
            d.get(slot, {}).get("activity")
            for d in plan.get("daily_schedule", [])
            for slot in ("morning", "afternoon", "evening")
            if isinstance(d.get(slot), dict)
        ][:15],
        "foods": [f.get("name") for f in plan.get("food_recommendations", [])][:6],
        "hotel": (plan.get("hotel_recommendation") or {}).get("name"),
    }
    messages = [
        {"role": "system", "content": prompt_templates.SYSTEM_PROMPT},
        {"role": "user", "content": prompt_templates.QUALITY_EVAL_PROMPT.format(
            requirement_json=json.dumps(structured, ensure_ascii=False, indent=2),
            plan_summary=json.dumps(summary, ensure_ascii=False, indent=2),
        )},
    ]
    try:
        raw = llm_service.chat_json(messages, temperature=0.2, max_tokens=800)
        data = json.loads(raw)
        score = int(data.get("score", 3))
        return {
            "name": "需求贴合度",
            "score": max(0, min(100, score * 20)),
            "detail": data.get("reason", ""),
        }
    except Exception:
        return {"name": "需求贴合度", "score": 60, "detail": "LLM 评估失败，按中等分计"}


def evaluate(plan: dict, knowledge: dict, structured: dict, plan_warnings: list) -> dict:
    """综合评估旅行方案，返回质量报告

    返回：{overall_score, level, dimensions: [...], suggestions: [...]}
    """
    dims = [
        eval_budget(plan, structured),
        eval_route(plan_warnings),
        eval_references(plan, knowledge),
        eval_structure(plan),
        eval_llm_fit(structured, plan),
    ]
    overall = int(sum(d["score"] for d in dims) / len(dims))
    level = "优秀" if overall >= 85 else "良好" if overall >= 70 else "一般" if overall >= 60 else "待改进"
    suggestions = [d["detail"] for d in dims if d["score"] < 80]
    return {
        "overall_score": overall,
        "level": level,
        "dimensions": dims,
        "suggestions": suggestions,
    }
