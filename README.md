# AI Dungeon Master

> LLM 驱动的文字冒险游戏。玩家用自然语言探索世界，LLM 担任 DM（地下城主）实时生成剧情、NPC 对话与谜题。
> 多用户存档、多 Provider 路由、结构化输出兜底、越狱防御。
> **本项目由 Claude Code 协作完成。** 开发过程、关键决策、prompt 演化全部留档可查。

## 工程亮点

1. **NPC 一致性三层注入** — 角色卡（静态）+ 长期记忆摘要（动态）+ 短期对话窗口（滑动）
2. **结构化输出 + 两层兜底** — JSON 解析失败 → 修正 prompt 重试 → 启发式解析
3. **越狱防御** — 输入侧规则过滤 + system prompt 护栏 + 输出审计
4. **多 LLM Provider 路由** — Claude / OpenAI / Gemini / Deepseek 等抽象层 + 主备 fallback / 按场景路由

## 技术栈

- 后端：FastAPI + SQLAlchemy 2.x + SQLite + bcrypt + python-jose（JWT）
- LLM：各厂商官方 SDK + 自写薄抽象层（**不用 LangChain**）
- 前端：Vite + React + TS + Tailwind + SSE 流式
- 部署：Nginx + systemd + Let's Encrypt

## 本地开发

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 填入 SECRET_KEY 和 LLM API key
uvicorn main:app --reload --port 8000
```

## 工程化产物（面试用）

- `DECISIONS.md` — 关键设计决策日志（决策 / 备选 / 选择理由）
- `WORKFLOW.md` — 用 CC 完成此项目的工作流方法论
- `backend/prompts/` — 所有 prompt 实物（含演化注释）

## Demo

`https://<域名>` — Day 5 上线后填入
