import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Any, List, Optional
from pydantic import BaseModel

from ..models.database import get_db, ProjectStatus, ProductType, Project
from ..services.project_service import ProjectService
from ..services.auth_service import UserService
from ..schemas.schemas import (
    ProjectCreate, ProjectUpdate, ProjectResponse,
    ProjectDetailResponse, TeamMember, ProductType as ProductTypeEnum
)
from .auth import get_current_user
from ..models.database import User

router = APIRouter(prefix="/projects", tags=["项目"])


class TeamRecruitRequest(BaseModel):
    agent_id: int
    role: str = "member"
    equity: float = 10.0


def _parse_team_members(raw: Any) -> list[dict]:
    """安全地将 team_members JSON 字符串解析为 list[dict]"""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _serialize_project(project: Project) -> dict:
    """将 Project ORM 对象序列化为 API 响应格式（修复 team_members）"""
    d = {}
    for col in project.__table__.columns:
        d[col.name] = getattr(project, col.name)
    # 关键修复：把 JSON 字符串解析成 list[dict]
    d["team_members"] = _parse_team_members(project.team_members)
    return d


@router.post("", response_model=ProjectResponse)
async def create_project(
    data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建新项目"""
    project = ProjectService.create_project(db, current_user.id, data)
    return _serialize_project(project)


@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    status: Optional[ProjectStatus] = None,
    product_type: Optional[ProductType] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取项目列表"""
    projects = ProjectService.get_all_projects(db, status, product_type, skip, limit)
    return [_serialize_project(p) for p in projects]


@router.get("/marketplace")
async def get_marketplace(
    product_type: Optional[ProductType] = None,
    db: Session = Depends(get_db)
):
    """获取市场项目（已上线的Skills/MCP服务）"""
    projects = ProjectService.get_marketplace_projects(db, product_type)

    result = []
    for p in projects:
        owner = UserService.get_user_by_id(db, p.owner_id)
        result.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "product_type": p.product_type.value,
            "price_per_use": p.price_per_use,
            "usage_count": p.usage_count,
            "valuation": p.valuation,
            "owner": {
                "id": owner.id if owner else 0,
                "name": owner.name if owner else "Unknown",
                "avatar": owner.avatar if owner else None,
            } if owner else None
        })

    return result


@router.get("/my", response_model=List[ProjectResponse])
async def get_my_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取我的项目"""
    projects = ProjectService.get_user_projects(db, current_user.id)
    return [_serialize_project(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: int,
    db: Session = Depends(get_db)
):
    """获取项目详情"""
    project = ProjectService.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    owner = UserService.get_user_by_id(db, project.owner_id)

    data = _serialize_project(project)
    data["owner"] = {
        "id": owner.id,
        "name": owner.name,
        "email": owner.email,
        "avatar": owner.avatar,
        "bio": owner.bio,
        "budget": owner.budget,
        "total_earned": owner.total_earned,
        "total_spent": owner.total_spent,
        "skills": _parse_team_members(owner.skills) if owner.skills else [],
        "specialties": _parse_team_members(owner.specialties) if owner.specialties else [],
        "settings": {
            "auto_spend_enabled": owner.auto_spend_enabled,
            "auto_spend_threshold": owner.auto_spend_threshold,
            "auto_spend_daily_limit": owner.auto_spend_daily_limit,
            "auto_invest_enabled": owner.auto_invest_enabled,
            "auto_invest_threshold": owner.auto_invest_threshold,
        },
        "created_at": owner.created_at,
    } if owner else None
    return data


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新项目"""
    project = ProjectService.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限修改此项目")

    updated = ProjectService.update_project(db, project_id, data)
    return _serialize_project(updated)


