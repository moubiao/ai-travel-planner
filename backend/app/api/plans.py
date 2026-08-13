"""旅行方案相关接口：方案生成（Agent工作流）/ 方案调整"""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import agent_service, llm_service, prompt_templates

router = APIRouter(prefix="/api/plans", tags=["plans"])


class GeneratePlanRequest(BaseModel):
    """方案生成请求：支持自然语言描述，也支持结构化字段（结构化字段优先）"""

    requirement: str = Field("", description="用户自然语言需求描述，如「成都3天2夜，两个人，预算4000，喜欢美食」")
    destination: str = Field("", description="目的地（可选）")
    start_date: str = Field("", description="出发日期 YYYY-MM-DD（可选）")
    days: int = Field(0, description="旅行天数（可选）")
    people: int = Field(0, description="出行人数（可选）")
    budget: int = Field(0, description="总预算，元（可选）")
    preferences: list[str] = Field([], description="兴趣偏好数组（可选）")
    special_requirements: str = Field("", description="特殊需求（可选）")
    variants: bool = Field(False, description="是否生成两套对比方案（性价比版 vs 舒适版，并行生成）")
    pace: str = Field("standard", description="行程节奏：fast=特种兵 / standard=标准 / slow=慢游")


class AdjustPlanRequest(BaseModel):
    """方案调整请求：用户对话式修改已有方案"""

    plan: dict = Field(..., description="当前方案 JSON")
    instruction: str = Field(..., description="用户修改要求，如「预算减少500元」「不要寺庙，多安排购物」")


def _parse_json(text: str, error_hint: str) -> dict:
    """解析 LLM 输出的 JSON，失败时抛出 502"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail=error_hint)


@router.post("/generate")
def generate_plan(req: GeneratePlanRequest):
    """根据用户需求生成旅行方案（LangGraph Agent 工作流）

    流程：需求分析 → 知识检索(RAG) → 天气查询 → 路线优化 → 方案生成
    """
    # 1. 收集显式提供的结构化字段（0 / 空串 / 空数组 视为未提供）
    fields = {
        "destination": req.destination,
        "start_date": req.start_date,
        "days": req.days,
        "people": req.people,
        "budget": req.budget,
        "preferences": req.preferences,
        "special_requirements": req.special_requirements,
        "pace": req.pace,
    }
    provided = {k: v for k, v in fields.items() if v not in ("", 0, [])}

    # 2. 运行 Agent 工作流（需求分析节点会解析自然语言补全缺失字段）
    if req.variants:
        # 对比模式：并行生成性价比版 + 舒适版
        results = agent_service.run_agent_variants(
            requirement_text=req.requirement,
            fields=provided,
        )
        structured = results["budget"]["structured"]
        if not structured.get("destination"):
            raise HTTPException(status_code=400, detail="请提供目的地或旅行需求描述，例如「成都3天2夜」")
        return {
            "structured_requirement": structured,
            "variants": {
                "budget": _variant_payload(results["budget"], "性价比版"),
                "comfort": _variant_payload(results["comfort"], "舒适版"),
            },
        }

    result = agent_service.run_agent(
        requirement_text=req.requirement,
        fields=provided,
    )

    # 3. 目的地必须存在
    structured = result["structured"]
    if not structured.get("destination"):
        raise HTTPException(status_code=400, detail="请提供目的地或旅行需求描述，例如「成都3天2夜」")

    # 4. 返回方案 + Agent 执行过程 + 行程校验结果 + 质量评估
    return {
        "structured_requirement": structured,
        "plan": result["plan"],
        "references": result["references"],
        "agent_trace": result["trace"],
        "weather": result["weather"],
        "plan_warnings": result["plan_warnings"],
        "quality_report": result["quality_report"],
    }


def _variant_payload(result: dict, label: str) -> dict:
    """将单个变体结果整理为前端展示负载"""
    return {
        "label": label,
        "plan": result["plan"],
        "references": result["references"],
        "agent_trace": result["trace"],
        "weather": result["weather"],
        "plan_warnings": result["plan_warnings"],
        "quality_report": result["quality_report"],
    }


@router.post("/adjust")
def adjust_plan(req: AdjustPlanRequest):
    """对话式调整已有方案（如「预算减少500元」）"""
    messages = [
        {"role": "system", "content": prompt_templates.SYSTEM_PROMPT},
        {"role": "user", "content": prompt_templates.ADJUST_PROMPT.format(
            plan_json=json.dumps(req.plan, ensure_ascii=False, indent=2),
            instruction=req.instruction,
        )},
    ]
    raw = llm_service.chat_json(messages, temperature=0.4)
    plan = _parse_json(raw, "方案调整失败，请重试")
    return {"plan": plan}
