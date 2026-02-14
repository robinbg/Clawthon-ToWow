"""
认证服务 — 支持 OpenClaw + SecondMe 双模式

OpenClaw 模式: 通过 API Key 验证 Agent 身份
SecondMe 模式: 通过 OAuth2 + Access Token 验证（过渡兼容）
"""
import httpx
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext

from ..core.config import get_settings
from ..models.database import User
from ..schemas.schemas import SecondMeUserInfo, OpenClawAgentInfo

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """认证服务（OpenClaw + SecondMe 兼容）"""

    @staticmethod
    async def verify_openclaw_agent(gateway_url: str, api_key: str = "") -> Optional[Dict[str, Any]]:
        """验证 OpenClaw Agent 身份 — 通过 Gateway 健康检查获取 Agent 信息"""
        try:
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{gateway_url.rstrip('/')}/api/status",
                    headers=headers,
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "agent_id": data.get("agentId", data.get("id", "")),
                        "name": data.get("name", "OpenClaw Agent"),
                        "gateway_url": gateway_url,
                        "skills": data.get("skills", []),
                    }
        except Exception:
            pass
        return None

    @staticmethod
    async def exchange_code_for_token(code: str) -> Optional[Dict[str, Any]]:
        """用授权码交换访问令牌（SecondMe 兼容）"""
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

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                data=form_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            body = response.json()
            logger.info(f"Token exchange response status: {response.status_code}")

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
        """获取用户信息（SecondMe 兼容）"""
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
    def get_or_create_user(db: Session, user_info, tokens: Dict[str, Any]) -> User:
        """获取或创建用户 — 兼容 OpenClaw Agent Info 和 SecondMe User Info"""
        # 判断是 OpenClaw 还是 SecondMe 用户
        if isinstance(user_info, OpenClawAgentInfo):
            return UserService._get_or_create_openclaw_user(db, user_info, tokens)
        else:
            return UserService._get_or_create_secondme_user(db, user_info, tokens)

    @staticmethod
    def _get_or_create_openclaw_user(db: Session, agent_info: 'OpenClawAgentInfo', tokens: Dict[str, Any]) -> User:
        """获取或创建 OpenClaw Agent 用户"""
        user = db.query(User).filter(User.openclaw_id == agent_info.agent_id).first()

        if not user:
            # 也检查是否已经以 secondme_id 存在（可能是迁移用户）
            user = User(
                openclaw_id=agent_info.agent_id,
                openclaw_gateway_url=agent_info.gateway_url,
                name=agent_info.name or f"Agent-{agent_info.agent_id[:8]}",
                budget=1000.0,
                access_token=tokens.get("api_key", ""),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            if agent_info.gateway_url:
                user.openclaw_gateway_url = agent_info.gateway_url
            if tokens.get("api_key"):
                user.access_token = tokens["api_key"]
            db.commit()

        return user

    @staticmethod
    def _get_or_create_secondme_user(db: Session, secondme_user: SecondMeUserInfo, tokens: Dict[str, Any]) -> User:
        """获取或创建 SecondMe 用户（过渡兼容）"""
        user = db.query(User).filter(User.secondme_id == secondme_user.id).first()

        if not user:
            user = User(
                secondme_id=secondme_user.id,
                email=secondme_user.email or None,
                name=secondme_user.name or f"Agent-{secondme_user.id[:8]}",
                avatar=secondme_user.avatar,
                budget=1000.0,
                access_token=tokens.get("access_token"),
                refresh_token=tokens.get("refresh_token"),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
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
