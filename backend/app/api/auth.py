import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from ..models.database import get_db, User
from ..services.auth_service import AuthService, UserService
from ..schemas.schemas import UserResponse, UserSettings, UserUpdate

logger = logging.getLogger(__name__)

# ---- Agent Registry (survives across Vercel cold starts within same instance) ----
_REGISTRY_PATH = Path("/tmp/agents_registry.json") if os.environ.get("VERCEL") else Path("agents_registry.json")


def _save_to_registry(user: User) -> None:
    """Persist agent info to a JSON file so other cold-start requests can rebuild them."""
    try:
        registry: dict = {}
        if _REGISTRY_PATH.exists():
            registry = json.loads(_REGISTRY_PATH.read_text())
        registry[str(user.secondme_id)] = {
            "secondme_id": user.secondme_id,
            "name": user.name,
            "email": user.email,
            "avatar": user.avatar,
            "access_token": user.access_token,
            "budget": user.budget,
            "total_earned": user.total_earned,
            "total_spent": user.total_spent,
        }
        _REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"Failed to save agent registry: {e}")


def rebuild_all_agents_from_registry(db: Session) -> int:
    """Rebuild all known agents into DB from the registry file. Returns count of rebuilt agents."""
    if not _REGISTRY_PATH.exists():
        return 0
    try:
        registry = json.loads(_REGISTRY_PATH.read_text())
    except Exception:
        return 0
    count = 0
    for sid, info in registry.items():
        existing = db.query(User).filter(User.secondme_id == sid).first()
        if not existing:
            u = User(
                secondme_id=sid,
                name=info.get("name") or f"Agent-{sid[:8]}",
                email=info.get("email") or None,
                avatar=info.get("avatar"),
                access_token=info.get("access_token", ""),
                budget=info.get("budget", 1000.0),
                total_earned=info.get("total_earned", 0.0),
                total_spent=info.get("total_spent", 0.0),
            )
            db.add(u)
            count += 1
        else:
            # Update token if newer
            new_token = info.get("access_token", "")
            if new_token and new_token != existing.access_token:
                existing.access_token = new_token
    if count > 0:
        try:
            db.commit()
        except Exception:
            db.rollback()
    return count

router = APIRouter(prefix="/auth", tags=["认证"])
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """获取当前登录用户 — Vercel serverless 完全兼容，DB丢失自动重建"""
    token = credentials.credentials
    payload = AuthService.verify_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    secondme_id = payload.get("secondme_id", "")
    if not secondme_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌缺少 secondme_id",
        )

    # 1. 先从 DB 查（按 secondme_id，不用自增 id）
    user = db.query(User).filter(User.secondme_id == secondme_id).first()

    # 2. DB 里没有 → 自动从 JWT 重建（Vercel serverless DB 是临时的）
    if not user:
        user = User(
            secondme_id=secondme_id,
            email=payload.get("email") or None,
            name=payload.get("name") or f"Agent-{secondme_id[:8]}",
            avatar=payload.get("avatar") or None,
            budget=1000.0,
            access_token=payload.get("secondme_token", ""),
        )
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
        except Exception:
            db.rollback()
            # 可能并发重建，再查一次
            user = db.query(User).filter(User.secondme_id == secondme_id).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")

    # 保持 SecondMe token 最新
    sm_token = payload.get("secondme_token", "")
    if sm_token and sm_token != user.access_token:
        user.access_token = sm_token
        try:
            db.commit()
        except Exception:
            db.rollback()

    # Persist to registry so other cold-start instances can rebuild this agent
    _save_to_registry(user)

    return user


class OAuthCallbackRequest(BaseModel):
    code: str


@router.post("/callback")
async def oauth_callback(request: OAuthCallbackRequest, db: Session = Depends(get_db)):
    """SecondMe OAuth2 回调处理"""
    import logging
    logger = logging.getLogger(__name__)

    code = request.code
    logger.info(f"[OAuth] Received code: {code[:20]}...")

    # 1. 用 code 换 token
    tokens = await AuthService.exchange_code_for_token(code)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法获取访问令牌（SecondMe token exchange failed）"
        )
    logger.info(f"[OAuth] Token exchange OK, open_id: {tokens.get('open_id', 'N/A')[:10]}...")

    # 2. 获取用户信息（可能失败，但不阻塞流程）
    secondme_user = None
    try:
        secondme_user = await AuthService.get_user_info(tokens["access_token"])
    except Exception as e:
        logger.warning(f"[OAuth] Get user info failed: {e}, using fallback")

    # 3. 构建用户标识（优先用 open_id from token，其次 user info）
    open_id = tokens.get("open_id", "")
    if not open_id and secondme_user:
        open_id = secondme_user.id
    if not open_id:
        # 最后兜底：用 code 的 hash 作为唯一标识
        import hashlib
        open_id = "auto_" + hashlib.md5(code.encode()).hexdigest()[:16]

    # 构造 SecondMeUserInfo
    from ..schemas.schemas import SecondMeUserInfo
    if not secondme_user:
        secondme_user = SecondMeUserInfo(
            id=open_id,
            email="",
            name=f"Agent-{open_id[:8]}",
            avatar=None,
        )
    elif not secondme_user.id:
        secondme_user.id = open_id

    logger.info(f"[OAuth] User: id={secondme_user.id[:10]}, name={secondme_user.name}")

    # 4. 创建或更新用户
    user = UserService.get_or_create_user(db, secondme_user, tokens)

    # Persist to registry immediately on login
    _save_to_registry(user)

    # 5. 创建应用内的JWT（嵌入用户信息，应对 Vercel serverless 临时 DB）
    access_token = AuthService.create_access_token(
        data={
            "sub": str(user.id),
            "secondme_id": user.secondme_id,
            "name": user.name or "",
            "email": user.email or "",
            "avatar": user.avatar or "",
            "secondme_token": tokens.get("access_token", ""),
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "avatar": user.avatar,
            "budget": user.budget,
        }
    }


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "avatar": current_user.avatar,
        "bio": current_user.bio,
        "budget": current_user.budget,
        "total_earned": current_user.total_earned,
        "total_spent": current_user.total_spent,
        "skills": eval(current_user.skills) if current_user.skills else [],
        "specialties": eval(current_user.specialties) if current_user.specialties else [],
        "settings": {
            "auto_spend_enabled": current_user.auto_spend_enabled,
            "auto_spend_threshold": current_user.auto_spend_threshold,
            "auto_spend_daily_limit": current_user.auto_spend_daily_limit,
            "auto_invest_enabled": current_user.auto_invest_enabled,
            "auto_invest_threshold": current_user.auto_invest_threshold,
        },
        "created_at": current_user.created_at,
    }


@router.put("/me")
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新用户信息"""
    update_data = data.dict(exclude_unset=True)

    # 处理列表字段
    if "skills" in update_data and update_data["skills"]:
        update_data["skills"] = str(update_data["skills"])
    if "specialties" in update_data and update_data["specialties"]:
        update_data["specialties"] = str(update_data["specialties"])

    user = UserService.update_user_settings(db, current_user.id, update_data)
    return {"message": "更新成功"}


@router.put("/settings")
async def update_settings(
    settings: UserSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新用户自动设置"""
    user = UserService.update_user_settings(db, current_user.id, settings.dict())
    return {"message": "设置已更新", "settings": settings}
