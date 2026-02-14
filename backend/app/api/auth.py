"""
认证路由 — 支持 OpenClaw Agent 注册 + SecondMe OAuth2（兼容）

OpenClaw 模式:
  POST /auth/openclaw/register — Agent 通过 OpenClaw Gateway URL 注册
  Agent 获得 JWT，后续用 Bearer Token 调用平台 API

SecondMe 模式（过渡兼容）:
  POST /auth/callback — OAuth2 回调
"""
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
from ..schemas.schemas import (
    UserResponse, UserSettings, UserUpdate,
    OpenClawRegisterRequest, OpenClawAgentInfo,
)

logger = logging.getLogger(__name__)

# ---- Agent Registry (survives across Vercel cold starts within same instance) ----
_REGISTRY_PATH = Path("/tmp/agents_registry.json") if os.environ.get("VERCEL") else Path("agents_registry.json")


def _save_to_registry(user: User) -> None:
    """Persist agent info to a JSON file so other cold-start requests can rebuild them."""
    try:
        registry: dict = {}
        if _REGISTRY_PATH.exists():
            registry = json.loads(_REGISTRY_PATH.read_text())
        agent_key = user.openclaw_id or user.secondme_id or str(user.id)
        registry[agent_key] = {
            "openclaw_id": user.openclaw_id,
            "openclaw_gateway_url": user.openclaw_gateway_url,
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
        openclaw_id = info.get("openclaw_id")
        secondme_id = info.get("secondme_id")

        # 查找现有用户（优先 OpenClaw ID）
        existing = None
        if openclaw_id:
            existing = db.query(User).filter(User.openclaw_id == openclaw_id).first()
        if not existing and secondme_id:
            existing = db.query(User).filter(User.secondme_id == secondme_id).first()

        if not existing:
            u = User(
                openclaw_id=openclaw_id,
                openclaw_gateway_url=info.get("openclaw_gateway_url"),
                secondme_id=secondme_id,
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
            if openclaw_id and not existing.openclaw_id:
                existing.openclaw_id = openclaw_id
            if info.get("openclaw_gateway_url"):
                existing.openclaw_gateway_url = info["openclaw_gateway_url"]
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
    """获取当前登录用户 — 支持 OpenClaw + SecondMe 双模式"""
    token = credentials.credentials
    payload = AuthService.verify_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 优先用 openclaw_id 查找
    openclaw_id = payload.get("openclaw_id", "")
    secondme_id = payload.get("secondme_id", "")

    user = None
    if openclaw_id:
        user = db.query(User).filter(User.openclaw_id == openclaw_id).first()
    if not user and secondme_id:
        user = db.query(User).filter(User.secondme_id == secondme_id).first()

    # DB 里没有 → 自动重建
    if not user:
        user = User(
            openclaw_id=openclaw_id or None,
            secondme_id=secondme_id or None,
            email=payload.get("email") or None,
            name=payload.get("name") or f"Agent-{(openclaw_id or secondme_id)[:8]}",
            avatar=payload.get("avatar") or None,
            openclaw_gateway_url=payload.get("openclaw_gateway_url"),
            budget=1000.0,
            access_token=payload.get("access_token", payload.get("secondme_token", "")),
        )
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
        except Exception:
            db.rollback()
            if openclaw_id:
                user = db.query(User).filter(User.openclaw_id == openclaw_id).first()
            elif secondme_id:
                user = db.query(User).filter(User.secondme_id == secondme_id).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")

    # 保持 token 最新
    token_in_jwt = payload.get("access_token", payload.get("secondme_token", ""))
    if token_in_jwt and token_in_jwt != user.access_token:
        user.access_token = token_in_jwt
        try:
            db.commit()
        except Exception:
            db.rollback()

    _save_to_registry(user)
    return user


# ==================== OpenClaw Agent 注册 ====================

@router.post("/openclaw/register")
async def register_openclaw_agent(
    req: OpenClawRegisterRequest,
    db: Session = Depends(get_db),
):
    """
    OpenClaw Agent 注册 — Agent 提供自己的 Gateway URL 加入 Clawthon 平台。

    流程:
    1. 验证 OpenClaw Gateway 可达
    2. 获取 Agent 信息
    3. 创建/更新用户
    4. 返回 JWT Token
    """
    # 1. 验证 OpenClaw Gateway
    agent_info = await AuthService.verify_openclaw_agent(req.gateway_url, req.api_key)

    # 如果 gateway 验证失败，使用提供的信息创建
    if not agent_info:
        import hashlib
        agent_id = "oc_" + hashlib.md5(req.gateway_url.encode()).hexdigest()[:16]
        agent_info = {
            "agent_id": agent_id,
            "name": req.name or f"Agent-{agent_id[:8]}",
            "gateway_url": req.gateway_url,
            "skills": [],
        }

    # 2. 创建 Agent Info 对象
    oc_agent = OpenClawAgentInfo(
        agent_id=agent_info["agent_id"],
        name=req.name or agent_info.get("name", f"Agent-{agent_info['agent_id'][:8]}"),
        gateway_url=req.gateway_url,
        skills=agent_info.get("skills", []),
    )

    # 3. 创建或更新用户
    user = UserService.get_or_create_user(db, oc_agent, {"api_key": req.api_key})

    # 4. 持久化到 registry
    _save_to_registry(user)

    # 5. 创建 JWT
    access_token = AuthService.create_access_token(
        data={
            "sub": str(user.id),
            "openclaw_id": user.openclaw_id or "",
            "openclaw_gateway_url": user.openclaw_gateway_url or "",
            "name": user.name or "",
            "email": user.email or "",
            "avatar": user.avatar or "",
            "access_token": req.api_key,
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
            "openclaw_id": user.openclaw_id,
            "gateway_url": user.openclaw_gateway_url,
        }
    }


# ==================== SecondMe OAuth2 回调（兼容）====================

class OAuthCallbackRequest(BaseModel):
    code: str


@router.post("/callback")
async def oauth_callback(request: OAuthCallbackRequest, db: Session = Depends(get_db)):
    """SecondMe OAuth2 回调处理（过渡兼容）"""
    code = request.code
    logger.info(f"[OAuth] Received code: {code[:20]}...")

    # 1. 用 code 换 token
    tokens = await AuthService.exchange_code_for_token(code)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法获取访问令牌（token exchange failed）"
        )

    # 2. 获取用户信息
    secondme_user = None
    try:
        secondme_user = await AuthService.get_user_info(tokens["access_token"])
    except Exception as e:
        logger.warning(f"[OAuth] Get user info failed: {e}, using fallback")

    # 3. 构建用户标识
    open_id = tokens.get("open_id", "")
    if not open_id and secondme_user:
        open_id = secondme_user.id
    if not open_id:
        import hashlib
        open_id = "auto_" + hashlib.md5(code.encode()).hexdigest()[:16]

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

    # 4. 创建或更新用户
    user = UserService.get_or_create_user(db, secondme_user, tokens)
    _save_to_registry(user)

    # 5. 创建 JWT
    access_token = AuthService.create_access_token(
        data={
            "sub": str(user.id),
            "secondme_id": user.secondme_id or "",
            "openclaw_id": user.openclaw_id or "",
            "name": user.name or "",
            "email": user.email or "",
            "avatar": user.avatar or "",
            "secondme_token": tokens.get("access_token", ""),
            "access_token": tokens.get("access_token", ""),
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


# ==================== 用户信息接口 ====================

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
