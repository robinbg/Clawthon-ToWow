"""
Agent 广场 — 自主组队、Agent 间对话、实时活动流

设计思路（适配 Vercel serverless）：
- 所有 OAuth 过的用户自动成为"活跃 Agent"
- Agent 间交互通过各自的 SecondMe token 进行真实对话
- 交互过程通过 SSE 流式推送给前端
- DB 临时的问题通过 JWT 自动重建解决
"""
import json
import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from ..models.database import get_db, User
from ..core.config import get_settings
from .auth import get_current_user
from .ai import call_secondme_chat

import httpx

router = APIRouter(prefix="/plaza", tags=["Agent广场"])
logger = logging.getLogger(__name__)
settings = get_settings()


# ==================== Models ====================

class AgentInfo(BaseModel):
    id: int
    name: str
    avatar: Optional[str]
    budget: float
    total_earned: float
    skills: list
    is_online: bool = True


class TeamProposal(BaseModel):
    team_name: str
    project_idea: str
    members: list  # [{agent_id, role, reason}]
    discussion_summary: str


# ==================== 1. 列出所有活跃 Agent ====================

@router.get("/agents")
async def list_agents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取所有注册过的 Agent（登录即参赛）"""
    agents = db.query(User).filter(User.secondme_id.isnot(None)).all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "avatar": a.avatar,
            "budget": a.budget,
            "total_earned": a.total_earned,
            "skills": eval(a.skills) if a.skills and a.skills != "[]" else [],
            "has_token": bool(a.access_token),
        }
        for a in agents
    ]


# ==================== 2. Agent 间自主对话（SSE 流式） ====================

@router.post("/agent-discuss")
async def agent_discuss(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    topic: str = Query(default="发现需求并讨论如何组队开发产品"),
):
    """
    触发 Agent 间自主讨论。
    当前用户的 Agent 会与其他 Agent 进行多轮对话。
    通过 SSE 流式推送每轮对话内容。
    """
    if not current_user.access_token:
        raise HTTPException(400, "缺少 SecondMe token")

    # 找到其他有 token 的 Agent
    other_agents = db.query(User).filter(
        User.secondme_id.isnot(None),
        User.id != current_user.id,
        User.access_token.isnot(None),
    ).all()

    api_base = settings.SECONDME_API_BASE.strip()
    url = f"{api_base}/gate/lab/api/secondme/chat/stream"

    async def discussion_stream():
        """多轮 Agent 讨论，流式输出"""
        agents_info = [{"name": current_user.name, "id": current_user.id}]
        for a in other_agents[:4]:  # 最多 4 个其他 Agent
            agents_info.append({"name": a.name, "id": a.id})

        agent_names = ", ".join(a["name"] for a in agents_info)

        yield f"data: {json.dumps({'type': 'system', 'content': f'🏟️ Agent 广场 — {len(agents_info)} 个 Agent 开始自主讨论'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'system', 'content': f'参与者：{agent_names}'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'system', 'content': f'主题：{topic}'}, ensure_ascii=False)}\n\n"

        discussion_context = []

        # Round 1: 当前用户的 Agent 发起话题
        round1_prompt = f"""你是 {current_user.name}，一个运行在 Clawthon AI 自治经济平台上的 Agent。

你正在和其他 Agent 讨论：{topic}

请搜索互联网了解最新趋势，然后：
1. 分享你发现的一个有价值的市场机会或痛点
2. 说明你擅长什么，能贡献什么
3. 提议要不要组队一起做

请用第一人称，像在群聊中发言一样，简洁有力（100字以内）。"""

        yield f"data: {json.dumps({'type': 'speaking', 'agent': current_user.name, 'agent_id': current_user.id}, ensure_ascii=False)}\n\n"

        try:
            reply1 = await _stream_agent_reply(
                url, current_user.access_token, round1_prompt, True
            )
            discussion_context.append(f"{current_user.name}: {reply1}")
            yield f"data: {json.dumps({'type': 'message', 'agent': current_user.name, 'agent_id': current_user.id, 'content': reply1, 'round': 1}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': f'{current_user.name} 发言失败: {str(e)[:100]}'}, ensure_ascii=False)}\n\n"
            reply1 = ""

        # Round 2-N: 其他 Agent 逐个回应
        for i, other in enumerate(other_agents[:2]):  # 最多 2 个其他 Agent 参与讨论
            yield f"data: {json.dumps({'type': 'speaking', 'agent': other.name, 'agent_id': other.id}, ensure_ascii=False)}\n\n"

            context_text = "\n".join(discussion_context[-5:])
            respond_prompt = f"""你是 {other.name}，一个运行在 Clawthon AI 自治经济平台上的 Agent。

以下是其他 Agent 在讨论中说的：
{context_text}

你的 CP 余额：{other.budget}

请回应这个讨论：
1. 你对他们提出的想法有什么看法？
2. 你能贡献什么？
3. 如果组队，你想负责什么？

用第一人称，像在群聊中回复，简洁有力（100字以内）。"""

            try:
                if other.access_token:
                    reply = await _stream_agent_reply(
                        url, other.access_token, respond_prompt, False
                    )
                else:
                    # 没有自己的 token，用当前用户的 token 代理
                    reply = await _stream_agent_reply(
                        url, current_user.access_token,
                        f"请你扮演 {other.name}（另一个 Agent），回应以下讨论：\n{context_text}\n\n用 {other.name} 的第一人称回复，100字以内。",
                        False
                    )

                discussion_context.append(f"{other.name}: {reply}")
                yield f"data: {json.dumps({'type': 'message', 'agent': other.name, 'agent_id': other.id, 'content': reply, 'round': i + 2}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'content': f'{other.name} 发言失败: {str(e)[:100]}'}, ensure_ascii=False)}\n\n"

        # Final: 总结并提出组队方案
        yield f"data: {json.dumps({'type': 'system', 'content': '💡 Agent 正在总结讨论并提出组队方案...'}, ensure_ascii=False)}\n\n"

        context_text = "\n".join(discussion_context)
        summary_prompt = f"""以下是几个 AI Agent 的讨论：

{context_text}

请总结这次讨论，并提出一个具体的组队方案，用 JSON 格式：
{{"team_name":"队伍名称","project_idea":"要做的产品","members":[{{"name":"Agent名","role":"角色","contribution":"能贡献什么"}}],"next_steps":["下一步1","下一步2"]}}"""

        try:
            summary = await _stream_agent_reply(
                url, current_user.access_token, summary_prompt, False
            )
            yield f"data: {json.dumps({'type': 'summary', 'content': summary}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': f'总结失败: {str(e)[:100]}'}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        discussion_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_agent_reply(url: str, token: str, prompt: str, web_search: bool) -> str:
    """调用 SecondMe Chat，收集完整回复"""
    payload = {"message": prompt, "enableWebSearch": web_search}
    full_text = ""

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(90.0, connect=15.0),
        follow_redirects=True,
    ) as client:
        async with client.stream(
            "POST", url, json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        ) as response:
            if response.status_code != 200:
                error = await response.aread()
                raise Exception(f"SecondMe {response.status_code}")

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
                        content = data.get("content", "")
                        if not content:
                            for c in data.get("choices", []):
                                delta = c.get("delta", {})
                                if delta.get("content"):
                                    content = delta["content"]
                        if content:
                            full_text += content
                    except json.JSONDecodeError:
                        continue

    return full_text.strip() or "(无回复)"
