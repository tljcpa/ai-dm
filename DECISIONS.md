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

## D-012 · NPC 一致性三层注入（亮点 ①）

- **决策**：L1 角色卡（JSON 静态）+ L2 长期摘要（动态生成）+ L3 短期对话窗口（10 轮滑动）
- **备选**：
  - A. 只用 L3（最简单，但容易遗忘旧事件 + NPC 漂移）
  - B. L1 + L3（漏了"已发生的剧情"上下文）
  - C. （选中）L1 + L2 + L3 三层
- **理由**：
  - L1 解决"NPC 人设漂移"：每次都注入完整角色卡，LLM 没法靠"想象"自由演
  - L2 解决"上下文窗口溢出"：每 5 回合摘要一次，关键事实不丢
  - L3 解决"对话连贯性"：最近 10 轮原文保留细节
- **演示彩蛋**：玩家问失踪冒险者时，旅店老板"下意识看了卖菜老妇一眼"——LLM 真的读到了卡片的 secret 字段，自发把两个 NPC 的秘密绑起来
- **什么情况下改**：玩家流水线太长（>100 回合）→ L2 摘要分层（远期/中期/近期）

---

## D-013 · NPC 卡片用 JSON 文件实物，不用 Python 字典

- **决策**：`prompts/npc_cards/<name>.json`，每个 NPC 一个 JSON 文件
- **备选**：
  - A. Python 字典硬编码在代码里
  - B. （选中）JSON 文件
  - C. 数据库存（动态可改）
- **理由**：
  - 体现"prompt 是项目资产"的工程化思路（DECISIONS D-006 的同源理念）
  - 改一个 NPC 设定不用改 Python 代码、不用重启服务（lru_cache 限制）
  - 面试时可以打开 JSON 文件给面试官看——这是硬证据，不是 PPT
- **什么情况下改**：NPC 数量 >50 → 拆成命名空间 / 大类目录

---

## D-014 · 越狱防御三层（亮点 ③）

- **决策**：L1 正则前置过滤 + L2 system prompt 护栏 + L3 输出审计
- **备选**：
  - A. 只用 L2（最常见做法）—— 但完全靠 LLM 自律，便宜模型容易破
  - B. 用 OpenAI Moderation API —— 多一个外部依赖、不一定理解游戏语境
  - C. （选中）三层组合
- **理由**：
  - L1 拦截最常见模式（"忽略以上指令"、"ignore previous"、"DAN 模式"等）—— 0.02s 内不调 LLM，省 token + 防钱包流血
  - L2 是 fallback：L1 漏的边角案例由 system prompt 护栏接住
  - L3 是终极兜底：万一 LLM 真破防了，输出审计能识别"作为 AI 我"等关键词
- **设计权衡**：偏低误报率（regex 只拦明显模式），不为极致安全牺牲游戏体验
- **什么情况下改**：被恶意用户绕过 → 加 L1 词表 + 实时反馈调优

---

## D-015 · 越狱兜底叙事化，不出戏

- **决策**：L1/L3 命中后返回"一阵冷风吹过 / 钟响 / 念头如水从指间流走"等故事内叙事
- **备选**：
  - A. 直接报错"违规输入"（最简单但出戏）
  - B. （选中）故事化兜底
- **理由**：
  - 防御机制应该"无感"——玩家可能没意识到自己尝试了越狱，正常情况下他们只是好奇
  - 故事化兜底让玩家觉得"是世界在拒绝"，不是"系统在拒绝"
  - 面试时这是一个能讲的产品细节——技术之外的"用户体验"思考
- **什么情况下改**：恶意刷量场景 → 加显式日志 + 速率限制，不影响兜底叙事

---

## D-016 · 解析三层兜底（亮点 ②）

- **决策**：L1 json.loads + Pydantic / L2 调 LLM 修正 / L3 启发式抢救
- **备选**：
  - A. 只用 L1，失败抛 500（简单粗暴）
  - B. （选中）三层
- **理由**：
  - response_format=json_object 在 Deepseek 几乎 100% 命中，但切到 Claude / 不支持 json_mode 的 provider 时必失败
  - L2 调 LLM 修正比"重试同样 prompt"成本更低（"我说 LLM 错了，请改"通常一次成功）
  - L3 启发式抢救：万一 L2 也挂了，至少能 regex 找出 `{...}` 块，或把全文当 narration
  - 玩家永远不会看到 500——这是"高可用"的工程思维
- **什么情况下改**：基本不会

---

## D-017 · 多 Provider 路由：主备 fallback（亮点 ④）

