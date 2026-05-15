"""
FastAPI 应用主入口
==================
路由划分:
  /auth/*       注册、登录、查当前用户（auth.py）
  /game/*       游戏核心循环、存档管理（本文件）
  /health       健康检查（部署期 Nginx 用）

运行:
  开发: uvicorn main:app --reload --port 8000
  生产: uvicorn main:app --host 0.0.0.0 --port 9001 --workers 1
"""

from typing import Annotated, List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth
from config import settings
from db import GameSession, User, get_db, init_db
from engine import (
    DeepseekProvider,
    LLMClient,
    LLMRouter,
    MockLLMClient,
    ZhipuProvider,
    play_turn,
    set_llm_client,
)
from state import GameState, default_state


app = FastAPI(
    title="AI Dungeon Master",
    description="LLM 驱动的文字冒险游戏",
    version="0.1.0",
)

# CORS：前端在 5173 端口（Vite 默认），生产环境填实际域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载 auth 路由
app.include_router(auth.router)


# 启动时建表（开发期友好；生产应该走 alembic migration）
# 启动时同时根据 settings 选择 LLM client
@app.on_event("startup")
def on_startup():
    init_db()
    _select_llm_client()


def _build_provider(name: str) -> Optional[LLMClient]:
    """
    根据名字构造单个 Provider 实例。
    没有对应 API key 时返回 None。
    """
    name = name.lower()
    if name == "deepseek" and settings.DEEPSEEK_API_KEY:
        return DeepseekProvider(api_key=settings.DEEPSEEK_API_KEY, model=settings.DEFAULT_DEEPSEEK_MODEL)
    if name == "zhipu" and settings.ZHIPU_API_KEY:
        return ZhipuProvider(api_key=settings.ZHIPU_API_KEY, model=settings.DEFAULT_ZHIPU_MODEL)
    if name == "mock":
        return MockLLMClient()
    return None


def _select_llm_client():
    """
    根据 settings.LLM_PRIMARY / LLM_BACKUP 构造 LLMRouter。
    Provider 构造失败（如 API key 缺失）时回退到 MockLLMClient。
    """
    primary = _build_provider(settings.LLM_PRIMARY)
    backup = _build_provider(settings.LLM_BACKUP) if settings.LLM_BACKUP else None

    if primary is None:
        print(f"[LLM] primary={settings.LLM_PRIMARY} not available; falling back to Mock")
        set_llm_client(MockLLMClient())
        return

    if backup is None:
        print(f"[LLM] primary={settings.LLM_PRIMARY} (no backup); single provider mode")
        set_llm_client(primary)
        return

    router = LLMRouter(primary=primary, backup=backup)
    print(f"[LLM] Router: primary={settings.LLM_PRIMARY}({settings.DEFAULT_DEEPSEEK_MODEL if settings.LLM_PRIMARY == 'deepseek' else '...'}) + backup={settings.LLM_BACKUP}")
    set_llm_client(router)


# ===== 健康检查 =====

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


# ===== 游戏路由 =====

class CreateSessionRequest(BaseModel):
    title: str = "未命名冒险"


class SessionSummary(BaseModel):
    """会话列表用的紧凑结构。"""
    id: int
    title: str
    turn_count: int
    location: str
    updated_at: str


class TurnRequest(BaseModel):
    user_input: str


class TurnResponse(BaseModel):
    narration: str
    options: List[str]
    state: GameState


@app.post("/game/sessions", response_model=SessionSummary, status_code=201)
def create_session(
    req: CreateSessionRequest,
    user: Annotated[User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """新建一份存档（开局状态）。"""
    initial = default_state()
    sess = GameSession(
        user_id=user.id,
        title=req.title,
        game_state_json=initial.model_dump_json(),
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return SessionSummary(
        id=sess.id,
        title=sess.title,
        turn_count=initial.turn_count,
        location=initial.scene.location,
        updated_at=sess.updated_at.isoformat(),
    )


@app.get("/game/sessions", response_model=List[SessionSummary])
def list_sessions(
    user: Annotated[User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """列出当前用户的所有存档。"""
    sessions = (
        db.query(GameSession)
        .filter(GameSession.user_id == user.id)
        .order_by(GameSession.updated_at.desc())
        .all()
    )
    result = []
    for s in sessions:
        state = GameState.model_validate_json(s.game_state_json)
        result.append(SessionSummary(
            id=s.id,
            title=s.title,
            turn_count=state.turn_count,
            location=state.scene.location,
            updated_at=s.updated_at.isoformat(),
        ))
    return result


@app.get("/game/sessions/{session_id}", response_model=GameState)
def get_session_state(
    session_id: int,
    user: Annotated[User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """取某份存档的完整 state（前端打开存档时调用）。"""
    sess = db.get(GameSession, session_id)
    if not sess or sess.user_id != user.id:
        raise HTTPException(status_code=404, detail="存档不存在")
    return GameState.model_validate_json(sess.game_state_json)


@app.post("/game/sessions/{session_id}/turn", response_model=TurnResponse)
def play_one_turn(
    session_id: int,
    req: TurnRequest,
    user: Annotated[User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    玩一回合的核心接口：
      读 state → 调 engine.play_turn → 存新 state → 返回 (叙事, 选项, 新 state)
    """
    sess = db.get(GameSession, session_id)
    if not sess or sess.user_id != user.id:
        raise HTTPException(status_code=404, detail="存档不存在")

    current_state = GameState.model_validate_json(sess.game_state_json)

    try:
        result = play_turn(req.user_input, current_state)
    except Exception as e:
        # Day 2 会替换为更细致的错误处理（结构化输出兜底）
        raise HTTPException(status_code=500, detail=f"游戏引擎错误: {type(e).__name__}: {e}")

    # 持久化新 state
    sess.game_state_json = result.state.model_dump_json()
    db.commit()

    return TurnResponse(
        narration=result.narration,
        options=result.options,
        state=result.state,
    )


@app.delete("/game/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: int,
    user: Annotated[User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    sess = db.get(GameSession, session_id)
    if not sess or sess.user_id != user.id:
        raise HTTPException(status_code=404, detail="存档不存在")
    db.delete(sess)
    db.commit()
    return None
