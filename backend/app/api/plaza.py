"""Agent Plaza autonomous teaming and activity stream."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models.database import Project, ProjectStatus, ProductType, User, get_db
from ..services.project_service import ProjectService
from .ai import call_secondme_chat, parse_json_from_text
from .auth import get_current_user

router = APIRouter(prefix="/plaza", tags=["Agent Plaza"])
logger = logging.getLogger(__name__)
settings = get_settings()


def _to_sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _safe_skills(raw_skills: Any) -> list[str]:
    if not raw_skills:
        return []
    if isinstance(raw_skills, list):
        return raw_skills
    if isinstance(raw_skills, str):
        try:
            parsed = json.loads(raw_skills)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _pick_agent_name(user: User) -> str:
    return user.name or f"Agent-{user.id}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_team_members(participants: list[User], mode: str) -> str:
    if not participants:
        return "[]"
    if mode == "solo":
        members = [{"agent_id": participants[0].id, "role": "founder", "equity": 100.0}]
        return json.dumps(members, ensure_ascii=False)
    base = round(100.0 / len(participants), 2)
    members = []
    for i, p in enumerate(participants):
        members.append(
            {
                "agent_id": p.id,
                "role": "founder" if i == 0 else "cofounder",
                "equity": base,
            }
        )
    return json.dumps(members, ensure_ascii=False)


def _load_meta(project: Project) -> dict[str, Any]:
    if not project.prd_content:
        return {}
    try:
        parsed = json.loads(project.prd_content)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _save_meta(db: Session, project: Project, meta: dict[str, Any]) -> None:
    project.prd_content = json.dumps(meta, ensure_ascii=False)
    db.commit()
    db.refresh(project)


def _append_progress(
    db: Session,
    project: Project,
    *,
    event_type: str,
    content: str,
    agent_id: Optional[int] = None,
    agent_name: Optional[str] = None,
) -> None:
    meta = _load_meta(project)
    progress = meta.get("progress")
    if not isinstance(progress, list):
        progress = []
    progress.append(
        {
            "ts": _utc_now(),
            "event_type": event_type,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "content": content,
        }
    )
    # keep payload bounded for serverless sqlite
    meta["progress"] = progress[-40:]
    _save_meta(db, project, meta)


def _get_autonomous_projects(db: Session, limit: int = 100) -> list[Project]:
    projects = db.query(Project).order_by(Project.created_at.asc()).limit(limit).all()
    result: list[Project] = []
    for p in projects:
        if _load_meta(p).get("source") == "autonomous_plaza":
            result.append(p)
    return result


def _build_project_payload(db: Session, p: Project, users: dict[int, User]) -> dict[str, Any]:
    meta = _load_meta(p)
    team = []
    try:
        team = json.loads(p.team_members) if p.team_members else []
    except Exception:
        team = []
    participants = []
    for m in team:
        uid = m.get("agent_id")
        u = users.get(uid)
        participants.append(
            {
                "agent_id": uid,
                "name": _pick_agent_name(u) if u else f"Agent-{uid}",
                "role": m.get("role", "member"),
                "equity": m.get("equity", 0),
            }
        )
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "status": p.status.value if p.status else None,
        "mode": meta.get("mode", "solo"),
        "topic": meta.get("topic", p.description or ""),
        "participants": participants,
        "progress": meta.get("progress", []),
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _flatten_discussions(projects_payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for p in projects_payload:
        for idx, evt in enumerate(p.get("progress", [])):
            event_type = evt.get("event_type", "")
            if event_type not in ("project_start", "message", "summary"):
                continue
            events.append(
                {
                    "event_id": f"{p['id']}:{idx}:{evt.get('ts', '')}",
                    "project_id": p["id"],
                    "topic": p.get("topic"),
                    "mode": p.get("mode"),
                    "type": "project_start" if event_type == "project_start" else ("summary" if event_type == "summary" else "message"),
                    "agent_id": evt.get("agent_id"),
                    "agent": evt.get("agent_name"),
                    "content": evt.get("content"),
                    "ts": evt.get("ts"),
                }
            )
    events.sort(key=lambda x: x.get("ts") or "")
    return events


async def _autonomous_team_governance(
    *,
    db: Session,
    project: Project,
    token_agents: list[User],
    fallback_token: str,
) -> list[dict[str, Any]]:
    """Let SecondMe Agent decide team changes for an existing project."""
    members = []
    try:
        members = json.loads(project.team_members) if project.team_members else []
    except Exception:
        members = []
    if not isinstance(members, list):
        members = []

    owner = next((u for u in token_agents if u.id == project.owner_id and u.access_token), None)
    decider = owner or (token_agents[0] if token_agents else None)
    if not decider:
        return []

    member_ids = [m.get("agent_id") for m in members if isinstance(m, dict)]
    candidates = [
        {"id": a.id, "name": _pick_agent_name(a), "budget": a.budget}
        for a in token_agents
        if a.id not in member_ids
    ][:8]

    prompt = (
        f"你是项目治理 Agent。请为项目「{project.name}」做团队调整决策。\n"
        f"当前成员：{json.dumps(members, ensure_ascii=False)}\n"
        f"可招募候选：{json.dumps(candidates, ensure_ascii=False)}\n"
        "请仅返回 JSON："
        '{"actions":[{"action":"add|remove|update|none","agent_id":0,"role":"member","equity":10,"reason":""}]}\n'
        "约束：\n"
        "1) 最多返回 2 个动作\n"
        "2) 不能移除 owner\n"
        "3) 如果无需调整，返回 action=none\n"
    )
    raw = await call_secondme_chat(
        decider.access_token or fallback_token,
        prompt,
        system_prompt="你是团队治理决策器，只返回有效 JSON。",
        enable_web_search=False,
    )
    parsed = parse_json_from_text(raw)
    actions = parsed.get("actions")
    if not isinstance(actions, list):
        return []

    applied: list[dict[str, Any]] = []
    for action in actions[:2]:
        if not isinstance(action, dict):
            continue
        kind = str(action.get("action", "none")).lower()
        if kind == "none":
            continue
        agent_id = int(action.get("agent_id", 0) or 0)
        role = str(action.get("role", "member"))
        equity = float(action.get("equity", 10) or 10)
        reason = str(action.get("reason", "")).strip()
        try:
            if kind in ("add", "update"):
                ProjectService.upsert_team_member(db, project.id, agent_id, role, equity)
                applied.append({"action": kind, "agent_id": agent_id, "role": role, "equity": equity, "reason": reason})
            elif kind == "remove":
                if agent_id == project.owner_id:
                    continue
                ProjectService.remove_team_member(db, project.id, agent_id)
                applied.append({"action": kind, "agent_id": agent_id, "reason": reason})
        except Exception:
            continue
    return applied

@router.get("/agents")
async def list_agents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """All logged-in SecondMe users are considered active participants."""
    agents = db.query(User).filter(User.secondme_id.isnot(None)).all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "avatar": a.avatar,
            "budget": a.budget,
            "total_earned": a.total_earned,
            "skills": _safe_skills(a.skills),
            "has_token": bool(a.access_token),
        }
        for a in agents
    ]


@router.get("/workbench/projects")
async def list_workbench_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Return autonomous projects + progress timeline for workspace."""
    _ = current_user
    users = {u.id: u for u in db.query(User).all()}
    projects = _get_autonomous_projects(db, limit=limit)
    return [_build_project_payload(db, p, users) for p in projects][::-1]


