"""Agent 工作流调试接口：展示完整执行过程（知识库/天气/路线/方案）"""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import agent_service

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentRunRequest(BaseModel):
    """Agent 工作流运行请求"""

    requirement: str = Field("", description="用户自然语言需求")
    destination: str = Field("", description="目的地（可选）")
    days: int = Field(0, description="旅行天数（可选）")
    people: int = Field(0, description="出行人数（可选）")
    budget: int = Field(0, description="总预算（可选）")
    preferences: list[str] = Field([], description="兴趣偏好（可选）")


@router.post("/run")
def run_agent(req: AgentRunRequest):
    """运行完整 Agent 工作流并返回全过程（演示/调试用）

    返回：结构化需求、检索到的知识、天气、路线建议、方案、执行日志
    """
    fields = {
        "destination": req.destination,
        "days": req.days,
        "people": req.people,
        "budget": req.budget,
        "preferences": req.preferences,
    }
    provided = {k: v for k, v in fields.items() if v not in ("", 0, [])}

    result = agent_service.run_agent(
        requirement_text=req.requirement,
        fields=provided,
    )
    if not result["structured"].get("destination"):
        raise HTTPException(status_code=400, detail="请提供目的地或旅行需求描述")

    # 裁剪知识库输出（只保留名称与关键字段，避免响应过大）
    knowledge_summary = {
        "city_name": result["knowledge"].get("city_name", ""),
        "attractions": [{"id": a["id"], "name": a["name"]} for a in result["knowledge"]["attractions"]],
        "foods": [{"id": f["id"], "name": f["name"]} for f in result["knowledge"]["foods"]],
        "hotels": [{"id": h["id"], "name": h["name"]} for h in result["knowledge"]["hotels"]],
    }
    return {
        "structured_requirement": result["structured"],
        "knowledge": knowledge_summary,
        "weather": result["weather"],
        "specialist_results": result["specialist_results"],
        "plan": result["plan"],
        "references": result["references"],
        "plan_warnings": result["plan_warnings"],
        "agent_trace": result["trace"],
    }
