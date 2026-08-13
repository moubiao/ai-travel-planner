"""Agent 服务：LangGraph 编排旅行规划工作流（多Agent协作）

工作流：需求分析 → 知识检索 → 天气查询 → 专家子Agent并行协作 → 主Agent方案生成 → 行程校验

多Agent协作：
- 景点Agent：从候选景点中挑选行程景点（偏好/预算/天气感知）
- 美食Agent：挑选餐厅
- 路线Agent：按地理位置分组优化路线
- 预算Agent：规划费用分配
- 主Agent：综合四路专家建议生成最终方案（可解释性：每个推荐带子Agent理由）
"""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.services import (city_links, llm_service, map_service, plan_validator,
                          prompt_templates, quality_service, rag_service,
                          weather_service)
from app.services.knowledge_loader import city_name_to_code, resolve_cities


class AgentState(TypedDict):
    """Agent 工作流状态"""

    requirement_text: str   # 用户原始需求（自然语言）
    structured: dict        # 结构化旅行需求
    knowledge: dict         # RAG 知识检索结果
    weather: dict           # 天气预报
    specialist_results: dict  # 专家子Agent输出（景点/美食/路线/预算）
    plan: dict              # 最终旅行方案
    references: list        # 方案引用的知识库来源
    plan_warnings: list     # 行程冲突检测警告
    trace: list             # 节点执行日志（用于展示 Agent 过程）
    variant: str            # 方案变体：""默认 / budget性价比 / comfort舒适
    quality_report: dict    # 质量评估报告（规则+LLM 双引擎）
    quality_feedback: str   # 质量评估反馈（低分时注入下一轮生成）
    retry_count: int        # 质量不达标重试次数


def _add_trace(state: AgentState, node: str, detail: str) -> list:
    """追加节点执行日志"""
    return state["trace"] + [{"node": node, "detail": detail, "time": datetime.now().strftime("%H:%M:%S")}]


# ---------- 节点 1：需求分析 ----------
def analyze_node(state: AgentState) -> AgentState:
    """解析用户需求为结构化 JSON（缺失字段由 LLM 补全）"""
    structured = dict(state["structured"])

    if state["requirement_text"]:
        messages = [
            {"role": "system", "content": prompt_templates.SYSTEM_PROMPT},
            {"role": "user", "content": prompt_templates.ANALYZE_PROMPT.format(
                requirement=state["requirement_text"],
                current_year=datetime.now().year,
            )},
        ]
        raw = llm_service.chat_json(messages, temperature=0.2)
        parsed = json.loads(raw)
        for key, value in parsed.items():
            if key not in structured and value not in ("", 0, [], None):
                structured[key] = value

    # 舒适版预算上浮 50%（取整到百位），让两套对比方案拉开差距
    if state.get("variant") == "comfort" and structured.get("budget"):
        structured["budget"] = round(structured["budget"] * 1.5 / 100) * 100

    detail = (
        f"目的地:{structured.get('destination','?')} "
        f"天数:{structured.get('days','?')}天 "
        f"人数:{structured.get('people','?')}人 "
        f"预算:{structured.get('budget','?')}元 "
        f"偏好:{'、'.join(structured.get('preferences', [])) or '未指定'}"
    )
    return {
        **state,
        "structured": structured,
        "trace": _add_trace(state, "需求分析", detail),
    }


# ---------- 节点 2：知识检索（RAG） ----------
def retrieve_node(state: AgentState) -> AgentState:
    """从旅游知识库检索景点/美食/酒店资料"""
    knowledge = rag_service.search_for_requirement(state["structured"])
    n_att = len(knowledge["attractions"])
    n_food = len(knowledge["foods"])
    n_hotel = len(knowledge["hotels"])
    detail = f"检索到 {n_att} 个景点、{n_food} 个美食、{n_hotel} 个酒店（来源：{knowledge['city_name']}知识库）"
    return {
        **state,
        "knowledge": knowledge,
        "trace": _add_trace(state, "知识检索", detail),
    }


