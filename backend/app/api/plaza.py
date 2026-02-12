"""Agent Plaza autonomous teaming and activity stream."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models.database import (
    Project,
    ProjectStatus,
    ProductType,
    Transaction,
    TransactionStatus,
    TransactionType,
    User,
    get_db,
)
from ..services.project_service import ProjectService
from .ai import call_secondme_chat, parse_json_from_text
from .auth import get_current_user, rebuild_all_agents_from_registry

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
            if event_type not in (
                "project_start",
                "message",
                "summary",
                "team_member_joined",
                "team_member_left",
                "team_member_recruited",
                "stage_advanced",
                "promotion",
                "agent_consumption",
                "human_consumption",
                "revenue_distribution",
                "iteration",
            ):
                continue
            mapped_type = "message"
            if event_type == "project_start":
                mapped_type = "project_start"
            elif event_type == "summary":
                mapped_type = "summary"
            elif event_type in ("team_member_joined", "team_member_left", "team_member_recruited"):
                mapped_type = "team_update"
            elif event_type in ("stage_advanced", "promotion", "human_consumption", "revenue_distribution", "iteration"):
                mapped_type = "system"
            events.append(
                {
                    "event_id": f"{p['id']}:{idx}:{evt.get('ts', '')}",
                    "project_id": p["id"],
                    "topic": p.get("topic"),
                    "mode": p.get("mode"),
                    "type": mapped_type,
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

    stage = project.status.value if project.status else "exploring"
    stage_policy = {
        "exploring": {
            "goal": "快速扩展信息面，优先补齐调研/产品洞察角色",
            "allowed_actions": ["add", "update", "none"],
            "team_size_hint": "2-4",
            "allow_stage_transition_to": "team_forming",
        },
        "team_forming": {
            "goal": "尽快形成可执行小队，角色覆盖产品/开发/增长",
            "allowed_actions": ["add", "update", "remove", "none"],
            "team_size_hint": "2-5",
            "allow_stage_transition_to": "developing",
        },
        "developing": {
            "goal": "稳定执行，避免频繁换人，仅按缺口补位",
            "allowed_actions": ["add", "update", "remove", "none"],
            "team_size_hint": "2-6",
            "allow_stage_transition_to": "launched",
        },
        "launched": {
            "goal": "上线后保稳定，围绕运营与增长做小幅调整",
            "allowed_actions": ["add", "update", "none"],
            "team_size_hint": "2-6",
            "allow_stage_transition_to": "iterating",
        },
        "iterating": {
            "goal": "迭代优化，按反馈微调团队，不做大规模重组",
            "allowed_actions": ["add", "update", "remove", "none"],
            "team_size_hint": "2-6",
            "allow_stage_transition_to": "iterating",
        },
    }.get(stage, {
        "goal": "保持团队稳定并按需优化",
        "allowed_actions": ["add", "update", "remove", "none"],
        "team_size_hint": "2-5",
        "allow_stage_transition_to": stage,
    })

    member_ids = [m.get("agent_id") for m in members if isinstance(m, dict)]
    candidates = [
        {"id": a.id, "name": _pick_agent_name(a), "budget": a.budget}
        for a in token_agents
        if a.id not in member_ids
    ][:8]

    prompt = (
        f"你是项目治理 Agent。请为项目「{project.name}」做团队调整决策。\n"
        f"当前阶段：{stage}\n"
        f"阶段目标：{stage_policy['goal']}\n"
        f"建议团队规模：{stage_policy['team_size_hint']}\n"
        f"允许动作：{stage_policy['allowed_actions']}\n"
        f"可推进到阶段：{stage_policy['allow_stage_transition_to']}\n"
        f"项目描述：{project.description or ''}\n"
        f"当前状态：valuation={project.valuation}, funding_pool={project.funding_pool}, revenue={project.total_revenue}, usage_count={project.usage_count}\n"
        f"当前成员：{json.dumps(members, ensure_ascii=False)}\n"
        f"可招募候选：{json.dumps(candidates, ensure_ascii=False)}\n"
        "请仅返回 JSON："
        '{"actions":[{"action":"add|remove|update|advance_stage|none","agent_id":0,"role":"member","equity":10,"to_stage":"team_forming|developing|launched|iterating","reason":""}]}\n'
        "约束：\n"
        "1) 最多返回 3 个动作\n"
        "2) 不能移除 owner\n"
        "3) stage 只能推进到可推进阶段，不可回退\n"
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

    valid_stage_values = {s.value for s in ProjectStatus}
    allowed_transition = str(stage_policy["allow_stage_transition_to"])

    # Build set of all real agent IDs for validation
    all_real_agent_ids = {a.id for a in token_agents}
    candidate_ids = {c["id"] for c in candidates}

    applied: list[dict[str, Any]] = []
    for action in actions[:3]:
        if not isinstance(action, dict):
            continue
        kind = str(action.get("action", "none")).lower()
        if kind == "none":
            continue
        agent_id = int(action.get("agent_id", 0) or 0)
        role = str(action.get("role", "member"))
        equity = float(action.get("equity", 10) or 10)
        reason = str(action.get("reason", "")).strip()

        # CRITICAL: skip any agent_id that doesn't exist in the real system
        if kind in ("add", "update", "remove") and agent_id not in all_real_agent_ids:
            logger.warning(f"Governance skipped: agent_id={agent_id} does not exist in system")
            continue

        try:
            if kind == "add":
                # Only allow adding agents that are in the candidate list (not already members)
                if agent_id not in candidate_ids:
                    continue
                agent_user = next((a for a in token_agents if a.id == agent_id), None)
                agent_name = _pick_agent_name(agent_user) if agent_user else f"Agent-{agent_id}"
                ProjectService.upsert_team_member(db, project.id, agent_id, role, equity)
                _append_progress(db, project, event_type="team_member_recruited",
                                 content=f"{agent_name} 被招募为 {role}", agent_id=agent_id, agent_name=agent_name)
                applied.append({"action": kind, "agent_id": agent_id, "name": agent_name, "role": role, "equity": equity, "reason": reason})
            elif kind == "update":
                agent_user = next((a for a in token_agents if a.id == agent_id), None)
                agent_name = _pick_agent_name(agent_user) if agent_user else f"Agent-{agent_id}"
                ProjectService.upsert_team_member(db, project.id, agent_id, role, equity)
                applied.append({"action": kind, "agent_id": agent_id, "name": agent_name, "role": role, "equity": equity, "reason": reason})
            elif kind == "remove":
                if agent_id == project.owner_id:
                    continue
                agent_user = next((a for a in token_agents if a.id == agent_id), None)
                agent_name = _pick_agent_name(agent_user) if agent_user else f"Agent-{agent_id}"
                ProjectService.remove_team_member(db, project.id, agent_id)
                _append_progress(db, project, event_type="team_member_left",
                                 content=f"{agent_name} 离开团队", agent_id=agent_id, agent_name=agent_name)
                applied.append({"action": kind, "agent_id": agent_id, "name": agent_name, "reason": reason})
            elif kind == "advance_stage":
                to_stage = str(action.get("to_stage", "")).strip()
                if to_stage in valid_stage_values and to_stage == allowed_transition:
                    if project.status is None or project.status.value != to_stage:
                        project.status = ProjectStatus(to_stage)
                        db.commit()
                        db.refresh(project)
                        _append_progress(
                            db,
                            project,
                            event_type="stage_advanced",
                            content=f"项目阶段从 {stage} 推进到 {to_stage}",
                        )
                        applied.append({"action": kind, "to_stage": to_stage, "reason": reason})
        except Exception:
            continue
    return applied


async def _autonomous_economy_cycle(
    *,
    db: Session,
    project: Project,
    token_agents: list[User],
    fallback_token: str,
) -> list[dict[str, Any]]:
    """Autonomous loop: promotion -> agent consumption -> human consumption -> revenue distribution -> iterate."""
    updates: list[dict[str, Any]] = []

    members = []
    try:
        members = json.loads(project.team_members) if project.team_members else []
    except Exception:
        members = []
    member_ids = [m.get("agent_id") for m in members if isinstance(m, dict)]
    owner = next((a for a in token_agents if a.id == project.owner_id and a.access_token), None)
    decision_token = (owner.access_token if owner else None) or fallback_token

    # 1) 宣发（由 Agent 决策文案）
    promo_text = await call_secondme_chat(
        decision_token,
        (
            f"你是项目{project.name}的增长 Agent。请生成一句简短宣发文案（40字内），"
            "强调真实价值和目标用户。只返回文案本身。"
        ),
        enable_web_search=False,
    )
    promo_text = (promo_text or "").strip()[:120] or "项目发布宣发启动"
    _append_progress(db, project, event_type="promotion", content=promo_text)
    updates.append({"action": "promotion", "content": promo_text})

    # 2) Agent 消费（非团队 Agent 自动选择消费）
    consumers = [a for a in token_agents if a.id not in member_ids and a.budget > 1][:3]
    unit_price = max(1.0, float(project.price_per_use or 15.0))
    for c in consumers:
        amount = min(unit_price, float(c.budget))
        if amount < 1:
            continue
        tx = Transaction(
            from_user_id=c.id,
            to_project_id=project.id,
            amount=amount,
            transaction_type=TransactionType.SPEND,
            status=TransactionStatus.AUTO_APPROVED,
            description=f"Agent 自主消费 {project.name}",
            expected_return="获得项目服务价值",
            risk_assessment="低",
        )
        c.budget -= amount
        c.total_spent += amount
        project.funding_pool += amount
        project.usage_count += 1
        db.add(tx)
        _append_progress(
            db,
            project,
            event_type="agent_consumption",
            content=f"Agent {_pick_agent_name(c)} 消费 {amount:.2f} CP",
            agent_id=c.id,
            agent_name=_pick_agent_name(c),
        )
        updates.append({"action": "agent_consumption", "agent_id": c.id, "amount": round(amount, 2)})
    db.commit()
    db.refresh(project)

    # 3) 人类消费（由 Agent 估算并执行）
    human_plan_raw = await call_secondme_chat(
        decision_token,
        (
            f"你是{project.name}的商业 Agent。基于当前阶段{project.status.value if project.status else 'unknown'}，"
            "请估算本轮人类消费。仅返回 JSON："
            '{"human_orders": 0, "unit_price": 0, "reason": ""}'
        ),
        enable_web_search=False,
    )
    human_orders = 0
    human_unit_price = unit_price
    human_reason = ""
    try:
        parsed = parse_json_from_text(human_plan_raw)
        human_orders = max(0, int(parsed.get("human_orders", 0) or 0))
        human_unit_price = max(0.0, float(parsed.get("unit_price", unit_price) or unit_price))
        human_reason = str(parsed.get("reason", "") or "").strip()
    except Exception:
        human_orders = 0
    human_orders = min(human_orders, 20)
    human_revenue = round(human_orders * human_unit_price, 2)
    if human_revenue > 0:
        project.total_revenue += human_revenue
        project.funding_pool += round(human_revenue * 0.6, 2)
        project.valuation = max(project.valuation, project.total_revenue * 5 if project.total_revenue > 0 else 1000.0)
        _append_progress(
            db,
            project,
            event_type="human_consumption",
            content=f"人类消费 {human_orders} 单，收入 {human_revenue:.2f} CP。{human_reason}",
        )
        updates.append({"action": "human_consumption", "orders": human_orders, "revenue": human_revenue})
    db.commit()
    db.refresh(project)

    # 4) 收益分配（按股权）
    if human_revenue > 0 and members:
        distributable = round(human_revenue * 0.5, 2)
        distribution_rows: list[str] = []
        for m in members:
            if not isinstance(m, dict):
                continue
            uid = m.get("agent_id")
            equity = float(m.get("equity", 0) or 0)
            amount = round(distributable * equity / 100.0, 2)
            if amount <= 0:
                continue
            u = db.query(User).filter(User.id == uid).first()
            if not u:
                continue
            u.budget += amount
            u.total_earned += amount
            distribution_rows.append(f"{_pick_agent_name(u)} +{amount:.2f}CP({equity:.2f}%)")
        if distribution_rows:
            _append_progress(
                db,
                project,
                event_type="revenue_distribution",
                content="; ".join(distribution_rows),
            )
            updates.append({"action": "revenue_distribution", "content": distribution_rows})
    db.commit()
    db.refresh(project)

    # 5) 迭代
    if project.status != ProjectStatus.ITERATING:
        project.status = ProjectStatus.ITERATING
        db.commit()
        db.refresh(project)
    _append_progress(
        db,
        project,
        event_type="iteration",
        content="进入迭代阶段：根据消费反馈调整定位与路线",
    )
    updates.append({"action": "iteration", "status": project.status.value if project.status else "iterating"})
    return updates

@router.get("/agents")
async def list_agents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """All logged-in SecondMe users are considered active participants."""
    rebuild_all_agents_from_registry(db)
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
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Infinite autonomous stream — keeps generating projects until client disconnects."""
    if not current_user.access_token:
        raise HTTPException(400, "缺少 SecondMe token")

    api_base = settings.SECONDME_API_BASE.strip()
    url = f"{api_base}/gate/lab/api/secondme/chat/stream"

    async def stream():
        project_seq = 0

        # Rebuild all known agents from registry (survives Vercel cold starts)
        rebuilt = rebuild_all_agents_from_registry(db)
        if rebuilt > 0:
            logger.info(f"Rebuilt {rebuilt} agents from registry")

        # ---- initial: govern existing projects first ----
        existing_projects = _get_autonomous_projects(db, limit=500)
        project_seq = len(existing_projects)

        all_agents = db.query(User).filter(User.secondme_id.isnot(None)).all()
        token_agents = [a for a in all_agents if a.access_token]
        if not any(a.id == current_user.id for a in token_agents):
            token_agents.insert(0, current_user)

        yield _to_sse({
            "type": "system",
            "content": f"♾️ 自治流已启动（无限模式）：{len(token_agents)} 个 Agent 在线，已有 {project_seq} 个项目。持续产生新项目...",
        })

        if existing_projects:
            yield _to_sse({"type": "system", "content": "先对最近项目执行一轮治理与经济循环..."})
            for p in existing_projects[-3:]:
                if await request.is_disconnected():
                    return
                try:
                    changes = await _autonomous_team_governance(db=db, project=p, token_agents=token_agents, fallback_token=current_user.access_token)
                    for c in changes:
                        yield _to_sse({"type": "team_update", "project_id": p.id, "content": c})
                    econ = await _autonomous_economy_cycle(db=db, project=p, token_agents=token_agents, fallback_token=current_user.access_token)
                    for e in econ:
                        yield _to_sse({"type": "economic_update", "project_id": p.id, "content": e})
                except Exception as exc:
                    yield _to_sse({"type": "error", "content": f"治理失败(#{p.id}): {str(exc)[:100]}"})

        # ---- infinite loop: keep generating new projects ----
        while True:
            if await request.is_disconnected():
                return

            # refresh agent list each round (rebuild from registry in case of cold start)
            rebuild_all_agents_from_registry(db)
            all_agents = db.query(User).filter(User.secondme_id.isnot(None)).all()
            token_agents = [a for a in all_agents if a.access_token]
            if not any(a.id == current_user.id for a in token_agents):
                token_agents.insert(0, current_user)
            if not token_agents:
                yield _to_sse({"type": "system", "content": "暂无可用 Agent，等待中..."})
                await asyncio.sleep(5)
                continue

            # generate 1 topic per iteration (pass existing projects for dedup)
            all_existing = _get_autonomous_projects(db, limit=500)
            try:
                topics = await _generate_project_topics(current_user.access_token, 1, existing_projects=all_existing)
            except Exception as exc:
                yield _to_sse({"type": "error", "content": f"生成主题失败: {str(exc)[:100]}"})
                await asyncio.sleep(3)
                continue

            for topic in topics:
                if await request.is_disconnected():
                    return

                project_seq += 1
                project_id = f"p{project_seq}"
                lead = token_agents[(project_seq - 1) % len(token_agents)]
                if len(token_agents) >= 2 and (project_seq % 2 == 0):
                    others = [a for a in token_agents if a.id != lead.id][:2]
                    participants = [lead] + others
                    mode = "team"
                else:
                    participants = [lead]
                    mode = "solo"

                db_project = Project(
                    name=f"[Auto] {topic[:60]}",
                    description=topic[:500],
                    product_type=ProductType.AGENT_SERVICE,
                    status=ProjectStatus.EXPLORING,
                    owner_id=lead.id,
                    team_members=_build_team_members(participants, mode),
                    valuation=1000.0,
                    prd_content=json.dumps({
                        "source": "autonomous_plaza",
                        "external_project_id": project_id,
                        "topic": topic,
                        "mode": mode,
                        "progress": [{"ts": _utc_now(), "event_type": "project_start", "content": f"{project_id} started"}],
                    }, ensure_ascii=False),
                )
                db.add(db_project)
                db.commit()
                db.refresh(db_project)

                yield _to_sse({
                    "type": "project_start",
                    "project_id": project_id,
                    "db_project_id": db_project.id,
                    "topic": topic,
                    "mode": mode,
                    "participants": [{"id": p.id, "name": _pick_agent_name(p)} for p in participants],
                })

                # discussion rounds
                context: list[str] = []
                for turn, speaker in enumerate(participants):
                    if await request.is_disconnected():
                        return
                    yield _to_sse({"type": "speaking", "project_id": project_id, "agent": _pick_agent_name(speaker), "agent_id": speaker.id})
                    prompt = _compose_speaker_prompt(topic=topic, speaker=speaker, prior_context="\n".join(context[-6:]), turn=turn, mode=mode)
                    reply = await _stream_agent_reply(url=url, token=speaker.access_token, prompt=prompt, web_search=(turn == 0))
                    context.append(f"{_pick_agent_name(speaker)}: {reply}")
                    _append_progress(db, db_project, event_type="message", content=reply, agent_id=speaker.id, agent_name=_pick_agent_name(speaker))
                    yield _to_sse({
                        "type": "message", "project_id": project_id, "db_project_id": db_project.id,
                        "topic": topic, "mode": mode, "agent": _pick_agent_name(speaker),
                        "agent_id": speaker.id, "round": turn + 1, "content": reply,
                    })

                # summary
                summary_prompt = (
                    f"以下是 Agent 对项目主题「{topic}」的讨论：\n\n{chr(10).join(context)}\n\n"
                    "请输出 JSON："
                    '{"team_name":"", "project_idea":"", "members":[{"name":"","role":"","contribution":""}], "next_steps":[""]}'
                )
                summary = await _stream_agent_reply(url=url, token=lead.access_token, prompt=summary_prompt, web_search=False)
                parsed_summary = parse_json_from_text(summary)
                if isinstance(parsed_summary, dict):
                    idea = parsed_summary.get("project_idea")
                    if isinstance(idea, str) and idea.strip():
                        db_project.description = idea.strip()[:1000]
                if db_project.status == ProjectStatus.EXPLORING:
                    db_project.status = ProjectStatus.TEAM_FORMING
                _append_progress(db, db_project, event_type="summary", content=summary[:2000], agent_id=lead.id, agent_name=_pick_agent_name(lead))
                yield _to_sse({"type": "summary", "project_id": project_id, "db_project_id": db_project.id, "topic": topic, "mode": mode, "content": summary})
                yield _to_sse({"type": "project_done", "project_id": project_id, "db_project_id": db_project.id})

                # governance + economy
                try:
                    changes = await _autonomous_team_governance(db=db, project=db_project, token_agents=token_agents, fallback_token=current_user.access_token)
                    for c in changes:
                        yield _to_sse({"type": "team_update", "project_id": db_project.id, "content": c})
                    econ = await _autonomous_economy_cycle(db=db, project=db_project, token_agents=token_agents, fallback_token=current_user.access_token)
                    for e in econ:
                        yield _to_sse({"type": "economic_update", "project_id": db_project.id, "content": e})
                except Exception as exc:
                    yield _to_sse({"type": "error", "content": f"治理失败(#{db_project.id}): {str(exc)[:100]}"})

            # brief pause between projects
            await asyncio.sleep(2)

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


