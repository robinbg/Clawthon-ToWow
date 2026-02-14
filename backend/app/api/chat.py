"""
直接与 OpenClaw Agent 对话 — 流式接口

通过 OpenClaw Gateway 实现 Agent 对话，支持：
- 流式 SSE 返回
- 非流式完整回复
- 自动联网搜索
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db, User
from ..core.config import get_settings
from ..core.openclaw import chat as openclaw_chat, chat_stream as openclaw_chat_stream
from .auth import get_current_user

router = APIRouter(prefix="/chat", tags=["Agent对话"])
logger = logging.getLogger(__name__)
settings = get_settings()


class ChatRequest(BaseModel):
    message: str
    context: str = ""  # 可选的上下文提示


@router.post("/stream")
async def chat_stream_endpoint(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """与 OpenClaw Agent 直接对话（SSE 流式）"""
    system_context = ""
    if req.context:
        system_context = req.context
    else:
        system_context = f"""你是 {current_user.name} 的 AI Agent（OpenClaw 驱动），运行在 Clawthon 平台上。
Clawthon 是一个基于 OpenClaw 的 AI 自治经济平台，你作为一个微型公司，可以：
- 发现市场需求并开发产品
- 为人类或其他 Agent 提供服务（OpenClaw Skills / MCP / 数据服务）
- 进行投资和消费，使用 CP（ClawPoints）作为货币
- 你的 CP 余额：{current_user.budget}

当用户问你关于市场趋势、技术发展、竞品分析等问题时，你可以搜索互联网获取最新信息。
请用中文回复，保持简洁专业。"""

    # 检测是否需要联网（包含关键词时自动开启）
    web_keywords = ["搜索", "查找", "最新", "趋势", "市场", "竞品", "新闻", "今天", "现在", "2024", "2025", "2026"]
    need_web = any(kw in req.message for kw in web_keywords)

    session_id = f"clawthon-chat-{current_user.id}"

    async def event_generator():
        try:
            async for chunk in openclaw_chat_stream(
                req.message,
                session_id=session_id,
                system_prompt=system_context,
                enable_web_search=need_web,
                agent_token=current_user.access_token or "",
            ):
                yield chunk
        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/send")
async def chat_send(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """与 OpenClaw Agent 对话（非流式，等待完整回复）"""
    try:
        reply = await openclaw_chat(
            req.message,
            session_id=f"clawthon-chat-{current_user.id}",
            agent_token=current_user.access_token or "",
        )
    except Exception as e:
        raise HTTPException(502, f"Agent 未返回回复: {str(e)[:200]}")

    if not reply:
        raise HTTPException(502, "Agent 未返回回复")

    return {"reply": reply}
