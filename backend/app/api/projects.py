from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from ..models.database import get_db, ProjectStatus, ProductType
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


@router.post("", response_model=ProjectResponse)
async def create_project(
    data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建新项目"""
    project = ProjectService.create_project(db, current_user.id, data)
    return project


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
    return projects


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
    return projects


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

    return {
        **project.__dict__,
        "owner": {
            "id": owner.id,
            "name": owner.name,
            "email": owner.email,
            "avatar": owner.avatar,
            "bio": owner.bio,
            "budget": owner.budget,
            "total_earned": owner.total_earned,
            "total_spent": owner.total_spent,
            "skills": eval(owner.skills) if owner.skills else [],
            "specialties": eval(owner.specialties) if owner.specialties else [],
            "settings": {
                "auto_spend_enabled": owner.auto_spend_enabled,
                "auto_spend_threshold": owner.auto_spend_threshold,
                "auto_spend_daily_limit": owner.auto_spend_daily_limit,
                "auto_invest_enabled": owner.auto_invest_enabled,
                "auto_invest_threshold": owner.auto_invest_threshold,
            },
            "created_at": owner.created_at,
        } if owner else None
    }


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
    return updated


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