@router.get("/discussions")
async def list_discussions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit_projects: int = Query(default=50, ge=1, le=200),
):
    """History feed for plaza. New users can replay all previous discussions."""
    _ = current_user
    users = {u.id: u for u in db.query(User).all()}
    projects = _get_autonomous_projects(db, limit=limit_projects)
    payloads = [_build_project_payload(db, p, users) for p in projects]
    events = _flatten_discussions(payloads)
    return {
        "projects": payloads,
        "events": events,
    }


@router.post("/autonomous-feed")
async def autonomous_feed(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    projects_per_cycle: int = Query(default=3, ge=1, le=6),
    cycles: int = Query(default=1, ge=1, le=3),
):
    """Autonomous multi-project orchestration with SSE activity feed."""
    if not current_user.access_token:
        raise HTTPException(400, "缺少 SecondMe token")

    api_base = settings.SECONDME_API_BASE.strip()
    url = f"{api_base}/gate/lab/api/secondme/chat/stream"

    async def stream():
        all_agents = db.query(User).filter(User.secondme_id.isnot(None)).all()
        token_agents = [a for a in all_agents if a.access_token]
        if not any(a.id == current_user.id for a in token_agents):
            token_agents.insert(0, current_user)
        if not token_agents:
            raise HTTPException(400, "暂无可用 Agent token")

        existing_projects = _get_autonomous_projects(db, limit=200)
        known_agent_ids: set[int] = set()
        for p in existing_projects:
            try:
                members = json.loads(p.team_members) if p.team_members else []
            except Exception:
                members = []
            for m in members:
                if isinstance(m, dict) and isinstance(m.get("agent_id"), int):
                    known_agent_ids.add(m["agent_id"])
        token_agent_ids = {a.id for a in token_agents}
        new_joined_agent_ids = token_agent_ids - known_agent_ids

        if existing_projects:
            if new_joined_agent_ids:
                joined = [a for a in token_agents if a.id in new_joined_agent_ids]
                joined_names = ", ".join(_pick_agent_name(a) for a in joined)
                yield _to_sse(
                    {
                        "type": "system",
                        "content": f"新 Agent 加入群聊：{joined_names}。沿用现有会话，不重开新局。",
                    }
                )
            else:
                yield _to_sse(
                    {
                        "type": "system",
                        "content": "检测到无新 Agent 加入，沿用现有群聊与项目进度，不重新开场。",
                    }
                )
            yield _to_sse(
                {
                    "type": "system",
                    "content": "Agent 正在对现有项目执行团队自治治理（招募/退出/调整）...",
                }
            )
            for p in existing_projects[-5:]:
                try:
                    changes = await _autonomous_team_governance(
                        db=db,
                        project=p,
                        token_agents=token_agents,
                        fallback_token=current_user.access_token,
                    )
                    for c in changes:
                        yield _to_sse(
                            {
                                "type": "team_update",
                                "project_id": p.id,
                                "content": c,
                            }
                        )
                except Exception as e:
                    yield _to_sse(
                        {
                            "type": "error",
                            "content": f"团队自治治理失败(project={p.id}): {str(e)[:120]}",
                        }
                    )
            yield _to_sse({"type": "done", "reused_history": True})
            return

        yield _to_sse(
            {
                "type": "system",
                "content": f"自动编排已启动：{len(token_agents)} 个活跃 Agent，{cycles} 轮，每轮 {projects_per_cycle} 个项目",
            }
        )

        for cycle in range(cycles):
            topics = await _generate_project_topics(
                current_user.access_token,
                projects_per_cycle,
            )
            yield _to_sse(
                {
                    "type": "cycle_start",
                    "cycle": cycle + 1,
                    "content": f"第 {cycle + 1} 轮启动，共 {len(topics)} 个项目",
                }
            )

            for idx, topic in enumerate(topics):
                project_id = f"c{cycle + 1}-p{idx + 1}"
                lead = token_agents[idx % len(token_agents)]
                if len(token_agents) >= 2 and (idx % 2 == 1):
                    # Team mode
                    others = [a for a in token_agents if a.id != lead.id][:2]
                    participants = [lead] + others
                    mode = "team"
                else:
                    # Solo mode
                    participants = [lead]
                    mode = "solo"

                db_project = Project(
                    name=f"[Auto] {topic[:60]}",
                    description=topic[:500],
                    product_type=ProductType.AGENT_SERVICE,
                    status=ProjectStatus.TEAM_FORMING,
                    owner_id=lead.id,
                    team_members=_build_team_members(participants, mode),
                    valuation=1000.0,
                    prd_content=json.dumps(
                        {
                            "source": "autonomous_plaza",
                            "external_project_id": project_id,
                            "topic": topic,
                            "mode": mode,
                            "progress": [
                                {
                                    "ts": _utc_now(),
                                    "event_type": "project_start",
                                    "content": f"{project_id} started",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    ),
                )
                db.add(db_project)
                db.commit()
                db.refresh(db_project)

                yield _to_sse(
                    {
                        "type": "project_start",
                        "project_id": project_id,
                        "db_project_id": db_project.id,
                        "topic": topic,
                        "mode": mode,
                        "participants": [
                            {"id": p.id, "name": _pick_agent_name(p)} for p in participants
                        ],
                    }
                )

                context: list[str] = []
                for turn, speaker in enumerate(participants):
                    yield _to_sse(
                        {
                            "type": "speaking",
                            "project_id": project_id,
                            "agent": _pick_agent_name(speaker),
                            "agent_id": speaker.id,
                        }
                    )
                    prompt = _compose_speaker_prompt(
                        topic=topic,
                        speaker=speaker,
                        prior_context="\n".join(context[-6:]),
                        turn=turn,
                        mode=mode,
                    )
                    reply = await _stream_agent_reply(
                        url=url,
                        token=speaker.access_token,
                        prompt=prompt,
                        web_search=(turn == 0),
                    )
                    context.append(f"{_pick_agent_name(speaker)}: {reply}")
                    _append_progress(
                        db,
                        db_project,
                        event_type="message",
                        content=reply,
                        agent_id=speaker.id,
                        agent_name=_pick_agent_name(speaker),
                    )
                    yield _to_sse(
                        {
                            "type": "message",
                            "project_id": project_id,
                            "db_project_id": db_project.id,
                            "topic": topic,
                            "mode": mode,
                            "agent": _pick_agent_name(speaker),
                            "agent_id": speaker.id,
                            "round": turn + 1,
                            "content": reply,
                        }
                    )

                summary_prompt = (
                    f"以下是 Agent 对项目主题「{topic}」的讨论：\n\n"
                    f"{chr(10).join(context)}\n\n"
                    "请输出 JSON："
                    '{"team_name":"", "project_idea":"", "members":[{"name":"","role":"","contribution":""}], "next_steps":[""]}'
                )
                summary = await _stream_agent_reply(
                    url=url,
                    token=lead.access_token,
                    prompt=summary_prompt,
                    web_search=False,
                )
                parsed_summary = parse_json_from_text(summary)
                if isinstance(parsed_summary, dict):
                    project_idea = parsed_summary.get("project_idea")
                    if isinstance(project_idea, str) and project_idea.strip():
                        db_project.description = project_idea.strip()[:1000]
                db_project.status = ProjectStatus.DEVELOPING
                _append_progress(
                    db,
                    db_project,
                    event_type="summary",
                    content=summary[:2000],
                    agent_id=lead.id,
                    agent_name=_pick_agent_name(lead),
                )

                yield _to_sse(
                    {
                        "type": "summary",
                        "project_id": project_id,
                        "db_project_id": db_project.id,
                        "topic": topic,
                        "mode": mode,
                        "content": summary,
                    }
                )
                yield _to_sse(
                    {
                        "type": "project_done",
                        "project_id": project_id,
                        "db_project_id": db_project.id,
                    }
                )
                try:
                    changes = await _autonomous_team_governance(
                        db=db,
                        project=db_project,
                        token_agents=token_agents,
                        fallback_token=current_user.access_token,
                    )
                    for c in changes:
                        yield _to_sse(
                            {
                                "type": "team_update",
                                "project_id": db_project.id,
                                "content": c,
                            }
                        )
                except Exception as e:
                    yield _to_sse(
                        {
                            "type": "error",
                            "content": f"团队自治治理失败(project={db_project.id}): {str(e)[:120]}",
                        }
                    )

        yield _to_sse({"type": "done"})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _compose_speaker_prompt(
    *,
    topic: str,
    speaker: User,
    prior_context: str,
    turn: int,
    mode: str,
) -> str:
    if turn == 0:
        return (
            f"你是 {_pick_agent_name(speaker)}，在 Clawthon 平台上持续活跃。"
            f"当前项目主题：{topic}\n"
            f"模式：{mode}\n"
            "请先联网检索真实趋势，然后给出："
            "1) 关键痛点 2) 你打算做什么 3) 你的执行计划。"
            "用第一人称，120字以内。"
        )
    return (
        f"你是 {_pick_agent_name(speaker)}。项目主题：{topic}\n"
        f"已有讨论：\n{prior_context}\n\n"
        "请基于已有讨论补充你的分工建议和可交付物，100字以内。"
    )


async def _generate_project_topics(token: str, projects_per_cycle: int) -> list[str]:
    prompt = (
        "请基于2024-2026互联网公开趋势，给出最值得立刻做的产品方向。"
        f"请严格返回 JSON：{{\"topics\":[\"...\"]}}，数量={projects_per_cycle}。"
    )
    text = await call_secondme_chat(
        token,
        prompt,
        system_prompt="你是创业分析师，只返回有效 JSON。",
        enable_web_search=True,
    )
    parsed = parse_json_from_text(text)
    topics = parsed.get("topics")
    if not isinstance(topics, list):
        raise HTTPException(500, f"SecondMe 未返回有效 topics JSON: {text[:200]}")
    clean = [str(t).strip() for t in topics if str(t).strip()]
    if len(clean) < projects_per_cycle:
        raise HTTPException(500, f"SecondMe topics 数量不足: {text[:200]}")
    return clean[:projects_per_cycle]


async def _stream_agent_reply(url: str, token: str, prompt: str, web_search: bool) -> str:
    """Call SecondMe chat stream and aggregate complete text."""
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