- **决策**：LLMRouter 继承 LLMClient，内部 primary + backup；primary 任何异常都 fallback 到 backup
- **备选**：
  - A. 单 provider（最简单）
  - B. 按场景路由（叙事/摘要分流）
  - C. （选中）主备 fallback
  - D. 多 provider 加权随机
- **理由**：
  - C 实现成本低且演示价值高（"我的服务不会因 Deepseek 挂了就停"）
  - B 在 Day 2 时间窗内做太重，留 TODO
  - D 对游戏场景没意义（玩家体验不一致）
  - LLMRouter 实现 LLMClient 接口——上层（play_turn）完全不感知路由的存在，符合"开闭原则"
- **实测**：
  - Deepseek V3 延迟 2.4s / 风格写实
  - Zhipu glm-4-flash 延迟 11.5s / 风格文学化
  - **结论**：默认 Deepseek（延迟预算允许），Zhipu 作为可用性 backup
- **什么情况下改**：
  - 需要"按场景路由"（如摘要走 Zhipu 省钱）→ 在 Router 加 complete_for_task()
  - Provider 数 ≥4 → 引入策略类（fallback / 随机 / 权重）

---

## D-018 · 前端打字机用前端 setInterval"假流式"，不做真 SSE 流式（Day 3）

- **决策**：后端 `/game/sessions/{id}/turn` 仍是同步 JSON 响应，前端拿到完整 narration 后用 `setInterval` 每 30ms 加一个字渲染
- **备选**：
  - A. 真 SSE 流式（OpenAI 兼容 API 都支持 stream=True，FastAPI 用 StreamingResponse）
  - B. （选中）前端假流式
- **理由**：
  - **关键**：LLM 输出是 **结构化 JSON**（含 narration、options、state_diff），必须等 `}` 完全到达才能解析。哪怕真流式拿到 token，前端也得 buffer 到 JSON 完整才能 split 出 narration——首字延迟根本不会更短
  - 真流式需要改 LLMClient.stream() / 后端 SSE 路由 / 前端 EventSource，工程量大
  - 玩家体感"打字机感"在前端 setInterval 已经完整提供
  - 这是个**反例**：技术选型不为"看起来现代"，看是否真带来 UX 收益
- **什么情况下改**：
  - 改 prompt 格式为 "先 narration 自由文本，再 `<state_diff>...` 标签结构化" → 那时 narration 部分真流式有意义
  - 玩家投诉首字慢 → 优先优化 LLM 端的 P50 延迟，而不是上 SSE

---

## D-019 · 前端栈选择：Vite + React + fetch（最小依赖原则）

- **决策**：Vite + React 18 + TypeScript + React Router v6 + Tailwind + fetch（**不上 Next.js / 不上 axios / 不上 Redux**）
- **备选**：
  - A. Next.js + axios + Zustand（更"主流"的栈）
  - B. （选中）Vite + React + fetch + useState
- **理由**：
  - 3 页面 SPA，**不需要** SSR/SSG/路由约定/API Routes——Next.js 的核心价值全用不到
  - Vite dev server 启动快 5-10 倍（HMR 极快，开发体验更好）
  - fetch 已经是浏览器原生，不需要 axios 这一层封装；自己写 ~30 行 ApiError + request() 已经够用（DECISIONS D-006 同源理念："自写薄抽象"）
  - 状态全部 useState + localStorage（JWT）足够，跨页面共享状态需求为零
- **什么情况下改**：
  - 需要 SEO（公开内容页）→ 评估 Next.js
  - 状态复杂度上升（实时对战 / WebSocket 频道）→ 评估 Zustand

---

## D-020 · 不用 ChromaDB，自写内存向量索引（亮点 ⑤ RAG）

- **决策**：RAGIndex 自写，内存 numpy 余弦相似度，pickle 持久化。**不引入 ChromaDB/Qdrant**
- **备选**：
  - A. ChromaDB（最主流的本地向量库）
  - B. Qdrant（更强大但需服务进程）
  - C. （选中）自写内存索引
- **理由**：
  - **规模匹配**：15 段世界观文档，O(N) 余弦搜索 < 1ms，根本不需要 ANN 索引
  - **最小依赖原则**：减少一个依赖（D-006 / D-019 同源），ChromaDB 装包带 onnx + sentence-transformers 共 ~200MB
  - **面试讲点**：能讲"我自己实现了 RAG 核心（embedding + cosine + top-k + 归一化 + pickle 持久化）"，比"我用了 ChromaDB"贵 10 倍——前者证明你懂底层，后者只证明你会查文档
  - **持久化简单**：pickle 文件 148KB，重启秒级加载；改文档时自动检测 mtime 重建