# ---------- 节点 3：天气查询（支持多城市） ----------
def weather_node(state: AgentState) -> AgentState:
    """查询行程期间天气预报（多城市时逐城查询，标注城市），标记雨天"""
    structured = state["structured"]
    cities = resolve_cities(structured.get("cities") or structured.get("destination", ""))
    days = structured.get("days", 3) or 3
    start_date = structured.get("start_date", "") or None

    all_days = []
    rain_days = []
    summaries = []
    is_demo = False
    for city_name in cities:
        city = city_name_to_code(city_name)
        if not city:
            continue
        weather = weather_service.get_weather(city, start_date, days)
        is_demo = is_demo or weather.get("is_demo", False)
        for d in weather.get("days", []):
            d["city"] = city_name  # 标注城市（多城市行程用）
        all_days.extend(weather.get("days", []))
        rain_days.extend(d["date"] for d in weather.get("days", []) if d.get("is_rain"))
        summaries.append(
            "、".join(
                f"{d['date']} {d['text_day']} {d['temp_min']}~{d['temp_max']}°C(降水{d['precip_prob']}%)"
                for d in weather.get("days", [])
            )
        )

    weather = {"city": "+".join(cities) or "", "is_demo": is_demo, "days": all_days}
    detail = "；".join(f"{city}:{s}" for city, s in zip(cities, summaries)) or "（无天气数据）"
    detail += f"。{'⚠️ 雨天:' + '、'.join(rain_days) if rain_days else '行程期间无降雨'}"
    if is_demo:
        detail += "（演示天气数据，配置和风天气 key 后使用真实预报）"
    weather["rain_days"] = rain_days
    return {
        **state,
        "weather": weather,
        "trace": _add_trace(state, "天气查询", detail),
    }


# ---------- 节点 4：专家子Agent并行协作 ----------
def _format_candidates(knowledge: dict, doc_type: str) -> str:
    """将检索结果裁剪为子Agent的候选文本"""
    items = knowledge.get(doc_type, [])
    lines = []
    for item in items:
        m = item["metadata"]
        if doc_type == "attraction":
            coord = m.get("coordinates", [])
            coord_str = f"坐标:{coord[0]},{coord[1]}" if coord else ""
            lines.append(
                f"[{item['id']}] {item['name']} | 类别:{m.get('category','')} | 门票:{m.get('ticket',0)}元 "
                f"| 时长:{item['text'].split('。')[-2] if item['text'] else ''} | {coord_str}"
            )
        elif doc_type == "foods":
            lines.append(
                f"[{item['id']}] {item['name']} | 类别:{m.get('category','')} | 人均:{m.get('price_per_person',0)}元 | 区域:{m.get('area','')}"
            )
    return "\n".join(lines) or "（无候选）"


