from typing import List, Optional
from sqlalchemy.orm import Session
import json

from ..models.database import Project, User, ProjectStatus, ProductType
from ..schemas.schemas import ProjectCreate, ProjectUpdate, TeamMember


class ProjectService:
    """项目服务 - 管理Agent项目/微型公司"""

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
        """获取用户的所有项目"""
        return db.query(Project).filter(Project.owner_id == user_id).all()

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

        members = json.loads(project.team_members)

        # 检查是否已存在
        for m in members:
            if m["agent_id"] == member.agent_id:
                raise ValueError("该成员已在团队中")

        members.append({
            "agent_id": member.agent_id,
            "role": member.role,
            "equity": member.equity
        })

        # 重新计算股权（按比例稀释）
        total_equity = sum(m["equity"] for m in members)
        if total_equity != 100:
            # 标准化到100%
            factor = 100 / total_equity
            for m in members:
                m["equity"] = round(m["equity"] * factor, 2)

        project.team_members = json.dumps(members)
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
