from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from app.core.config import get_settings
from app.models.database import init_db
from app.api import auth, projects, transactions, ai, agent_work

settings = get_settings()

# 创建FastAPI应用
app = FastAPI(
    title="Clawthon API",
    description="AI自治经济Hackathon平台 - 后端API",
    version="0.1.0"
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


@app.get("/")
async def root():
    return {
        "message": "Welcome to Clawthon API",
        "version": "0.1.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# 初始化数据库
@app.on_event("startup")
async def startup_event():
    init_db()
    print("✅ 数据库已初始化")


if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
