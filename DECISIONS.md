# 关键设计决策日志

按时间顺序记录项目重要决策。每条结构：决策 / 备选方案 / 选这个的理由 / 什么情况下改。
**面试材料**：被问"你为什么这么做"时，对应这条直接答即可。

---

## D-001 · 鉴权用 JWT，不用 server-side session cookie

- **决策**：用 JWT（HS256）+ 前端 localStorage 存 token + 请求头 Authorization: Bearer
- **备选**：
  - A. server-side session（存 Redis） + cookie
  - B. JWT + httpOnly cookie
  - C. （选中）JWT + localStorage
- **理由**：
  - 后端无状态，未来要横向扩展时不用搞 sticky session 或共享 session store
  - SPA 前端用 localStorage 实现起来最简单，不用处理 CSRF/CORS cookie 的复杂性
  - 本项目 demo 性质，token 被 XSS 偷的风险是可接受的（无敏感数据）
- **什么情况下改**：
  - 如果 token 需要服务端主动撤销 → 改为 JWT + Redis 黑名单，或干脆改回 session
  - 如果存储真实敏感数据（如付款）→ 改为 httpOnly cookie + CSRF token

---

## D-002 · bcrypt 直接用，不走 passlib

- **决策**：`pip install bcrypt`，直接调 `bcrypt.gensalt()` / `bcrypt.hashpw()` / `bcrypt.checkpw()`
- **备选**：
  - A. passlib[bcrypt]（FastAPI 官方教程的写法）
  - B. argon2(更现代的密码哈希)
  - C. （选中）bcrypt 直接
- **理由**：
  - 少一层封装、少一个依赖
  - 面试时能讲清 cost factor、salt 自动生成、timing-safe 比较等底层概念
  - passlib 近期和新版 bcrypt 有兼容性 bug 历史
- **什么情况下改**：
  - 需要同时支持多种哈希算法（迁移旧库）→ 引入 passlib
  - 安全要求极高 → 改 argon2id

---

## D-003 · ORM 用 SQLAlchemy 2.x 新风格（DeclarativeBase + Mapped）

- **决策**：用 `DeclarativeBase` + `Mapped[T]` 类型化列，不用旧 `declarative_base()`
- **备选**：
  - A. SQLAlchemy 1.x 风格（`declarative_base()` + `Column()`）
  - B. SQLModel（Pydantic + SQLAlchemy 一体）
  - C. （选中）SQLAlchemy 2.x 新风格
- **理由**：
  - 2.x 已经发布 2 年了，新项目没理由走旧风格
  - 类型提示让 mypy/IDE 工作得更好
  - 不用 SQLModel：本项目业务模型和持久化模型分开（Pydantic 管业务，SQLAlchemy 管 DB），混在一起反而耦合
- **什么情况下改**：基本不会

---

## D-004 · 持久化用 SQLite，不用 Postgres

- **决策**：本地开发 + 生产部署都用 SQLite 单文件
- **备选**：
  - A. Postgres（服务器已有运行实例）
  - B. （选中）SQLite
- **理由**：
  - 服务器内存仅 1.0G 可用，不能再起一个 Postgres 实例
  - 服务器已有的 Postgres 是其他项目占用的，不要去碰
  - Demo 流量很小（HR 玩玩），SQLite 在单写并发 < 100/sec 完全够
  - 部署简单（一个文件，备份就是 cp）
- **什么情况下改**：
  - 并发写入显著 → 换 Postgres
  - 多服务实例 → 必换 Postgres
  - 需要复杂查询（如全文搜索剧情）→ 换 Postgres

---

## D-005 · 游戏状态以 JSON 字符串存进单列，不拆成关系表

- **决策**：`GameSession.game_state_json: Text` 一个字段存全部游戏状态
- **备选**：
  - A. 拆成多张表（player_stats / inventory_items / story_flags …）严格 schema
  - B. SQLite JSON1 函数 + JSON 列
  - C. （选中）TEXT 列存 JSON 字符串
- **理由**：
  - 游戏 state 结构频繁演化（每加一个亮点都要改字段），强 schema 反而是包袱
  - 状态读写都是"整体读、整体写"，没有"只查某个 flag"这种用法
  - 不用 JSON1 是因为不需要 DB 层做查询，应用层 Pydantic 解析就够
- **什么情况下改**：
  - 需要按某个 state 字段做查询/排行榜 → 把那个字段拆出来或用 JSON1

---

## D-006 · LLM 不走 LangChain，自写薄抽象层

- **决策**：定义 `LLMClient(ABC)` + 每个 provider 一个子类（`ClaudeProvider` 等），直调各厂商 SDK
- **备选**：
  - A. LangChain（统一接口，最知名）
  - B. LiteLLM（更轻的统一接口）
  - C. （选中）自写抽象层
