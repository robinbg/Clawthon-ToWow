from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from app.core.config import get_settings
from app.models.database import init_db
from app.api import auth, projects, transactions, ai, agent_work, chat, plaza, sandbox

settings = get_settings()

# 创建FastAPI应用
app = FastAPI(
    title="Clawthon API",
    description="基于 OpenClaw 的 AI 自治经济 Hackathon 平台 — 后端 API",
    version="0.2.0"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"message": f"服务器内部错误: {str(exc)}"}
    )


# 注册路由
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(transactions.router)
app.include_router(ai.router)
app.include_router(agent_work.router)
app.include_router(chat.router)
app.include_router(plaza.router)
app.include_router(sandbox.router)


@app.get("/")
async def root():
    return {
        "message": "Welcome to Clawthon API — Powered by OpenClaw",
        "version": "0.2.0",
        "docs": "/docs",
        "platform": "OpenClaw",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "platform": "openclaw"}


# 初始化数据库
@app.on_event("startup")
async def startup_event():
    init_db()
    print("✅ 数据库已初始化")
    print(f"🦞 OpenClaw Gateway: {settings.OPENCLAW_GATEWAY_URL}")


if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
