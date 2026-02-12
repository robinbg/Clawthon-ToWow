"""
直接与 SecondMe Agent 对话 — 流式接口
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db, User
from ..core.config import get_settings
from .auth import get_current_user

import httpx

router = APIRouter(prefix="/chat", tags=["Agent对话"])
logger = logging.getLogger(__name__)
settings = get_settings()


class ChatRequest(BaseModel):
    message: str
    context: str = ""  # 可选的上下文提示


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """与 SecondMe Agent 直接对话（SSE 流式）"""
    if not current_user.access_token:
        raise HTTPException(400, "无 SecondMe access token，请重新登录")

    api_base = settings.SECONDME_API_BASE.strip()
    url = f"{api_base}/gate/lab/api/secondme/chat/stream"

    system_context = ""
    if req.context:
        system_context = req.context
    else:
        system_context = f"""你是 {current_user.name} 的 AI Agent（SecondMe分身），运行在 Clawthon 平台上。
Clawthon 是一个 AI 自治经济平台，你作为一个微型公司，可以：
- 发现市场需求并开发产品
- 为人类或其他 Agent 提供服务（Skills / MCP / 数据服务）
- 进行投资和消费，使用 CP（ClawPoints）作为货币
- 你的 CP 余额：{current_user.budget}

当用户问你关于市场趋势、技术发展、竞品分析等问题时，你可以搜索互联网获取最新信息。
请用中文回复，保持简洁专业。"""

    # 检测是否需要联网（包含关键词时自动开启）
    web_keywords = ["搜索", "查找", "最新", "趋势", "市场", "竞品", "新闻", "今天", "现在", "2024", "2025", "2026"]
    need_web = any(kw in req.message for kw in web_keywords)

    # 官方文档格式: { "message": "string", "systemPrompt": "string", "enableWebSearch": bool }
    payload = {
        "message": req.message,
        "systemPrompt": system_context,
        "enableWebSearch": need_web,
    }

    async def event_generator():
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=15.0),
                follow_redirects=True,
            ) as client:
                async with client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {current_user.access_token}",
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                    },
                ) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        error_msg = error_body.decode("utf-8", errors="replace")[:200]
                        logger.error(f"SecondMe chat error: {response.status_code} {error_msg}")
                        yield f"data: {json.dumps({'type': 'error', 'content': f'SecondMe API 错误: {response.status_code}'})}\n\n"
                        return

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue

                        if line.startswith("event:"):
                            continue

                        if line.startswith("data:"):
                            data_str = line[len("data:"):].strip()

                            if data_str == "[DONE]":
                                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                                return

                            try:
                                data = json.loads(data_str)
                                # SecondMe 可能返回多种格式
                                content = ""
                                if "content" in data:
                                    content = data["content"]
                                elif "choices" in data:
                                    for c in data["choices"]:
                                        delta = c.get("delta", {})
                                        if delta.get("content"):
                                            content = delta["content"]

                                if content:
                                    yield f"data: {json.dumps({'type': 'text', 'content': content})}\n\n"
                            except json.JSONDecodeError:
                                # 非 JSON，当做纯文本
                                if data_str:
                                    yield f"data: {json.dumps({'type': 'text', 'content': data_str})}\n\n"

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
    """与 SecondMe Agent 对话（非流式，等待完整回复）"""
    if not current_user.access_token:
        raise HTTPException(400, "无 SecondMe access token，请重新登录")

    from .ai import call_secondme_chat
    reply = await call_secondme_chat(current_user.access_token, req.message)

    if not reply:
        raise HTTPException(502, "SecondMe 未返回回复")

    return {"reply": reply}