async def _generate_project_topics(token: str, projects_per_cycle: int, existing_projects: list[Project] | None = None) -> list[str]:
    # Build list of existing project names/descriptions so AI avoids duplicates
    existing_lines: list[str] = []
    if existing_projects:
        for p in existing_projects[-30:]:  # last 30 projects
            desc = (p.description or p.name or "")[:80]
            existing_lines.append(f"- {p.name}: {desc}")
    existing_text = "\n".join(existing_lines) if existing_lines else "（暂无）"

    prompt = (
        "你是创业分析师。请基于2024-2026互联网公开趋势，给出最值得立刻做的产品方向。\n\n"
        "⚠️ 重要：以下是平台上已有的项目，你必须避免与它们重复或高度相似：\n"
        f"{existing_text}\n\n"
        "要求：\n"
        "1. 每个方向必须和上面已有项目本质不同（不同行业/不同用户群/不同技术路线）\n"
        "2. 具体到可执行的产品，不要泛泛的方向\n"
        "3. 覆盖不同领域（如教育、医疗、金融、创作、社交、开发者工具、硬件等）\n\n"
        f"请严格返回 JSON：{{\"topics\":[\"...\"]}}，数量={projects_per_cycle}。"
    )
    text = await call_secondme_chat(
        token,
        prompt,
        system_prompt="你是创业分析师，只返回有效 JSON。必须避开已有项目方向。",
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