@router.post("/{project_id}/team")
async def add_team_member(
    project_id: int,
    member: TeamMember,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """添加团队成员"""
    project = ProjectService.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限修改此项目")

    try:
        updated = ProjectService.add_team_member(db, project_id, member)
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{project_id}/team/recruit")
async def recruit_team_member(
    project_id: int,
    payload: TeamRecruitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """招募新成员（owner）或更新成员角色/股权"""
    project = ProjectService.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="仅项目 owner 可招募成员")
    try:
        updated = ProjectService.upsert_team_member(
            db, project_id, payload.agent_id, payload.role, payload.equity
        )
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{project_id}/team/leave")
async def leave_team(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前用户退出团队"""
    project = ProjectService.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project.owner_id == current_user.id:
        raise HTTPException(status_code=400, detail="owner 不能直接退出团队，请先转让 owner")
    try:
        updated = ProjectService.remove_team_member(db, project_id, current_user.id)
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{project_id}/team/{agent_id}")
async def remove_team_member(
    project_id: int,
    agent_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """owner 移除成员"""
    project = ProjectService.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="仅项目 owner 可移除成员")
    if agent_id == current_user.id:
        raise HTTPException(status_code=400, detail="owner 不能移除自己")
    try:
        updated = ProjectService.remove_team_member(db, project_id, agent_id)
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{project_id}/launch")
async def launch_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """上线项目"""
    project = ProjectService.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限操作")

    updated = ProjectService.update_project(
        db, project_id,
        ProjectUpdate(status=ProjectStatus.LAUNCHED)
    )
    return {"message": "项目已上线", "project": updated}


# ==================== 导出：需求 & PRD & 产品全量下载 ====================

def _extract_project_data(p: Project) -> dict[str, Any]:
    """从 Project 对象提取完整的需求/PRD/产品数据"""
    meta: dict = {}
    try:
        if p.prd_content:
            parsed = json.loads(p.prd_content)
            if isinstance(parsed, dict):
                meta = parsed
    except Exception:
        pass

    # 从 progress 事件中提取结构化数据
    progress = meta.get("progress", [])
    needs = []
    prds = []
    discussions = []
    summaries = []
    deployments = []

    for evt in progress if isinstance(progress, list) else []:
        if not isinstance(evt, dict):
            continue
        et = evt.get("event_type", "")
        content = evt.get("content", "")
        ts = evt.get("ts", "")
        agent = evt.get("agent_name", "")

        if et == "prd_generated":
            prds.append({"timestamp": ts, "agent": agent, "content": content})
        elif et == "message":
            discussions.append({"timestamp": ts, "agent": agent, "content": content})
        elif et == "summary":
            summaries.append({"timestamp": ts, "agent": agent, "content": content})
        elif et == "product_deployed":
            deployments.append({"timestamp": ts, "agent": agent, "content": content})
        elif et == "project_start":
            needs.append({"timestamp": ts, "content": content})

    # 如果 prd_content 不是 JSON 而是纯文本 PRD
    raw_prd = ""
    if not meta and p.prd_content:
        raw_prd = p.prd_content

    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "product_type": p.product_type.value if p.product_type else None,
        "status": p.status.value if p.status else None,
        "valuation": p.valuation,
        "total_revenue": p.total_revenue,
        "funding_pool": p.funding_pool,
        "usage_count": p.usage_count,
        "price_per_use": p.price_per_use,
        "owner_id": p.owner_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        # 结构化内容
        "topic": meta.get("topic", p.description or ""),
        "mode": meta.get("mode", "solo"),
        "source": meta.get("source", "manual"),
        "needs": needs,
        "prds": prds,
        "discussions": discussions,
        "summaries": summaries,
        "deployments": deployments,
        "raw_prd": raw_prd,
        # 产品代码
        "product_type_detail": p.product_type_detail,
        "product_code": p.product_code,
        "product_endpoint": p.product_endpoint,
        # team
        "team_members_raw": p.team_members,
    }


@router.get("/export/all")
async def export_all_projects(
    db: Session = Depends(get_db),
):
    """导出所有项目的完整数据（需求/PRD/讨论/产品代码）— 无需认证，方便本地脚本调用"""
    projects = db.query(Project).order_by(Project.created_at.asc()).all()
    result = [_extract_project_data(p) for p in projects]
    return {
        "exported_at": datetime.utcnow().isoformat(),
        "total_projects": len(result),
        "projects": result,
    }


@router.get("/export/{project_id}")
async def export_single_project(
    project_id: int,
    db: Session = Depends(get_db),
):
    """导出单个项目的完整数据"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    return _extract_project_data(project)


@router.post("/export/save-local")
async def save_all_to_local(
    db: Session = Depends(get_db),
):
    """将所有项目数据保存到本地磁盘 D:\\Clawthon\\exports\\"""
    projects = db.query(Project).order_by(Project.created_at.asc()).all()
    if not projects:
        return {"message": "暂无项目数据", "saved": 0}

    # 基础导出目录
    export_base = Path(os.environ.get("CLAWTHON_EXPORT_DIR", "D:/Clawthon/exports"))
    export_base.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    batch_dir = export_base / f"batch_{timestamp}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    saved_count = 0
    index_entries: list[dict] = []

    for p in projects:
        data = _extract_project_data(p)
        safe_name = (p.name or f"project_{p.id}").replace("/", "_").replace("\\", "_").replace(":", "_")[:60]
        proj_dir = batch_dir / f"{p.id}_{safe_name}"
        proj_dir.mkdir(parents=True, exist_ok=True)

        # 1) 完整 JSON
        (proj_dir / "project.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 2) PRD 文档（Markdown）
        for i, prd in enumerate(data.get("prds", [])):
            prd_file = proj_dir / f"PRD_{i+1}.md"
            header = f"# PRD: {p.name}\n\n"
            header += f"- 项目ID: {p.id}\n"
            header += f"- 生成时间: {prd.get('timestamp', 'N/A')}\n"
            header += f"- Agent: {prd.get('agent', 'N/A')}\n\n---\n\n"
            prd_file.write_text(header + prd.get("content", ""), encoding="utf-8")

        # 如果有纯文本 PRD
        if data.get("raw_prd"):
            (proj_dir / "PRD_raw.md").write_text(
                f"# PRD: {p.name}\n\n{data['raw_prd']}", encoding="utf-8"
            )

        # 3) 需求/讨论
        if data.get("discussions"):
            lines = [f"# 讨论记录: {p.name}\n"]
            for d in data["discussions"]:
                lines.append(f"\n## [{d.get('timestamp', '')}] {d.get('agent', '')}\n")
                lines.append(d.get("content", ""))
            (proj_dir / "discussions.md").write_text("\n".join(lines), encoding="utf-8")

        # 4) 摘要
        if data.get("summaries"):
            lines = [f"# 摘要: {p.name}\n"]
            for s in data["summaries"]:
                lines.append(f"\n## [{s.get('timestamp', '')}] {s.get('agent', '')}\n")
                lines.append(s.get("content", ""))
            (proj_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")

        # 5) 产品代码
        if data.get("product_code"):
            pt = data.get("product_type_detail", "unknown")
            if pt == "web_app":
                (proj_dir / "product.html").write_text(data["product_code"], encoding="utf-8")
            elif pt == "agent_skill":
                (proj_dir / "product_skill.py").write_text(data["product_code"], encoding="utf-8")
            elif pt == "mcp_service":
                (proj_dir / "product_mcp.py").write_text(data["product_code"], encoding="utf-8")
            else:
                (proj_dir / "product_code.txt").write_text(data["product_code"], encoding="utf-8")

        saved_count += 1
        index_entries.append({
            "id": p.id,
            "name": p.name,
            "status": data.get("status"),
            "product_type": data.get("product_type"),
            "prds_count": len(data.get("prds", [])),
            "has_raw_prd": bool(data.get("raw_prd")),
            "has_product_code": bool(data.get("product_code")),
            "discussions_count": len(data.get("discussions", [])),
            "dir": str(proj_dir),
        })

    # 6) 写入索引文件
    index_data = {
        "exported_at": datetime.utcnow().isoformat(),
        "total_projects": saved_count,
        "export_dir": str(batch_dir),
        "projects": index_entries,
    }
    (batch_dir / "INDEX.json").write_text(
        json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 7) 也写入一份完整的 all_projects.json
    all_data = [_extract_project_data(p) for p in projects]
    (batch_dir / "all_projects.json").write_text(
        json.dumps({
            "exported_at": datetime.utcnow().isoformat(),
            "total_projects": len(all_data),
            "projects": all_data,
        }, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "message": f"已保存 {saved_count} 个项目到本地",
        "saved": saved_count,
        "export_dir": str(batch_dir),
        "index": index_entries,
    }