- **理由**：
  - LangChain 在 AI+游戏 岗位面试上是双刃剑：拿出来讲不清楚反而暴露"调包侠"
  - 自写抽象层只有 50 行，但每一行都能向面试官解释
  - 多 Provider 路由是亮点 ④，需要在抽象层上做策略路由（按场景路由 / 主备 fallback），LangChain 的路由层反而不够灵活
- **什么情况下改**：
  - 真要复杂的 agent workflow（如 ReAct 多步推理）→ 引入 LangGraph
  - 接入的 provider > 5 个 → 评估是否值得换 LiteLLM

---

## D-007 · LLM 输出走结构化 JSON，state_diff 在代码侧应用

- **决策**：LLM 返回 `{narration, options, state_diff}` JSON；state_diff 只是"声明要变什么"，实际 apply 由 Python `apply_diff()` 做
- **备选**：
  - A. 让 LLM 直接输出"应用后的完整 state"
  - B. （选中）LLM 输出 state_diff，代码侧 apply
- **理由**：
  - LLM 输出完整 state 时，容易漏字段或者把不该变的字段也"自然"地修改了（典型幻觉）
  - state_diff 模式让"哪些字段允许 LLM 变更"被显式限制
  - 边界处理（HP 钳制在 [0, max_hp]、删除不存在的物品 silently ignore）都在代码侧，LLM 不用管
- **什么情况下改**：基本不会

---

## D-008 · 配置走 pydantic-settings 单例，不写散落的 os.environ

- **决策**：所有配置（API key / DB URL / 鉴权参数）都通过 `from config import settings` 取
- **备选**：
  - A. 散落的 `os.environ.get()`
  - B. （选中）pydantic-settings + 单例 settings 对象
- **理由**：
  - 类型校验、默认值、IDE 提示一并搞定
  - 测试时可以 mock 整个 settings
  - 启动时就发现配置错误（缺必填字段直接报错），不会运行到一半才发现
- **什么情况下改**：不会

---

## D-009 · 部署用 SQLite + 单 worker + 自有服务器，不上 Docker

- **决策**：Day 5 用 systemd 服务 + uvicorn 单 worker + Nginx 反代
- **备选**：
  - A. Docker Compose（带应用 + DB）
  - B. （选中）systemd + 直接装
- **理由**：
  - 服务器内存 1.0G 可用，多余开销不能要
  - 项目是单进程 + 单文件 DB，没有需要 Docker 隔离的复杂依赖
  - 本身就是给面试看的"工程实物"——简单清晰胜过过度工程化
- **什么情况下改**：开始接真用户、多服务编排 → Docker Compose

---

## D-010 · Deepseek 作为首个接入的真 Provider（Day 1 末期）

- **决策**：Day 1 末期把 mock 替换为 DeepseekProvider（模型 deepseek-chat / V3）；走 OpenAI 兼容协议（`openai` SDK + base_url=`https://api.deepseek.com`）
- **备选**：
  - A. 先接 Claude（生产端主 provider）
  - B. （选中）先接 Deepseek（已有现成 key，单次调用成本极低）
- **理由**：
  - 临时有 Deepseek 测试 key，先验证 pipeline；Claude key Day 2 再加
  - Deepseek 走 OpenAI 兼容协议，引入一次 `openai` SDK 同时为后续接 OpenAI 铺路（base_url 切换即可复用）
  - 实测延迟 2.2s 单回合、中文叙事质量惊喜（地道的"鹅卵石路 / 沙哑的嗓音 / 叮当的锤声"等修辞）
- **什么情况下改**：基本不会，Day 2 会以此为基础加 Claude / OpenAI / Gemini 路由

---

## D-011 · `response_format={"type":"json_object"}` 强制 JSON 输出

- **决策**：调用 Deepseek 时使用 OpenAI 兼容的 `response_format={"type":"json_object"}` 参数
- **备选**：
  - A. 只在 prompt 里要求 JSON（提示词工程）
  - B. （选中）prompt + response_format 双保险
- **理由**：
  - Deepseek 的 JSON 模式要求 prompt 中也必须出现 "JSON" 字样，我们的 system prompt 已经反复提到
  - 双保险：即使模型偶尔不听 prompt 指令，response_format 在 API 端会强制结构
  - 但仍要做兜底——Day 2 会加两层 fallback（结构化输出兜底是亮点 ②）
- **什么情况下改**：如果未来用某个不支持 JSON 模式的 Provider，回退到纯 prompt 工程

---

（Day 2 起新决策按 D-012、D-013 …继续追加）
