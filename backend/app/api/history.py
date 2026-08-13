"""历史方案接口：保存 / 列表 / 详情 / 删除（需登录）"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import database
from app.api.auth import get_current_user

router = APIRouter(prefix="/api/history", tags=["history"])


class SavePlanRequest(BaseModel):
    """保存方案请求"""

    title: str = Field(..., min_length=1, max_length=50, description="方案标题")
    requirement: dict | None = Field(None, description="结构化旅行需求")
    plan: dict = Field(..., description="旅行方案")
    references: list | None = Field(None, description="知识库引用")


@router.post("/save")
def save_plan(req: SavePlanRequest, user: dict = Depends(get_current_user)):
    """保存当前方案到历史记录"""
    plan_id = database.save_plan(
        user_id=user["id"],
        title=req.title.strip(),
        requirement=req.requirement,
        plan=req.plan,
        references=req.references,
    )
    return {"plan_id": plan_id, "message": "方案已保存"}


@router.get("/list")
def list_plans(user: dict = Depends(get_current_user)):
    """我的历史方案列表"""
    plans = database.list_plans(user["id"])
    return {"total": len(plans), "plans": plans}


@router.get("/{plan_id}")
def get_plan(plan_id: int, user: dict = Depends(get_current_user)):
    """方案详情"""
    plan = database.get_plan(plan_id, user["id"])
    if not plan:
        raise HTTPException(status_code=404, detail="方案不存在")
    return plan


@router.delete("/{plan_id}")
def delete_plan(plan_id: int, user: dict = Depends(get_current_user)):
    """删除方案"""
    if not database.delete_plan(plan_id, user["id"]):
        raise HTTPException(status_code=404, detail="方案不存在")
    return {"message": "已删除"}
