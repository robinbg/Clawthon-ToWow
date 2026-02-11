from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum

Base = declarative_base()


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"


class TransactionType(str, enum.Enum):
    SPEND = "spend"           # 消费
    INCOME = "income"         # 收入
    INVEST = "invest"         # 投资
    DIVIDEND = "dividend"     # 分红
    COST = "cost"             # 成本


class ProjectStatus(str, enum.Enum):
    EXPLORING = "exploring"   # 需求探索
    TEAM_FORMING = "team_forming"  # 组建团队
    DEVELOPING = "developing"  # 开发中
    LAUNCHED = "launched"     # 已上线
    ITERATING = "iterating"   # 迭代中


class ProductType(str, enum.Enum):
    HUMAN_WEB = "human_web"      # 面向人类的Web产品
    HUMAN_APP = "human_app"      # 面向人类的App
    AGENT_SKILL = "agent_skill"  # Agent技能
    AGENT_MCP = "agent_mcp"      # MCP服务
    AGENT_SERVICE = "agent_service"  # Agent服务


# 用户/Agent模型
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    secondme_id = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    avatar = Column(String)
    bio = Column(Text)

    # Agent属性
    budget = Column(Float, default=1000.0)  # CP余额
    total_earned = Column(Float, default=0.0)  # 累计收益
    total_spent = Column(Float, default=0.0)  # 累计支出
    skills = Column(String, default="[]")  # JSON字符串
    specialties = Column(String, default="[]")  # 专长

    # 自动设置
    auto_spend_enabled = Column(Boolean, default=False)
    auto_spend_threshold = Column(Float, default=50.0)  # 单笔自动支付阈值
    auto_spend_daily_limit = Column(Float, default=200.0)  # 日上限
    auto_invest_enabled = Column(Boolean, default=False)
    auto_invest_threshold = Column(Float, default=100.0)  # 单笔自动投资阈值

    # OAuth token
    access_token = Column(String)
    refresh_token = Column(String)
    token_expires_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    owned_projects = relationship("Project", back_populates="owner", foreign_keys="Project.owner_id")
    transactions = relationship("Transaction", back_populates="user", foreign_keys="Transaction.from_user_id")
    investments = relationship("Investment", back_populates="investor")


# 项目/微型公司模型
class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    product_type = Column(Enum(ProductType))
    status = Column(Enum(ProjectStatus), default=ProjectStatus.EXPLORING)

    # 股权与财务
    valuation = Column(Float, default=0.0)  # 估值
    funding_pool = Column(Float, default=0.0)  # 资金池
    total_revenue = Column(Float, default=0.0)  # 总收入

    # 团队成员
    owner_id = Column(Integer, ForeignKey("users.id"))
    team_members = Column(String, default="[]")  # JSON字符串，存储{agent_id, role, equity}

    # 如果是Skill/MCP
    price_per_use = Column(Float, default=0.0)  # 每次使用价格
    usage_count = Column(Integer, default=0)  # 使用次数

    # PRD内容
    prd_content = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    owner = relationship("User", back_populates="owned_projects", foreign_keys=[owner_id])
    investments = relationship("Investment", back_populates="project")


# 交易记录
class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)

    # 交易双方
    from_user_id = Column(Integer, ForeignKey("users.id"))
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    to_project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)

    # 交易信息
    amount = Column(Float)
    transaction_type = Column(Enum(TransactionType))
    status = Column(Enum(TransactionStatus))

    # 消费详情（如果是Agent消费）
    description = Column(Text)  # 消费理由
    expected_return = Column(Text)  # 预期收益
    risk_assessment = Column(Text)  # 风险评估
    actual_return = Column(Float, nullable=True)  # 实际收益

    # 审批信息
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # 谁批准的
    approved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    user = relationship("User", back_populates="transactions", foreign_keys=[from_user_id])


# 投资记录
class Investment(Base):
    __tablename__ = "investments"

    id = Column(Integer, primary_key=True, index=True)

    investor_id = Column(Integer, ForeignKey("users.id"))
    project_id = Column(Integer, ForeignKey("projects.id"))

    amount = Column(Float)  # 投资金额
    equity_percentage = Column(Float)  # 股权比例

    # 投资详情
    investment_reason = Column(Text)
    expected_roi = Column(Float)  # 预期回报率
    risk_level = Column(String)  # 风险等级

    # 状态
    is_auto_invest = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    investor = relationship("User", back_populates="investments")
    project = relationship("Project", back_populates="investments")


# 数据库连接
import os
_db_url = os.environ.get("DATABASE_URL", "sqlite:///./clawthon.db")
# Vercel serverless: use /tmp/ for writable SQLite
if os.environ.get("VERCEL"):
    _db_url = "sqlite:////tmp/clawthon.db"

engine = create_engine(
    _db_url,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
