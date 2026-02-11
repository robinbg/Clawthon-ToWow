import httpx
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext

from ..core.config import get_settings
from ..models.database import User
from ..schemas.schemas import SecondMeUserInfo

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """SecondMe OAuth2 认证服务"""

    @staticmethod
    async def exchange_code_for_token(code: str) -> Optional[Dict[str, Any]]:
        """用授权码交换访问令牌（SecondMe 实际接口）"""
        api_base = settings.SECONDME_API_BASE.strip()
        url = f"{api_base}/gate/lab/api/oauth/token/code"

        form_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.SECONDME_REDIRECT_URI.strip(),
            "client_id": settings.SECONDME_CLIENT_ID.strip(),
            "client_secret": settings.SECONDME_CLIENT_SECRET.strip(),
        }

        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Token exchange URL: {url}")
        logger.info(f"Token exchange redirect_uri: {form_data['redirect_uri']}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                data=form_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            body = response.json()
            logger.info(f"Token exchange response status: {response.status_code}, body: {str(body)[:500]}")

            if response.status_code == 200 and body.get("code") == 0:
                data = body.get("data", {})
                return {
                    "access_token": data.get("accessToken") or data.get("access_token"),
                    "refresh_token": data.get("refreshToken") or data.get("refresh_token"),
                    "open_id": data.get("openId") or data.get("open_id", ""),
                    "expires_in": data.get("expiresIn") or data.get("expires_in", 7200),
                }
            return None

    @staticmethod
    async def get_user_info(access_token: str) -> Optional[SecondMeUserInfo]:
        """获取SecondMe用户信息（SecondMe 实际接口）"""
        api_base = settings.SECONDME_API_BASE.strip()
        url = f"{api_base}/gate/lab/api/secondme/user/info"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )

            body = response.json()

            if response.status_code == 200 and (body.get("code") is None or body.get("code") == 0):
                data = body.get("data", body)
                return SecondMeUserInfo(
                    id=data.get("openId") or data.get("open_id") or data.get("email", ""),
                    email=data.get("email", ""),
                    name=data.get("name") or data.get("nickname", ""),
                    avatar=data.get("avatar") or data.get("avatarUrl"),
                )
            return None

    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """创建JWT访问令牌"""
        to_encode = data.copy()
        expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")

    @staticmethod
    def verify_token(token: str) -> Optional[Dict[str, Any]]:
        """验证JWT令牌"""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            return payload
        except JWTError:
            return None


class UserService:
    """用户管理服务"""

    @staticmethod
    def get_or_create_user(db: Session, secondme_user: SecondMeUserInfo, tokens: Dict[str, Any]) -> User:
        """获取或创建用户"""
        user = db.query(User).filter(User.secondme_id == secondme_user.id).first()

        if not user:
            # 新用户，创建并分配初始预算
            user = User(
                secondme_id=secondme_user.id,
                email=secondme_user.email or None,  # 空字符串存 None 避免 unique 冲突
                name=secondme_user.name or f"Agent-{secondme_user.id[:8]}",
                avatar=secondme_user.avatar,
                budget=1000.0,  # 初始CP
                access_token=tokens.get("access_token"),
                refresh_token=tokens.get("refresh_token"),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            # 更新 token 和用户信息
            user.access_token = tokens.get("access_token")
            user.refresh_token = tokens.get("refresh_token")
            if secondme_user.name and secondme_user.name != user.name:
                user.name = secondme_user.name
            if secondme_user.avatar:
                user.avatar = secondme_user.avatar
            db.commit()

        return user

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def update_user_settings(db: Session, user_id: int, settings_data: Dict[str, Any]) -> Optional[User]:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            for key, value in settings_data.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            db.commit()
            db.refresh(user)
        return user
