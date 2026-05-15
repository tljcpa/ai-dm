"""
数据库层
========
- 使用 SQLAlchemy 2.x 新风格（DeclarativeBase + Mapped 类型化列）
- SQLite 文件持久化（路径由 DATABASE_URL 控制）
- 两张表：User（账号）+ GameSession（玩家的游戏存档）
- 关键设计：游戏状态以 JSON 字符串存进 game_state_json 字段
  原因：游戏状态结构频繁演化，强 schema 反而成为负担；面试可讲"什么时候 JSON 列比关系列合适"
"""

from datetime import datetime
from typing import Generator, List

from sqlalchemy import ForeignKey, String, Text, create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类（SQLAlchemy 2.x 推荐写法）"""
    pass


class User(Base):
    """用户表：用户名 + bcrypt 哈希后的密码"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # bcrypt 哈希后是 60 字节 ASCII 字符串，留 128 留余量
    hashed_password: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # 一个用户多个存档
    sessions: Mapped[List["GameSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class GameSession(Base):
    """游戏存档表：每条记录是一个玩家的某一次游戏会话"""
    __tablename__ = "game_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # 存档显示名（如"勇者的第一次冒险"），玩家可改
    title: Mapped[str] = mapped_column(String(128), default="未命名冒险")
    # 完整的 GameState（Pydantic）序列化为 JSON 字符串
    # 为什么不拆成多列？因为 state 结构频繁演化，JSON 列演化无痛
    game_state_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped[User] = relationship(back_populates="sessions")


# SQLite 单连接模式：connect_args 是 SQLite 在多线程下必须加的
# 生产环境换 Postgres 时这行删掉即可
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """建表。开发期反复调用安全（已存在的表不会重建）"""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI 依赖：每个请求一个 DB session，请求结束自动关闭
    用法：def my_route(db: Session = Depends(get_db)): ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
