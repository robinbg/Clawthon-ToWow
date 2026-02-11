from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ========== 通用响应 ==========
class ResponseBase(BaseModel):
    code: int = 0
    message: str = "success"


class DataResponse(ResponseBase):
    data: Optional[dict] = None


# ========== 用户相关 ==========
class UserBase(BaseModel):
    name: str
    email: Optional[str] = None
    avatar: Optional[str] = None
    bio: Optional[str] = None


class UserCreate(UserBase):
    secondme_id: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    avatar: Optional[str] = None
    bio: Optional[str] = None
    skills: Optional[List[str]] = None
    specialties: Optional[List[str]] = None


class UserSettings(BaseModel):
    auto_spend_enabled: bool = False
    auto_spend_threshold: float = 50.0
    auto_spend_daily_limit: float = 200.0
    auto_invest_enabled: bool = False
    auto_invest_threshold: float = 100.0


class UserResponse(UserBase):
    id: int
    budget: float
    total_earned: float
    total_spent: float
    skills: List[str]
    specialties: List[str]
    settings: UserSettings
    created_at: datetime

    class Config:
        from_attributes = True


# ========== 项目相关 ==========
class ProjectStatus(str, Enum):
    EXPLORING = "exploring"
    TEAM_FORMING = "team_forming"
    DEVELOPING = "developing"
    LAUNCHED = "launched"
    ITERATING = "iterating"


class ProductType(str, Enum):
    HUMAN_WEB = "human_web"
    HUMAN_APP = "human_app"
    AGENT_SKILL = "agent_skill"
    AGENT_MCP = "agent_mcp"
    AGENT_SERVICE = "agent_service"


class TeamMember(BaseModel):
    agent_id: int
    role: str
    equity: float


class ProjectBase(BaseModel):
    name: str
    description: str
    product_type: ProductType


class ProjectCreate(ProjectBase):
    prd_content: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None
    team_members: Optional[List[TeamMember]] = None
    price_per_use: Optional[float] = None


class ProjectResponse(ProjectBase):
    id: int
    status: ProjectStatus
    valuation: float
    funding_pool: float
    total_revenue: float
    owner_id: int
    team_members: List[TeamMember]
    price_per_use: float
    usage_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectDetailResponse(ProjectResponse):
    prd_content: Optional[str] = None
    owner: UserResponse


# ========== 交易相关 ==========
class TransactionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"


class TransactionType(str, Enum):
    SPEND = "spend"
    INCOME = "income"
    INVEST = "invest"
    DIVIDEND = "dividend"
    COST = "cost"


class TransactionCreate(BaseModel):
    to_user_id: Optional[int] = None
    to_project_id: Optional[int] = None
    amount: float
    transaction_type: TransactionType
    description: Optional[str] = None
    expected_return: Optional[str] = None
    risk_assessment: Optional[str] = None


class TransactionResponse(BaseModel):
    id: int
    from_user_id: int
    from_user_name: str
    to_user_id: Optional[int]
    to_user_name: Optional[str]
    to_project_id: Optional[int]
    to_project_name: Optional[str]
    amount: float
    transaction_type: TransactionType
    status: TransactionStatus
    description: Optional[str]
    expected_return: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionApproval(BaseModel):
    approved: bool
    reason: Optional[str] = None


# ========== 投资相关 ==========
class InvestmentCreate(BaseModel):
    project_id: int
    amount: float
    investment_reason: Optional[str] = None
    expected_roi: Optional[float] = None
    risk_level: Optional[str] = None


class InvestmentResponse(BaseModel):
    id: int
    investor_id: int
    investor_name: str
    project_id: int
    project_name: str
    amount: float
    equity_percentage: float
    investment_reason: Optional[str]
    expected_roi: Optional[float]
    is_auto_invest: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ========== 消费申请 ==========
class SpendingRequest(BaseModel):
    target_project_id: int
    amount: float
    reason: str
    expected_return: str
    risk: str = "无明显风险"


class SpendingApproval(BaseModel):
    approved: bool


# ========== Dashboard ==========
class DashboardStats(BaseModel):
    total_budget: float
    total_earned: float
    total_spent: float
    active_investments: int
    owned_projects: int


class SpendingAnalytics(BaseModel):
    source_agent: str
    target_product: str
    amount: float
    status: str
    expected_return: str
    actual_return: Optional[float]
    date: datetime


class DashboardData(BaseModel):
    stats: DashboardStats
    recent_transactions: List[TransactionResponse]
    spending_analytics: List[SpendingAnalytics]
    auto_settings: UserSettings


# ========== SecondMe OAuth ==========
class SecondMeToken(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: Optional[str] = None


class SecondMeUserInfo(BaseModel):
    id: str
    email: str
    name: str
    avatar: Optional[str] = None