def _run_specialist(name: str, system_prompt: str, user_content: str) -> dict:
    """运行单个专家子Agent（独立 LLM 调用）"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    raw = llm_service.chat_json(messages, temperature=0.4)
    return json.loads(raw)


def _attraction_specialist(state: AgentState) -> dict:
    """景点专家：挑选行程景点"""
    knowledge = state["knowledge"]
    structured = state["structured"]
    weather_text = "、".join(
        f"{d['date']} {d['text_day']} 降水{d['precip_prob']}%"
        for d in state["weather"].get("days", [])
    ) or "（无数据）"
    content = prompt_templates.SPECIALIST_ATTRACTION_PROMPT.format(
        requirement_json=json.dumps(structured, ensure_ascii=False, indent=2),
        candidates_text=_format_candidates(knowledge, "attraction"),
        weather_text=weather_text,
    )
    return _run_specialist("景点专家", prompt_templates.SYSTEM_PROMPT, content)


def _food_specialist(state: AgentState) -> dict:
    """美食专家：挑选餐厅"""
    knowledge = state["knowledge"]
    structured = state["structured"]
    content = prompt_templates.SPECIALIST_FOOD_PROMPT.format(
        requirement_json=json.dumps(structured, ensure_ascii=False, indent=2),
        candidates_text=_format_candidates(knowledge, "foods"),
    )
    return _run_specialist("美食专家", prompt_templates.SYSTEM_PROMPT, content)


def _route_specialist(state: AgentState) -> dict:
    """路线专家：按地理位置分组"""
    knowledge = state["knowledge"]
    content = prompt_templates.SPECIALIST_ROUTE_PROMPT.format(
        candidates_text=_format_candidates(knowledge, "attraction"),
    )
    try:
        result = _run_specialist("路线专家", prompt_templates.SYSTEM_PROMPT, content)
    except Exception as exc:
        print(f"[agent] 路线专家调用失败，使用规则聚类: {exc}")
        result = {}

    # LLM 输出为空时，用坐标规则聚类兜底
    if not result.get("grouping"):
        attractions = knowledge.get("attractions", [])
        groups = map_service.cluster_by_proximity(attractions, threshold_km=8.0)
        result = {
            "grouping": [
                {"area": f"区域{i + 1}", "attraction_ids": [item["id"] for item in group]}
                for i, group in enumerate(groups) if len(group) > 1
            ],
            "notes": ["按地理位置就近分组，建议同区域安排在同一天（规则聚类兜底）"],
        }
    return result


def _budget_specialist(state: AgentState) -> dict:
    """预算专家：费用分配"""
    knowledge = state["knowledge"]
    structured = state["structured"]
    content = prompt_templates.SPECIALIST_BUDGET_PROMPT.format(
        requirement_json=json.dumps(structured, ensure_ascii=False, indent=2),
        candidates_text=_format_candidates(knowledge, "attraction"),
    )
    return _run_specialist("预算专家", prompt_templates.SYSTEM_PROMPT, content)


def specialists_node(state: AgentState) -> AgentState:
    """并行运行四个专家子Agent，汇总各自建议"""
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            "attraction": pool.submit(_attraction_specialist, state),
            "food": pool.submit(_food_specialist, state),
            "route": pool.submit(_route_specialist, state),
            "budget": pool.submit(_budget_specialist, state),
        }
        results = {name: fut.result() for name, fut in futures.items()}

    # 生成执行日志
    new_trace = state["trace"]
    att_count = len(results["attraction"].get("selections", []))
    new_trace = _add_trace({**state, "trace": new_trace}, "景点Agent", f"从候选中挑选 {att_count} 个景点（结合偏好/天气/预算）")
    new_trace = _add_trace({**state, "trace": new_trace}, "美食Agent", f"挑选 {len(results['food'].get('selections', []))} 个美食")
    groups = len(results["route"].get("grouping", []))
    new_trace = _add_trace({**state, "trace": new_trace}, "路线Agent", f"按地理位置分为 {groups} 个区域组")
    bd = results["budget"].get("budget_breakdown", {})
    bd_summary = "、".join(f"{k}{v}元" for k, v in list(bd.items())[:3])
    new_trace = _add_trace({**state, "trace": new_trace}, "预算Agent", f"费用分配：{bd_summary}等")

    return {
        **state,
        "specialist_results": results,
        "trace": new_trace,
    }


# 方案变体风格指引（注入主Agent，差异化两套对比方案）
STYLE_GUIDANCE = {
    "budget": (
        "用户要求【高性价比】风格：优先免票/低门票景点，酒店选经济型（如全季/如家/汉庭），"
        "餐饮控制人均支出，突出省钱技巧；方案基本信息的预算分配应尽量低于预算总额。"
    ),
    "comfort": (
        "用户要求【舒适体验】风格：优先品质酒店（亚朵/四星级及以上），餐饮选知名餐厅，"
        "每天节奏宽松不赶路，可适当增加预算用于住宿与餐饮。"
    ),
}

VARIANT_LABELS = {"budget": "性价比版", "comfort": "舒适版"}


# ---------- 节点 5：主Agent方案生成 ----------
def plan_node(state: AgentState) -> AgentState:
    """主Agent综合专家建议 + 知识库 + 天气生成最终方案（低分时带质量反馈重生成）"""
    structured = state["structured"]
    knowledge = state["knowledge"]
    specialists = state["specialist_results"]
    variant = state.get("variant", "")
    quality_feedback = state.get("quality_feedback", "")
    retrying = bool(quality_feedback)
    # 多城市衔接信息（跨城高铁建议，单城市为空）
    cities = resolve_cities(structured.get("cities") or structured.get("destination", ""))
    city_links_text = city_links.format_city_links(cities)

    weather_text = "、".join(
        f"{d['date']} {d['text_day']} {d['temp_min']}~{d['temp_max']}°C 降水概率{d['precip_prob']}%"
        for d in state["weather"].get("days", [])
    ) or "（暂无天气数据）"

    if knowledge.get("attractions") and specialists.get("attraction", {}).get("selections"):
        # 专家建议文本化
        att_selections = "\n".join(
            f"- {s['source_id']}（建议Day{s.get('day_hint','?')}）：{s.get('reason','')}"
            for s in specialists["attraction"].get("selections", [])
        ) or "（无）"
        food_selections = "\n".join(
            f"- {s['source_id']}（{s.get('meal','')}）：{s.get('reason','')}"
            for s in specialists["food"].get("selections", [])
        ) or "（无）"
        budget_plan = json.dumps(specialists.get("budget", {}), ensure_ascii=False, indent=2)
        route_plan = json.dumps(specialists.get("route", {}), ensure_ascii=False, indent=2)

        prompt = prompt_templates.MULTI_AGENT_PLAN_PROMPT.format(
            requirement_json=json.dumps(structured, ensure_ascii=False, indent=2),
            knowledge_text=rag_service.format_knowledge_for_prompt(knowledge),
            weather_text=weather_text,
            city_links_text=city_links_text,
            style_guidance=STYLE_GUIDANCE.get(variant, ""),
            quality_feedback=quality_feedback,
            attraction_selections=att_selections,
            food_selections=food_selections,
            budget_plan=budget_plan,
            route_plan=route_plan,
            current_year=datetime.now().year,
        )
    else:
        prompt = prompt_templates.PLAN_PROMPT.format(
            requirement_json=json.dumps(structured, ensure_ascii=False, indent=2),
            current_year=datetime.now().year,
        )

    messages = [
        {"role": "system", "content": prompt_templates.SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    raw = llm_service.chat_json(messages, temperature=0.6)
    plan = json.loads(raw)
    references = rag_service.build_references(plan, knowledge)

    return {
        **state,
        "plan": plan,
        "references": references,
        "trace": _add_trace(state, "方案生成" + ("（质量改进）" if retrying else ""),
                             f"综合4位专家建议，生成 {len(plan.get('daily_schedule', []))} 天行程，引用 {len(references)} 条知识库资料"
                             + (f"（{VARIANT_LABELS.get(variant, '')}）" if variant else "")
                             + (f"。按反馈改进：{quality_feedback[:60]}" if retrying else "")),
    }


# ---------- 节点 6：行程冲突检测 ----------
def validate_node(state: AgentState) -> AgentState:
    """校验行程合理性：跨区奔波/雨天户外/预算偏差等"""
    warnings = plan_validator.check_plan_conflicts(
        plan=state["plan"],
        knowledge=state["knowledge"],
        weather=state["weather"],
    )
    detail = f"校验完成，发现 {len(warnings)} 个需要关注的问题" if warnings else "行程校验通过，无冲突问题"
    return {
        **state,
        "plan_warnings": warnings,
        "trace": _add_trace(state, "行程校验", detail),
    }


# ---------- 节点 7：方案质量评估（低分自动重生成） ----------
def quality_node(state: AgentState) -> AgentState:
    """规则+LLM 双引擎评估方案质量；低分（<70）且未重试时携带反馈重新生成"""
    report = quality_service.evaluate(
        plan=state["plan"],
        knowledge=state["knowledge"],
        structured=state["structured"],
        plan_warnings=state["plan_warnings"],
    )
    retry_count = state.get("retry_count", 0)
    feedback = ""
    if report["overall_score"] < 70 and retry_count < 1:
        feedback = "；".join(report["suggestions"]) or "方案质量不达标，请改进后再生成"

    detail = f"{report['level']}（{report['overall_score']}分）"
    if report["suggestions"]:
        detail += "，改进项：" + "；".join(report["suggestions"][:2])
    if feedback:
        detail += "。质量不达标，将带反馈重新生成"
    return {
        **state,
        "quality_report": report,
        "quality_feedback": feedback,
        "retry_count": retry_count + 1 if feedback else retry_count,
        "trace": _add_trace(state, "质量评估", detail),
    }


def quality_route(state: AgentState) -> str:
    """条件路由：有质量反馈则回 plan 节点重生成，否则结束"""
    if state.get("quality_feedback"):
        return "retry"
    return "end"


# ---------- 工作流构建 ----------
def build_graph():
    """构建 LangGraph 有向图：analyze → retrieve → weather → specialists → plan → validate → quality → (条件) plan/END"""
    graph = StateGraph(AgentState)
    graph.add_node("analyze", analyze_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("weather", weather_node)
    graph.add_node("specialists", specialists_node)
    graph.add_node("plan", plan_node)
    graph.add_node("validate", validate_node)
    graph.add_node("quality", quality_node)
    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "retrieve")
    graph.add_edge("retrieve", "weather")
    graph.add_edge("weather", "specialists")
    graph.add_edge("specialists", "plan")
    graph.add_edge("plan", "validate")
    graph.add_edge("validate", "quality")
    # 低分 → 带反馈回 plan 重生成；达标 → 结束
    graph.add_conditional_edges("quality", quality_route, {"retry": "plan", "end": END})
    return graph.compile()


def run_agent(requirement_text: str = "", fields: dict | None = None, variant: str = "") -> dict:
    """运行完整 Agent 工作流

    参数：
    - requirement_text: 用户自然语言需求（可选）
    - fields: 结构化字段（可选，destination 必填其一）
    - variant: 方案变体（""默认 / budget性价比 / comfort舒适），舒适版预算自动上浮 50%

    返回：完整状态（含 structured / knowledge / weather / specialist_results / plan / references / plan_warnings / trace）
    """
    graph = build_graph()
    initial: AgentState = {
        "requirement_text": requirement_text,
        "structured": dict(fields or {}),
        "knowledge": {},
        "weather": {},
        "specialist_results": {},
        "plan": None,
        "references": [],
        "plan_warnings": [],
        "trace": [],
        "variant": variant,
        "quality_report": {},
        "quality_feedback": "",
        "retry_count": 0,
    }
    return graph.invoke(initial)


def run_agent_variants(requirement_text: str = "", fields: dict | None = None) -> dict:
    """并行生成两套对比方案（性价比版 / 舒适版）

    返回：{"budget": 性价比版完整状态, "comfort": 舒适版完整状态}
    """
    def _run(variant: str) -> dict:
        return run_agent(requirement_text, fields, variant=variant)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_budget = pool.submit(_run, "budget")
        f_comfort = pool.submit(_run, "comfort")
        return {
            "budget": f_budget.result(),
            "comfort": f_comfort.result(),
        }
