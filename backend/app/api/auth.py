from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from ..models.database import get_db, User
from ..services.auth_service import AuthService, UserService
from ..schemas.schemas import UserResponse, UserSettings, UserUpdate

router = APIRouter(prefix="/auth", tags=["认证"])
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """获取当前登录用户"""
    token = credentials.credentials
    payload = AuthService.verify_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌内容",
        )

    user = UserService.get_user_by_id(db, int(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    return user


class OAuthCallbackRequest(BaseModel):
    code: str


@router.post("/callback")
async def oauth_callback(request: OAuthCallbackRequest, db: Session = Depends(get_db)):
    """SecondMe OAuth2 回调处理"""
    code = request.code
    # 1. 用 code 换 token
    tokens = await AuthService.exchange_code_for_token(code)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法获取访问令牌"
        )

    # 2. 获取用户信息
    secondme_user = await AuthService.get_user_info(tokens["access_token"])
    if not secondme_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法获取用户信息"
        )

    # 3. 创建或更新用户
    user = UserService.get_or_create_user(db, secondme_user, tokens)

    # 4. 创建应用内的JWT
    access_token = AuthService.create_access_token(
        data={"sub": str(user.id), "email": user.email}
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