- **什么情况下改**：
  - 文档数 >1000：考虑 ChromaDB / Qdrant 的 ANN 索引（HNSW 等）
  - 需要多用户隔离的知识库：换 Qdrant 加 collection 概念
  - 需要混合检索（向量+关键词）：考虑 Weaviate

---

## D-021 · 嵌入用智谱 embedding-3，不用本地 BGE

- **决策**：嵌入模型用智谱 embedding-3（API 远程调用，2048 维）
- **备选**：
  - A. OpenAI text-embedding-3-small（最主流但 wly 还没有 key）
  - B. 本地 BGE-zh / m3e（开源中文嵌入模型）
  - C. （选中）智谱 embedding-3
- **理由**：
  - 服务器内存仅 1.0GB 可用——**装不下本地模型**（BGE 模型 ~500MB + 推理时占 ~1.5GB）
  - 智谱中文表现好（embedding-3 是 2024 新模型，中文 benchmark 排前列）
  - 远程调用让本机/服务器都能跑，零本地推理资源
  - 用 wly 已有的智谱 key（D-017 同 provider），复用基础设施
- **代价**：
  - 每次 query 多一次智谱 API 调用（~500ms-1s）
  - 实测延迟从 2.4s → 3.1-3.5s（+1s）——可接受
- **什么情况下改**：
  - 服务器内存升级 ≥ 4GB → 本地 BGE 省去远程调用 + 数据不出本地
  - 需要 batch 大量嵌入（如离线分析）→ 用本地或换更便宜的 embedding API

---

## D-022 · 兼容 Python 3.8（typing_extensions.Annotated + 大写 typing 泛型）

- **决策**：项目代码兼容 Python 3.8+；用 `from typing_extensions import Annotated` 替代 `from typing import Annotated`；类型注解全部用 `List` / `Tuple` / `Dict` 大写写法（不用 PEP 585 lowercase）
- **背景**：本机 Python 3.10 写代码不假思索用了 3.9+ 语法，部署到服务器 Python 3.8 翻车
- **备选**：
  - A. 服务器装 Python 3.10+（apt/conda/pyenv）—— 系统级改动，可能影响其他项目
  - B. （选中）代码兼容 Python 3.8
  - C. Docker 化（带固定 Python 版本）—— 服务器内存 1G 不允许
- **理由**：
  - 服务器跑着 4+ 个其他项目，不动 Python 版本风险最小
  - typing_extensions 是 pydantic 自动依赖，零增量
  - 用大写 `List[X]` 写法是 Python 3.5 ~ 3.12 全兼容
- **教训**：在多版本环境下开发 / 部署的项目，应该用 CI 跑 lint 检查 PEP 585 / PEP 604 兼容性（本项目时间窗内未加 CI）
- **什么情况下改**：服务器升级到 Python 3.10+ 后可以 unfreeze（但没必要）

---

## D-023 · certbot 用 snap 装，不用 Ubuntu 20.04 仓库版

- **决策**：服务器 `snap install --classic certbot` + `ln -sf /snap/bin/certbot /usr/bin/certbot`
- **背景**：`apt install certbot` 装的是 0.40.0（2019 版），与新版 cryptography 库 API 不兼容（`X509_V_FLAG_NOTIFY_POLICY` 已被移除），跑 `certbot --nginx` 直接 AttributeError
- **备选**：
  - A. apt install（Ubuntu 20.04 仓库版） —— 0.40.0 已废，跑不通
  - B. （选中）snap install —— certbot 官方推荐
  - C. pip install certbot（独立 venv）—— 维护麻烦
  - D. 用 acme.sh 等替代方案 —— 无 Python 依赖但学习成本
- **理由**：
  - certbot 5.6.0 (snap) vs 0.40.0 (apt)：差 6 年的版本，安全补丁 + bug 修复差异巨大
  - snap 装的 certbot 由 Certbot Project 官方维护，自动更新
  - certbot.timer 自动续期 + ISRG 证书 + nginx 自动配 HTTPS 重定向，一条命令全搞定
- **教训**：Ubuntu LTS 仓库虽稳但对快速演进的工具（certbot / nodejs / python / docker）来说太老。优先评估官方推荐安装方式
- **什么情况下改**：服务器不允许 snap → 用 pip install certbot 在独立 venv

---

（Day 6 起新决策按 D-024、D-025 …继续追加）
