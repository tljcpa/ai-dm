"""
鉴权层
======
- 注册：bcrypt 哈希密码（cost factor 12，默认）
- 登录：返回 JWT（HS256，python-jose 签）
- 中间件：get_current_user 依赖，从 Authorization: Bearer <token> 拿用户

为什么这么选：
- bcrypt 不走 passlib：少一层封装，pip 依赖少一个，面试能讲清 cost factor 的含义
- JWT 不走 cookie：前端 SPA 用 localStorage 存 token 更简单（不需要处理 CSRF/CORS cookie 的复杂性）
  代价：XSS 攻击可偷 token——本项目接受这个权衡（demo 不存储敏感数据）
- HS256 不用 RS256：单服务，无需公私钥分发；面试时讲清"如果上多节点要换 RS256"
"""

from datetime import datetime, timedelta
from typing import Annotated

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from db import User, get_db


router = APIRouter(prefix="/auth", tags=["auth"])

# OAuth2PasswordBearer 只是一个"如何提取 token"的策略，不是真的 OAuth2 流程
# 它告诉 FastAPI: 从请求头的 Authorization: Bearer xxx 里取 token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ===== Pydantic 请求/响应模型 =====

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str


# ===== 密码哈希 =====

def hash_password(plain: str) -> str:
    """
    bcrypt 哈希。salt 由 bcrypt 自动生成（每次不同），最终格式 $2b$<cost>$<salt><hash>
    cost factor 默认 12 —— 大约 250ms 一次哈希，平衡安全和体验
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """
    bcrypt 自带 timing-safe 比较，防止时间侧信道攻击
    """
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ===== JWT 签发/解析 =====

def create_access_token(user_id: int, username: str) -> str:
    """
    签发 access token。
    payload 字段：
      sub: 标准字段，subject，放 user_id
      username: 自定义，前端展示用
      exp: 过期时间戳（python-jose 自动转 UTC unix ts）
      iat: 签发时间（防 token 被人为提前生效）
    """
    now = datetime.utcnow()
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """
    FastAPI 依赖：用于受保护接口，自动验证 JWT 并返回当前 User 对象
    用法：def my_route(user: User = Depends(get_current_user)): ...
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效或过期的凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(user_id_str)
    except (JWTError, ValueError):
        raise credentials_exception

    user = db.get(User, user_id)
    if user is None:
        raise credentials_exception
    return user


# ===== 路由 =====

@router.post("/register", response_model=UserResponse, status_code=201)
def register(req: RegisterRequest, db: Annotated[Session, Depends(get_db)]):
    # 用户名唯一性检查
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(username=req.username, hashed_password=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse(id=user.id, username=user.username)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Annotated[Session, Depends(get_db)]):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.hashed_password):
        # 注意：用户不存在 和 密码错误 返回同一个错误，避免账号枚举
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(user_id=user.id, username=user.username)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(user: Annotated[User, Depends(get_current_user)]):
    """当前登录用户信息（用于前端验证 token 是否还有效）"""
    return UserResponse(id=user.id, username=user.username)
