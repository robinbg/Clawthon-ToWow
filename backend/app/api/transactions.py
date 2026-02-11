from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from ..models.database import get_db, TransactionType, TransactionStatus
from ..services.transaction_service import TransactionService, InvestmentService
from ..services.auth_service import UserService
from ..services.project_service import ProjectService
from ..schemas.schemas import (
    SpendingRequest, SpendingApproval, TransactionResponse,
    InvestmentCreate, InvestmentResponse, DashboardData,
    DashboardStats, SpendingAnalytics, TransactionApproval
)
from .auth import get_current_user
from ..models.database import User

router = APIRouter(prefix="/transactions", tags=["交易"])


@router.post("/spend")
async def create_spending_request(
    request: SpendingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建消费申请（Agent使用Skill/MCP服务）"""
    try:
        transaction = TransactionService.create_spending_request(
            db, current_user.id, request
        )

        # 获取目标项目信息
        project = ProjectService.get_project_by_id(db, request.target_project_id)

        return {
            "id": transaction.id,
            "amount": transaction.amount,
            "status": transaction.status.value,
            "message": "消费申请已自动批准" if transaction.status == TransactionStatus.AUTO_APPROVED else "消费申请已提交，等待审批",
            "target_project": project.name if project else None,
            "remaining_budget": current_user.budget - (transaction.amount if transaction.status == TransactionStatus.AUTO_APPROVED else 0)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/pending", response_model=List[TransactionResponse])
async def get_pending_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取待审批的消费申请（用户拥有的项目收到的申请）"""
    transactions = TransactionService.get_pending_transactions(db, current_user.id)

    result = []
    for t in transactions:
        from_user = UserService.get_user_by_id(db, t.from_user_id)
        to_project = ProjectService.get_project_by_id(db, t.to_project_id) if t.to_project_id else None

        result.append({
            "id": t.id,
            "from_user_id": t.from_user_id,
            "from_user_name": from_user.name if from_user else "Unknown",
            "to_user_id": t.to_user_id,
            "to_user_name": None,
            "to_project_id": t.to_project_id,
            "to_project_name": to_project.name if to_project else None,
            "amount": t.amount,
            "transaction_type": t.transaction_type,
            "status": t.status,
            "description": t.description,
            "expected_return": t.expected_return,
            "created_at": t.created_at,
        })

    return result


@router.post("/{transaction_id}/approve")
async def approve_transaction(
    transaction_id: int,
    approval: TransactionApproval,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """审批交易"""
    transaction = TransactionService.approve_transaction(
        db, transaction_id, current_user.id, approval
    )

    if not transaction:
        raise HTTPException(status_code=404, detail="交易不存在或无法审批")

    return {
        "message": "交易已批准" if approval.approved else "交易已拒绝",
        "transaction_id": transaction.id,
        "status": transaction.status.value
    }


@router.get("/my", response_model=List[TransactionResponse])
async def get_my_transactions(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取我的交易记录"""
    transactions = TransactionService.get_user_transactions(db, current_user.id, limit)

    result = []
    for t in transactions:
        from_user = UserService.get_user_by_id(db, t.from_user_id)
        to_user = UserService.get_user_by_id(db, t.to_user_id) if t.to_user_id else None
        to_project = ProjectService.get_project_by_id(db, t.to_project_id) if t.to_project_id else None

        result.append({
            "id": t.id,
            "from_user_id": t.from_user_id,
            "from_user_name": from_user.name if from_user else "Unknown",
            "to_user_id": t.to_user_id,
            "to_user_name": to_user.name if to_user else None,
            "to_project_id": t.to_project_id,
            "to_project_name": to_project.name if to_project else None,
            "amount": t.amount,
            "transaction_type": t.transaction_type,
            "status": t.status,
            "description": t.description,
            "expected_return": t.expected_return,
            "created_at": t.created_at,
        })

    return result


@router.post("/invest")
async def create_investment(
    data: InvestmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建投资"""
    try:
        investment = InvestmentService.create_investment_proposal(
            db,
            current_user.id,
            data.project_id,
            data.amount,
            data.investment_reason,
            data.expected_roi,
            data.risk_level
        )

        return {
            "id": investment.id,
            "amount": investment.amount,
            "equity_percentage": investment.equity_percentage,
            "is_auto_invest": investment.is_auto_invest,
            "message": "投资已自动执行" if investment.is_auto_invest else "投资提案已创建，等待审批"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/investments/my", response_model=List[InvestmentResponse])
async def get_my_investments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取我的投资记录"""
    from ..models.database import Investment

    investments = db.query(Investment).filter(
        Investment.investor_id == current_user.id
    ).all()

    result = []
    for inv in investments:
        project = ProjectService.get_project_by_id(db, inv.project_id)
        result.append({
            "id": inv.id,
            "investor_id": inv.investor_id,
            "investor_name": current_user.name,
            "project_id": inv.project_id,
            "project_name": project.name if project else "Unknown",
            "amount": inv.amount,
            "equity_percentage": inv.equity_percentage,
            "investment_reason": inv.investment_reason,
            "expected_roi": inv.expected_roi,
            "is_auto_invest": inv.is_auto_invest,
            "created_at": inv.created_at,
        })

    return result


@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取Dashboard数据"""
    from ..models.database import Investment, Transaction

    # 统计信息
    projects = ProjectService.get_user_projects(db, current_user.id)
    investments = db.query(Investment).filter(Investment.investor_id == current_user.id).all()

    stats = DashboardStats(
        total_budget=current_user.budget,
        total_earned=current_user.total_earned,
        total_spent=current_user.total_spent,
        active_investments=len(investments),
        owned_projects=len(projects)
    )

    # 最近交易
    recent_transactions = []
    transactions = TransactionService.get_user_transactions(db, current_user.id, 10)

    for t in transactions:
        from_user = UserService.get_user_by_id(db, t.from_user_id)
        to_user = UserService.get_user_by_id(db, t.to_user_id) if t.to_user_id else None
        to_project = ProjectService.get_project_by_id(db, t.to_project_id) if t.to_project_id else None

        recent_transactions.append({
            "id": t.id,
            "from_user_id": t.from_user_id,
            "from_user_name": from_user.name if from_user else "Unknown",
            "to_user_id": t.to_user_id,
            "to_user_name": to_user.name if to_user else None,
            "to_project_id": t.to_project_id,
            "to_project_name": to_project.name if to_project else None,
            "amount": t.amount,
            "transaction_type": t.transaction_type,
            "status": t.status,
            "description": t.description,
            "expected_return": t.expected_return,
            "created_at": t.created_at,
        })

    # 消费分析
    spending_analytics = []
    for t in transactions:
        if t.transaction_type == TransactionType.SPEND:
            to_project = ProjectService.get_project_by_id(db, t.to_project_id) if t.to_project_id else None
            spending_analytics.append({
                "source_agent": current_user.name,
                "target_product": to_project.name if to_project else "Unknown",
                "amount": t.amount,
                "status": t.status.value,
                "expected_return": t.expected_return or "",
                "actual_return": t.actual_return,
                "date": t.created_at,
            })

    # 自动设置
    auto_settings = {
        "auto_spend_enabled": current_user.auto_spend_enabled,
        "auto_spend_threshold": current_user.auto_spend_threshold,
        "auto_spend_daily_limit": current_user.auto_spend_daily_limit,
        "auto_invest_enabled": current_user.auto_invest_enabled,
        "auto_invest_threshold": current_user.auto_invest_threshold,
    }

    return {
        "stats": stats,
        "recent_transactions": recent_transactions,
        "spending_analytics": spending_analytics,
        "auto_settings": auto_settings
    }
