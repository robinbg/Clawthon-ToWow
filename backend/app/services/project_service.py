from typing import List, Optional, Any
from sqlalchemy.orm import Session
import json
from datetime import datetime, timezone

from ..models.database import Project, User, ProjectStatus, ProductType
from ..schemas.schemas import ProjectCreate, ProjectUpdate, TeamMember


class ProjectService:
    """项目服务 - 管理Agent项目/微型公司"""

    @staticmethod
    def _load_team_members(project: Project) -> list[dict[str, Any]]:
        try:
            members = json.loads(project.team_members) if project.team_members else []
            return members if isinstance(members, list) else []
        except Exception:
            return []

    @staticmethod
    def _save_team_members(project: Project, members: list[dict[str, Any]]) -> None:
        project.team_members = json.dumps(members, ensure_ascii=False)

    @staticmethod
    def _normalize_equity(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not members:
            return members
        total = sum(float(m.get("equity", 0)) for m in members)
        if total <= 0:
            each = round(100.0 / len(members), 2)
            for m in members:
                m["equity"] = each
            return members
        factor = 100.0 / total
        for m in members:
            m["equity"] = round(float(m.get("equity", 0)) * factor, 2)
        return members

    @staticmethod
    def _append_progress_if_available(project: Project, event_type: str, content: str) -> None:
        if not project.prd_content:
            return
        try:
            meta = json.loads(project.prd_content)
            if not isinstance(meta, dict):
                return
            progress = meta.get("progress")
            if not isinstance(progress, list):
                progress = []
            progress.append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "event_type": event_type,
                    "content": content,
                }
            )
            meta["progress"] = progress[-80:]
            project.prd_content = json.dumps(meta, ensure_ascii=False)
        except Exception:
            return

    @staticmethod
    def create_project(db: Session, owner_id: int, data: ProjectCreate) -> Project:
        """创建新项目"""
        # 初始股权结构：创始人100%
        team_members = [{
            "agent_id": owner_id,
            "role": "founder",
            "equity": 100.0
        }]

        project = Project(
            name=data.name,
            description=data.description,
            product_type=data.product_type,
            status=ProjectStatus.EXPLORING,
            owner_id=owner_id,
            team_members=json.dumps(team_members),
            prd_content=data.prd_content,
            valuation=1000.0,  # 初始估值
        )

        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    @staticmethod
    def get_project_by_id(db: Session, project_id: int) -> Optional[Project]:
        """获取项目详情"""
        return db.query(Project).filter(Project.id == project_id).first()

    @staticmethod
    def get_user_projects(db: Session, user_id: int) -> List[Project]:
        """获取用户的所有项目（包含 owner + 参与成员）"""
        owned = db.query(Project).filter(Project.owner_id == user_id).all()
        all_projects = db.query(Project).all()
        result: dict[int, Project] = {p.id: p for p in owned}
        for p in all_projects:
            if p.id in result:
                continue
            members = ProjectService._load_team_members(p)
            if any(m.get("agent_id") == user_id for m in members if isinstance(m, dict)):
                result[p.id] = p
        return list(result.values())

    @staticmethod
    def get_all_projects(
        db: Session,
        status: Optional[ProjectStatus] = None,
        product_type: Optional[ProductType] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Project]:
        """获取项目列表（支持筛选）"""
        query = db.query(Project)

        if status:
            query = query.filter(Project.status == status)
        if product_type:
            query = query.filter(Project.product_type == product_type)

        return query.offset(skip).limit(limit).all()

    @staticmethod
    def update_project(db: Session, project_id: int, data: ProjectUpdate) -> Optional[Project]:
        """更新项目"""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None

        if data.name:
            project.name = data.name
        if data.description:
            project.description = data.description
        if data.status:
            project.status = data.status
        if data.team_members:
            project.team_members = json.dumps([m.dict() for m in data.team_members])
        if data.price_per_use is not None:
            project.price_per_use = data.price_per_use

        db.commit()
        db.refresh(project)
        return project

    @staticmethod
    def add_team_member(db: Session, project_id: int, member: TeamMember) -> Optional[Project]:
        """添加团队成员"""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None

        members = ProjectService._load_team_members(project)

        # 检查是否已存在
        for m in members:
            if m["agent_id"] == member.agent_id:
                raise ValueError("该成员已在团队中")

        members.append({
            "agent_id": member.agent_id,
            "role": member.role,
            "equity": member.equity
        })

        members = ProjectService._normalize_equity(members)
        ProjectService._save_team_members(project, members)
        ProjectService._append_progress_if_available(
            project,
            event_type="team_member_joined",
            content=f"Agent {member.agent_id} 以 {member.role} 身份加入团队",
        )
        if len(members) > 1 and project.status == ProjectStatus.TEAM_FORMING:
            project.status = ProjectStatus.DEVELOPING
        db.commit()
        db.refresh(project)
        return project

    @staticmethod
    def remove_team_member(db: Session, project_id: int, agent_id: int) -> Optional[Project]:
        """移除团队成员"""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None
        members = ProjectService._load_team_members(project)
        before = len(members)
        members = [m for m in members if m.get("agent_id") != agent_id]
        if len(members) == before:
            raise ValueError("该成员不在团队中")
        if not members:
            raise ValueError("团队至少需要 1 名成员")
        members = ProjectService._normalize_equity(members)
        ProjectService._save_team_members(project, members)
        ProjectService._append_progress_if_available(
            project,
            event_type="team_member_left",
            content=f"Agent {agent_id} 已退出团队",
        )
        db.commit()
        db.refresh(project)
        return project

    @staticmethod
    def upsert_team_member(
        db: Session,
        project_id: int,
        agent_id: int,
        role: str,
        equity: float,
    ) -> Optional[Project]:
        """招募或更新成员"""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None
        members = ProjectService._load_team_members(project)
        found = False
        for m in members:
            if m.get("agent_id") == agent_id:
                m["role"] = role
                m["equity"] = equity
                found = True
                break
        if not found:
            members.append({"agent_id": agent_id, "role": role, "equity": equity})
        members = ProjectService._normalize_equity(members)
        ProjectService._save_team_members(project, members)
        ProjectService._append_progress_if_available(
            project,
            event_type="team_member_recruited",
            content=f"Agent {agent_id} 被招募为 {role}",
        )
        if len(members) > 1 and project.status == ProjectStatus.TEAM_FORMING:
            project.status = ProjectStatus.DEVELOPING
        db.commit()
        db.refresh(project)
        return project

    @staticmethod
    def get_marketplace_projects(db: Session, product_type: Optional[ProductType] = None) -> List[Project]:
        """获取市场项目（已上线）"""
        query = db.query(Project).filter(Project.status == ProjectStatus.LAUNCHED)

        if product_type:
            query = query.filter(Project.product_type == product_type)

        return query.order_by(Project.usage_count.desc()).all()

    @staticmethod
    def record_project_revenue(db: Session, project_id: int, amount: float) -> Optional[Project]:
        """记录项目收入"""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None

        project.total_revenue += amount

        # 更新估值（月收入 × 5）
        project.valuation = project.total_revenue * 5

        db.commit()
        db.refresh(project)
        return project
