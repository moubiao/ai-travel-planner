"""用户认证接口：注册 / 登录（JWT 令牌）"""
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app import database

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


class RegisterRequest(BaseModel):
    """注册请求"""

    username: str = Field(..., min_length=2, max_length=20, description="用户名")
    password: str = Field(..., min_length=6, max_length=64, description="密码（至少6位）")


class LoginRequest(BaseModel):
    """登录请求"""

    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
    """FastAPI 依赖：解析 JWT 获取当前用户，未认证返回 401"""
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = database.decode_token(credentials.credentials)
        user = database.get_user_by_id(int(payload["sub"]))
        if not user:
            raise ValueError("用户不存在")
        return dict(user)
    except Exception:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")


@router.post("/register")
def register(req: RegisterRequest):
    """注册新用户，成功即返回令牌"""
    if not re.match(r"^[a-zA-Z0-9_\u4e00-\u9fa5]+$", req.username):
        raise HTTPException(status_code=400, detail="用户名只能包含字母、数字、下划线或中文")
    try:
        user = database.create_user(req.username.strip(), req.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    token = database.create_token(user["id"], user["username"])
    return {"token": token, "username": user["username"]}


@router.post("/login")
def login(req: LoginRequest):
    """登录，返回 JWT 令牌"""
    user = database.get_user_by_username(req.username.strip())
    if not user or not database.verify_password(req.password, user["password_hash"], user["salt"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = database.create_token(user["id"], user["username"])
    return {"token": token, "username": user["username"]}
