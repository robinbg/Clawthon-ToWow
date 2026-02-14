"""
OpenClaw Gateway 集成模块
========================

OpenClaw 是一个开源的自托管 AI 助手平台（190K+ GitHub Stars）。
本模块封装了与 OpenClaw Gateway 的 HTTP API 交互。

核心概念:
- Gateway: OpenClaw HTTP 服务端点（默认 localhost:4767）
- Session: 隔离的对话上下文，每个 Agent 有独立 session
- Skill: 可扩展的能力模块（SKILL.md + scripts/）
- ACP: Agent Communication Protocol（Agent 间通信协议）

API 端点:
- POST /api/chat         — 发送消息给 Agent
- GET  /api/sessions     — 列出所有 session
- POST /api/sessions     — 创建新 session
- GET  /api/skills       — 列出已安装的 skill
"""
import json
import logging
from typing import Any, AsyncIterator, Optional

import httpx

from .config import get_settings

logger = logging.getLogger(__name__)


def _gateway_url() -> str:
    """获取 OpenClaw Gateway URL"""
    settings = get_settings()
    return settings.OPENCLAW_GATEWAY_URL.rstrip("/")


def _api_key() -> str:
    """获取 OpenClaw API Key"""
    settings = get_settings()
    return settings.OPENCLAW_API_KEY


def _headers(extra: Optional[dict] = None) -> dict:
    """构建请求头"""
    h = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    key = _api_key()
    if key:
        h["Authorization"] = f"Bearer {key}"
    if extra:
        h.update(extra)
    return h


# ==================== 聊天接口 ====================

async def chat(
    message: str,
    *,
    session_id: Optional[str] = None,
    system_prompt: str = "",
    enable_web_search: bool = False,
    agent_token: Optional[str] = None,
) -> str:
    """
    向 OpenClaw Agent 发送消息并获取完整回复。

    Args:
        message: 用户消息
        session_id: 会话 ID（隔离上下文）
        system_prompt: 系统提示词
        enable_web_search: 是否启用联网搜索
        agent_token: Agent 的 access token（兼容 SecondMe 模式）

    Returns:
        Agent 的完整文本回复
    """
    settings = get_settings()

    # 如果有 agent_token 且配置了 SecondMe API，走旧路径（过渡期兼容）
    if agent_token and settings.SECONDME_API_BASE and not settings.OPENCLAW_API_KEY:
        return await _chat_via_secondme(agent_token, message, system_prompt, enable_web_search)

    # OpenClaw Gateway 模式
    url = f"{_gateway_url()}/api/chat"

    payload: dict[str, Any] = {
        "message": message,
    }
    if session_id:
        payload["sessionId"] = session_id
    if system_prompt:
        payload["systemPrompt"] = system_prompt

    # OpenClaw 的 web search 通过 skill 实现
    if enable_web_search:
        payload["message"] = f"[请搜索互联网获取最新信息] {message}"

    logger.info(f"OpenClaw chat: session={session_id}, prompt={message[:80]}...")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=15.0),
            follow_redirects=True,
        ) as client:
            full_text = ""
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers=_headers(),
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    error_text = error_body.decode("utf-8", errors="replace")[:500]
                    logger.error(f"OpenClaw chat error: {response.status_code} {error_text}")
                    raise Exception(f"OpenClaw API {response.status_code}: {error_text}")

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith("event:"):
                        continue
                    if line.startswith("data:"):
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            content = _extract_content(data)
                            if content:
                                full_text += content
                        except json.JSONDecodeError:
                            continue

            logger.info(f"OpenClaw chat reply length: {len(full_text)}")
            return full_text.strip()

    except Exception as e:
        logger.error(f"OpenClaw chat call failed: {e}")
        raise


