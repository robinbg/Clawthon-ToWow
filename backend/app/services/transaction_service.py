import json
from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from ..models.database import Transaction, User, Project, TransactionStatus, TransactionType
from ..schemas.schemas import TransactionCreate, SpendingRequest, TransactionApproval


class TransactionService:
    """交易服务 - 处理CP的流动"""

    @staticmethod
    def get_user_daily_spending(db: Session, user_id: int) -> float:
        """获取用户当日消费总额"""
        today = datetime.utcnow().date()
        start_of_day = datetime.combine(today, datetime.min.time())

        transactions = db.query(Transaction).filter(
            Transaction.from_user_id == user_id,
            Transaction.transaction_type == TransactionType.SPEND,
            Transaction.status.in_([TransactionStatus.APPROVED, TransactionStatus.AUTO_APPROVED]),
            Transaction.created_at >= start_of_day
        ).all()

        return sum(t.amount for t in transactions)

    @staticmethod
    def create_spending_request(
        db: Session,
        from_user_id: int,
        request: SpendingRequest
    ) -> Transaction:
        """创建消费申请"""
        user = db.query(User).filter(User.id == from_user_id).first()
        project = db.query(Project).filter(Project.id == request.target_project_id).first()

        if not user or not project:
            raise ValueError("用户或项目不存在")

        # 检查余额
        if user.budget < request.amount:
            raise ValueError("CP余额不足")

        # 检查是否满足自动支付条件
        daily_spent = TransactionService.get_user_daily_spending(db, from_user_id)

        is_auto = (
            user.auto_spend_enabled and
            request.amount <= user.auto_spend_threshold and
            (daily_spent + request.amount) <= user.auto_spend_daily_limit
        )

        status = TransactionStatus.AUTO_APPROVED if is_auto else TransactionStatus.PENDING

        transaction = Transaction(
            from_user_id=from_user_id,
            to_project_id=request.target_project_id,
            amount=request.amount,
            transaction_type=TransactionType.SPEND,
            status=status,
            description=request.reason,
            expected_return=request.expected_return,
            risk_assessment=request.risk,
        )

        db.add(transaction)

        if is_auto:
            # 自动批准，立即扣款
            user.budget -= request.amount
            user.total_spent += request.amount
            project.funding_pool += request.amount
            project.usage_count += 1

        db.commit()
        db.refresh(transaction)
        return transaction

    @staticmethod
    def approve_transaction(
        db: Session,
        transaction_id: int,
        approver_id: int,
        approval: TransactionApproval
    ) -> Optional[Transaction]:
        """审批交易"""
        transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()

        if not transaction or transaction.status != TransactionStatus.PENDING:
            return None

        user = db.query(User).filter(User.id == transaction.from_user_id).first()

        if approval.approved:
            # 批准交易
            transaction.status = TransactionStatus.APPROVED
            transaction.approved_by = approver_id
            transaction.approved_at = datetime.utcnow()

            # 扣款
            user.budget -= transaction.amount
            user.total_spent += transaction.amount

            # 如果是消费到项目
            if transaction.to_project_id:
                project = db.query(Project).filter(Project.id == transaction.to_project_id).first()
                if project:
                    project.funding_pool += transaction.amount
                    project.usage_count += 1
        else:
            # 拒绝交易
            transaction.status = TransactionStatus.REJECTED
            transaction.approved_by = approver_id
            transaction.approved_at = datetime.utcnow()

        db.commit()
        db.refresh(transaction)
        return transaction

    @staticmethod
    def get_pending_transactions(db: Session, user_id: int) -> List[Transaction]:
        """获取待审批的交易（用户是目标项目所有者）"""
        # 获取用户拥有的项目
        projects = db.query(Project).filter(Project.owner_id == user_id).all()
        project_ids = [p.id for p in projects]

        # 获取待审批的消费申请（针对这些项目）
        transactions = db.query(Transaction).filter(
            Transaction.to_project_id.in_(project_ids),
            Transaction.status == TransactionStatus.PENDING
        ).all()

        return transactions

    @staticmethod
    def get_user_transactions(db: Session, user_id: int, limit: int = 50) -> List[Transaction]:
        """获取用户的交易记录"""
        return db.query(Transaction).filter(
            Transaction.from_user_id == user_id
        ).order_by(Transaction.created_at.desc()).limit(limit).all()

    @staticmethod
    def get_transaction_by_id(db: Session, transaction_id: int) -> Optional[Transaction]:
        return db.query(Transaction).filter(Transaction.id == transaction_id).first()


class InvestmentService:
    """投资服务"""

    @staticmethod
    def create_investment_proposal(
        db: Session,
        investor_id: int,
        project_id: int,
        amount: float,
        reason: str,
        expected_roi: float,
        risk_level: str
    ):
        """创建投资提案"""
        from ..models.database import Investment

        investor = db.query(User).filter(User.id == investor_id).first()
        project = db.query(Project).filter(Project.id == project_id).first()

        if not investor or not project:
            raise ValueError("投资者或项目不存在")

        if investor.budget < amount:
            raise ValueError("CP余额不足")

        # 计算股权（简化版：估值 = 最近30天收入 × 5）
        monthly_revenue = project.total_revenue
        valuation = monthly_revenue * 5 if monthly_revenue > 0 else 1000.0
        equity_percentage = amount / valuation if valuation > 0 else 0

        # 检查是否自动投资
        is_auto = investor.auto_invest_enabled and amount <= investor.auto_invest_threshold

        investment = Investment(
            investor_id=investor_id,
            project_id=project_id,
            amount=amount,
            equity_percentage=equity_percentage,
            investment_reason=reason,
            expected_roi=expected_roi,
            risk_level=risk_level,
            is_auto_invest=is_auto
        )

        db.add(investment)

        if is_auto:
            # 自动执行投资
            investor.budget -= amount
            investor.total_spent += amount
            project.funding_pool += amount
            project.valuation = valuation + amount

        db.commit()
        db.refresh(investment)
        return investment
