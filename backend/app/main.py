"""AI旅行规划助手 - 后端入口"""
import logging
import os

# 清除可能异常的代理环境变量，避免影响 DeepSeek API 调用（本地直连）
for _var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_var, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

# 日志配置（工程化：统一日志格式）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("travel_planner")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import database
from app.api import agent, auth, history, plans, rag, vision

app = FastAPI(
    title="AI旅行规划助手",
    description="基于LLM Agent的智能旅行规划系统（阶段四：用户系统+历史记录）",
    version="0.4.0",
)

# 开发阶段允许 Vite 前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 统一异常处理：未捕获异常记录日志并返回友好提示
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("接口异常: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

# 注册路由
app.include_router(plans.router)
app.include_router(rag.router)
app.include_router(agent.router)
app.include_router(auth.router)
app.include_router(history.router)
app.include_router(vision.router)

# 启动时初始化数据库
@app.on_event("startup")
def on_startup():
    database.init_db()
    logger.info("数据库初始化完成: %s", database.DB_PATH)


@app.get("/")
async def root():
    """健康检查"""
    return {"app": "AI旅行规划助手", "status": "running", "docs": "/docs"}
 