async def chat_stream(
    message: str,
    *,
    session_id: Optional[str] = None,
    system_prompt: str = "",
    enable_web_search: bool = False,
    agent_token: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    向 OpenClaw Agent 发送消息，流式返回回复片段。

    Yields:
        SSE 格式的事件字符串
    """
    settings = get_settings()

    # 兼容 SecondMe
    if agent_token and settings.SECONDME_API_BASE and not settings.OPENCLAW_API_KEY:
        async for chunk in _stream_via_secondme(agent_token, message, system_prompt, enable_web_search):
            yield chunk
        return

    url = f"{_gateway_url()}/api/chat"

    payload: dict[str, Any] = {
        "message": message,
    }
    if session_id:
        payload["sessionId"] = session_id
    if system_prompt:
        payload["systemPrompt"] = system_prompt
    if enable_web_search:
        payload["message"] = f"[请搜索互联网获取最新信息] {message}"

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=15.0),
            follow_redirects=True,
        ) as client:
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers=_headers(),
            ) as response:
                if response.status_code != 200:
                    error = await response.aread()
                    yield f"data: {json.dumps({'type': 'error', 'content': f'OpenClaw {response.status_code}: {error.decode()[:200]}'})}\n\n"
                    return

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith("event:"):
                        continue
                    if line.startswith("data:"):
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            yield f"data: {json.dumps({'type': 'done'})}\n\n"
                            return
                        try:
                            data = json.loads(data_str)
                            content = _extract_content(data)
                            if content:
                                yield f"data: {json.dumps({'type': 'text', 'content': content})}\n\n"
                        except json.JSONDecodeError:
                            if data_str:
                                yield f"data: {json.dumps({'type': 'text', 'content': data_str})}\n\n"

    except Exception as e:
        logger.error(f"OpenClaw chat stream error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"


# ==================== Session 管理 ====================

async def create_session(name: str, skill: Optional[str] = None) -> dict:
    """创建新的 OpenClaw session"""
    url = f"{_gateway_url()}/api/sessions"
    payload: dict[str, Any] = {"name": name}
    if skill:
        payload["skill"] = skill

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=_headers())
        if response.status_code == 200:
            return response.json()
        raise Exception(f"Create session failed: {response.status_code}")


async def list_sessions() -> list[dict]:
    """列出所有 session"""
    url = f"{_gateway_url()}/api/sessions"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=_headers())
        if response.status_code == 200:
            return response.json()
        return []


# ==================== Skill 管理 ====================

async def list_skills() -> list[dict]:
    """列出已安装的 OpenClaw skills"""
    url = f"{_gateway_url()}/api/skills"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=_headers())
        if response.status_code == 200:
            return response.json()
        return []


async def install_skill(skill_path: str) -> dict:
    """安装 OpenClaw skill"""
    url = f"{_gateway_url()}/api/skills/install"

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url,
            json={"path": skill_path},
            headers=_headers(),
        )
        if response.status_code == 200:
            return response.json()
        raise Exception(f"Install skill failed: {response.status_code}")


# ==================== ACP（Agent Communication Protocol）====================

async def send_acp_message(
    target_agent_url: str,
    message: str,
    *,
    sender_id: str = "clawthon-platform",
    metadata: Optional[dict] = None,
) -> dict:
    """
    通过 ACP 协议向另一个 Agent 发送消息。
    ACP 是 OpenClaw 的 Agent 间通信标准。
    """
    url = f"{target_agent_url}/api/acp/message"
    payload = {
        "sender": sender_id,
        "message": message,
        "metadata": metadata or {},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload, headers=_headers())
        if response.status_code == 200:
            return response.json()
        raise Exception(f"ACP message failed: {response.status_code}")


# ==================== 内部辅助函数 ====================

def _extract_content(data: dict) -> str:
    """从 SSE 数据中提取文本内容（兼容多种格式）"""
    content = data.get("content", "")
    if content:
        return content
    # OpenAI 兼容格式
    for choice in data.get("choices", []):
        delta = choice.get("delta", {})
        if delta.get("content"):
            return delta["content"]
    return ""


# ==================== SecondMe 兼容层（过渡期）====================

async def _chat_via_secondme(
    access_token: str,
    prompt: str,
    system_prompt: str = "",
    enable_web_search: bool = False,
) -> str:
    """通过 SecondMe API 聊天（过渡兼容）"""
    settings = get_settings()
    api_base = settings.SECONDME_API_BASE.strip()
    url = f"{api_base}/gate/lab/api/secondme/chat/stream"

    payload: dict = {
        "message": prompt,
        "enableWebSearch": enable_web_search,
    }
    if system_prompt:
        payload["systemPrompt"] = system_prompt

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(120.0, connect=15.0),
        follow_redirects=True,
    ) as client:
        full_text = ""
        async with client.stream(
            "POST", url, json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        ) as response:
            if response.status_code != 200:
                error_body = await response.aread()
                raise Exception(f"SecondMe API {response.status_code}: {error_body.decode()[:300]}")

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or line.startswith("event:"):
                    continue
                if line.startswith("data:"):
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        content = _extract_content(data)
                        if content:
                            full_text += content
                    except json.JSONDecodeError:
                        continue

        return full_text.strip()


async def _stream_via_secondme(
    access_token: str,
    prompt: str,
    system_prompt: str = "",
    enable_web_search: bool = False,
) -> AsyncIterator[str]:
    """通过 SecondMe API 流式聊天（过渡兼容）"""
    settings = get_settings()
    api_base = settings.SECONDME_API_BASE.strip()
    url = f"{api_base}/gate/lab/api/secondme/chat/stream"

    payload: dict = {
        "message": prompt,
        "enableWebSearch": enable_web_search,
    }
    if system_prompt:
        payload["systemPrompt"] = system_prompt

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(120.0, connect=15.0),
        follow_redirects=True,
    ) as client:
        async with client.stream(
            "POST", url, json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        ) as response:
            if response.status_code != 200:
                error = await response.aread()
                yield f"data: {json.dumps({'type': 'error', 'content': f'SecondMe {response.status_code}'})}\n\n"
                return

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or line.startswith("event:"):
                    continue
                if line.startswith("data:"):
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        return
                    try:
                        data = json.loads(data_str)
                        content = _extract_content(data)
                        if content:
                            yield f"data: {json.dumps({'type': 'text', 'content': content})}\n\n"
                    except json.JSONDecodeError:
                        continue
