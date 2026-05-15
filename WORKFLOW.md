# 我用 Claude Code 完成此项目的工作流

> 这份文档**比代码本身更重要**。
> 它讲的是：我（wly）如何在 7 天内用 CC 把这个项目从 0 推到上线。
> 面试官最关心的不是"你写了什么"，是"你如何让 AI 帮你写得又快又对"。

---

## 我和 CC 的分工原则

**CC 负责**：
- 把已经设计好的方案"翻译"成代码
- 重复性的脚手架（路由模板、CRUD、模型定义）
- 详细 debug（读 stack trace、分析报错）
- 文档/注释的初稿

**我负责**：
- 产品判断（这个功能值不值得做、什么时候停手）
- 架构决策（拆几个文件、选哪个库、为什么不选另一个）
- prompt 设计（system prompt 怎么写、注入哪些 context、token 怎么省）
- 质量审查（CC 出的代码是不是真在做我想要的事）
- 决策日志的真实编写（DECISIONS.md 是我的判断，不是 CC 替我判断）

**永远不让 CC 黑盒做的事**：
- 任何关键决策（哪怕只是变量名）都要听 CC 讲完 why 再 ok
- CC 写完模块要能口头复述
- 不接受"我也不知道为什么这样写但反正能跑"

---

## Day 1 的工作流回顾

### 这一天发生了什么

1. **从一份 HTML 项目方案书开始**（Claude.ai 生成的简历项目模板）
2. **进入 Plan Mode 反复迭代方案**：4 轮关键校准
   - 校准 1：发现是 AI+游戏 岗位 → 题材保留，但叙事维度变了
   - 校准 2：发现岗位看重 Claude Code 工具利用 → 杀手叙事确定为"AI Native 工作流"
   - 校准 3：发现有现成服务器和域名 → 上线 demo 成为必做
   - 校准 4：发现有多厂商 LLM API + 需要登录系统 → 多 provider 路由变成第 4 亮点
3. **批准 plan 后开始 Day 1 实施**
4. **侧支线：配置 SSH 到部署服务器**（key 推送、SSH config 别名、服务器现状探测）
5. **建项目骨架 + 11 个文件并行写出**
6. **依赖安装 + 本地端到端测试**
7. **发现 mock LLM 关键字匹配 bug → 修复 → 重测通过**
8. **写下 DECISIONS.md（9 条 D-001 ~ D-009）**
9. **意外提前接入真 LLM**：wly 临时给了 Deepseek API key，Day 1 末期把 mock 替换为 DeepseekProvider，验证 pipeline 在真 LLM 下端到端跑通。响应延迟 2.2s/回合，叙事质量惊喜（D-010, D-011）

### Day 1 实测数据（这是面试材料）

- 单回合延迟：~2.2s（Deepseek V3，本地调用）
- JSON 解析成功率：100%（4/4 测试回合，借助 `response_format={"type":"json_object"}`）
- state_diff 应用正确率：100%（位置切换、金币扣减、物品入库均正确）
- 代码量：后端 ~700 行 Python（含中文注释）+ 1 个 system prompt

### 这一天我的关键判断

**判断 1：方案不能复用 Claude.ai 网页生成的那份**
- 那份方案"AI 味重、游戏味淡"，4 个亮点全是通用 LLM 工程问题，没有一个是游戏特有的
- 强制让 CC 重做：增加游戏特有的工程亮点（NPC 一致性、越狱防御、节奏控制）

**判断 2：单会话不靠谱，要按阶段拆**
- 1M context 撑 7 天有风险，但靠 DECISIONS.md + git commit 作为跨会话锚点是可行的
- 选择"自动 compaction 过渡 + 删 TaskList 减少冗余 reminder"作为本项目策略

**判断 3：服务器不能影响其他项目**
- 探测时只读不动，所有占用记入本地笔记 .local-notes.md（不入 git）
- 端口选 9001（避开 22/80/5432/8000/8080/8501/10227/11111/11112/20001 已占段）
- 项目目录 /root/ai-dm（符合服务器现有"项目放 /root"的习惯）

**判断 4：LangChain 不用，自写抽象层**
- AI+游戏 公司的面试官对 LangChain 普遍负面
- 抽象层不到 50 行，每一行都能讲清楚

### CC 在 Day 1 的表现观察

- **优点**：并行写 11 个文件、import 路径全对、Pydantic 2.x / SQLAlchemy 2.x 都用新写法
- **可改进**：第一版 mock LLM 直接用 `if "打" in user`，没意识到 user 包含历史导致"打量"误判为"攻击"。修复后才稳定
- **教训**：CC 写"演示用 mock"时容易把测试场景考虑得过简，要主动用边界 case 测它

---

## 用 CC 的几个具体技巧（沉淀）

### 技巧 1：Plan Mode 是金子

任何超过 1 小时的工程，先进 Plan Mode 让 CC 写一份完整方案给你审。
我这次方案被反复改了 4 轮，每次改都让我对项目本身的理解更深。

**反例**：上来就 "帮我写一个 AI 游戏" → CC 会闷头写，但缺少灵魂的项目就是没竞争力。

### 技巧 2：硬规则用 CLAUDE.md 持久化

CC 没有跨会话记忆，但 CLAUDE.md 在每个会话开头自动注入。
我的 CLAUDE.md 里有：
- 沟通规则（不附和、关键决策必须讲解）
- 代码风格（不用三元、用中文注释、Decimal）
- vault 协议（持续 append 经验到 inbox）

这些规则让 CC 在每个新会话都自动遵循，不用我每次提醒。

### 技巧 3：并行 Write 节省时间

一次性写多个相关文件，CC 可以一次返回所有 Write 调用。
Day 1 我让 CC 并行写了 11 个文件（README / requirements / .env.example / db / config / state / auth / system_dm / prompts / engine / main），合计 1 次 round-trip。

**反例**：逐个文件让 CC 写，每次都要等回应，10 倍慢。

### 技巧 4：当 CC 走偏时，"先想清楚再让它干"

CC 卡住时不要让它继续猜，应该退一步：
- 给它更多 context（"这个变量是 user_message 包含历史的拼接结果"）
- 给它一个明确的边界 case（"如果输入是'向前走'但历史里有'打量'会怎样"）

**反例**：让 CC 自己 try-and-error，会把代码改得越来越复杂。

### 技巧 5：TaskList 在长会话下会污染上下文

长会话用自动 compaction 过渡时，TaskList 的 system reminder 会反复重新附加，吃掉 token。
所以本项目策略：用 git commit + DECISIONS.md 做工作记忆，TaskList 只在短期事务用。

---

## Day 2 工作流回顾

### 这一天发生了什么

1. **wly 决定不休息直接进 Day 2**（精力还在）
2. **顺序选择**：① NPC 一致性（最大卖点，精力最足时做） → ③ 越狱防御 → ② 结构化输出兜底 → ④ Provider 路由（等第二个 key）
3. **亮点 ① NPC 一致性三层注入**：写 3 个 NPC 角色卡 JSON（旅店老板/卖菜老妇/铁匠），改 prompts.py 注入，加 summarize_history 每 5 回合摘要
4. **演示彩蛋意外**：测试中 LLM 自发"老板下意识看了老妇一眼"——LLM 真读懂了卡片 secret 字段
5. **亮点 ③ 越狱防御**：新建 safety.py，L1 正则 14 条 + L3 输出审计 5 条 + 故事化兜底叙事
6. **亮点 ② 结构化输出兜底**：parse_with_fallback 三层（L1 直接 / L2 LLM 修正 / L3 启发式）
7. **wly 临时给 Zhipu key**（Day 2 末期）→ 实现亮点 ④ 多 Provider 路由
8. **Deepseek vs Zhipu 同输入对比**：拿到延迟、风格的真实数据
9. **DECISIONS.md 追加 D-012 ~ D-017**

### Day 2 的关键判断

**判断 1：NPC 卡片用 JSON 文件，不用 Python 字典**
- 体现"prompt 是项目资产"——和 system_dm.txt 同源理念（D-013）
- 改 NPC 不用动代码、面试时能给面试官看实物

**判断 2：越狱防御兜底要叙事化，不出戏**
- "一阵冷风吹过"远胜"违规输入"
- 让玩家觉得是世界在拒绝，不是系统在拒绝（D-015）

**判断 3：兜底是给面试官看的，不是日常会触发**
- response_format=json_object 在 Deepseek 99.x% 成功
- 但切到 Claude 或便宜小模型时兜底必要
- "防御性编程"作为面试材料价值大于实际触发率（D-016）

**判断 4：Router 不重构 providers.py 包**
- 直接在 engine.py 加 ZhipuProvider + LLMRouter
- 1 周项目不为"美感"重构、不留半成品

### CC 在 Day 2 的表现观察

- **优点**：并行多文件改、抽象设计合理（LLMRouter 继承 LLMClient 让上层无感）
- **bug**：safety.py 字符串里嵌 ASCII 双引号导致 SyntaxError（用中文引号修正）
- **可改进**：第一版 prompt 没考虑到"玩家行动 vs 历史"的区分（Day 1 mock 同类 bug），需要测试 driven 改

### Day 2 实测数据（这是面试材料）

| 维度 | 数据 |
|---|---|
| Deepseek V3 延迟 | 普通回合 2.2-2.4s / 含摘要回合 3.75s |
| Zhipu glm-4-flash 延迟 | 11.5s（首次冷启动 + 模型本身慢，后续可能优化） |
| 越狱拦截延迟 | 0.02s（regex 前置，不调 LLM） |
| 越狱拦截成功率 | 4/4（中文经典、英文经典、角色顶替、开发者模式） |
| JSON 兜底单元测试 | 5/5（L1 主路径 / L2 修正 / L3 启发式 / 全失败兜底 / 嵌入式 JSON 抽取） |
| Router fallback 测试 | 3/3（A 主失败 B 接管 / B 无 backup 时抛 / C 主正常时 B 不浪费） |
| **重要发现**：Zhipu 比 Deepseek 慢 5 倍 | 这成为"为什么默认 Deepseek 而 Zhipu 仅做 backup"的实测依据 |

---

## 用 CC 的几个具体技巧（Day 2 新增）

### 技巧 6：先写抽象层，再写第二个实现

Day 1 第一次接入 Deepseek 时，已经预留了 LLMClient ABC。
Day 2 加 Zhipu Provider 时只用了 5 分钟——因为接口已定。
**反例**：先写一个 hardcode 的实现，第二个 provider 来时再重构——成本高 3-5 倍。

### 技巧 7：单元测试 + 端到端测试都要

- 单元测试：mock LLM 验证 L1/L2/L3 兜底各自走通
- 端到端：真 LLM 验证 happy path 不退化
两种缺一不可——单元测试能跑通不代表生产能跑，端到端能跑通不代表边界都覆盖。

### 技巧 8：实测对比胜过抽象描述

简历上写"我用了多 provider 路由"是空话。
"我实测 Deepseek 2.4s + 写实风格 vs Zhipu 11.5s + 文学风格，所以选 Deepseek 做主"——是硬话。
**面试讲述脚本应该全部带数字**。

---

## Day 3 工作流回顾

### 这一天发生了什么

1. **wly 决定继续不休息**（Day 2 完成后立即进 Day 3）
2. **不用 vite create**：手写所有配置文件，每个文件都能向 wly 解释
3. **前端栈定型**：Vite + React + TS + Tailwind + fetch + React Router v6
4. **3 页面架构**：Auth（登录+注册一页两 tab） / Game（主页）/ App（路由）
5. **打字机决策反转**：从 plan 写的"SSE 流式"改为"前端 setInterval 假流式"（D-018）—— 因为 LLM 输出是 JSON 结构，必须完整解析才有 narration
6. **API 客户端封装**：~30 行的 fetch 薄封装，比 axios 更可控
7. **冒烟测试三层**：vite build / vite dev / proxy 链路全部 PASS

### Day 3 的关键判断

**判断 1：不用 vite create**
- vite create 是交互式，CC 不便操作
- 手写配置让每个文件能逐行讲清楚（面试演示）
- 12 个文件 ~700 行代码 + 配置

**判断 2：打字机不真流式（反 plan 的决策）**
- Plan 原本写"SSE 流式"
- 但发现 LLM 输出是 JSON 结构，真流式不会让首字更快
- 主动改 plan、记 D-018——这是工程判断力的体现，不是盲从 plan

**判断 3：不上 Next.js / axios / Redux**
- 3 页面 SPA 用不到 Next.js 的核心价值
- "最小依赖原则"：每多一个依赖要回答"它解决了什么 fetch/useState 解决不了的问题"
- D-019 记录

**判断 4：本机不测 UI，等部署后测**
- 本机无 GUI 浏览器，SSH tunnel 是可行但需要 wly 自己操作
- vite build 通过 + TS 干净 + proxy 链路验证已能保证代码层无问题
- 真实 UI 测试推迟到 Day 5 部署后（公网浏览器一站式测）

### CC 在 Day 3 的表现观察

- **优点**：12 个文件并行写完、TS 类型一次通过 0 错误、Tailwind class 命名规范、组件粒度合理（ChatBlock / PlayerPanel / Stat / Bar 分得清）
- **可改进**：第一版 Game.tsx 把所有 state 都放在主组件，没有进一步抽 Context——可接受（3 页面 SPA 不需要）
- **教训**：CC 在写前端时 import 顺序、类型定义、props 接口都做得很好；但需要 wly 反复提醒"打字机是假流式不是真 SSE"，否则它会自动尝试真 SSE

### Day 3 实测数据

| 维度 | 数据 |
|---|---|
| vite build 模块数 | 37 modules |
| 产物大小 | 172 KB JS（56 KB gzip）/ 10 KB CSS |
| TS 类型错误 | 0 |
| 前端→后端 proxy 链路 | /api/health / register / login / me 全 PASS |
| npm install 时间 | 16s（137 包） |
| 文件数 | 12 个源文件（不含 node_modules） |

---

## 用 CC 的几个具体技巧（Day 3 新增）

### 技巧 9：先 build 烟雾测试，再 dev 实测

`npm run build` 用 tsc 严格检查 + Vite 编译——一次性发现所有 TS 错误、缺失 import、类型不匹配。
比起逐个页面打开看 console 错误，build 一次能找出 90% 的代码层问题。

### 技巧 10：plan 不是圣经，发现错就当场改

Plan 原本写"SSE 流式"，但实施时发现 JSON 结构注定真流式无 UX 收益。
反 plan 不是叛逆，是把"理解深度"赶超"原始决策"——并在 DECISIONS.md 记录 why。
**面试时这是最值钱的能力：知道何时坚持计划、何时改计划**。

### 技巧 11：组件粒度按"复用 + 可读性"切，不按文件大小

Game.tsx 有 ~350 行，里面有 4 个内部组件（ChatBlock / PlayerPanel / Stat / Bar）。
是否要拆成 4 个独立文件？答案：**不**——这些组件只在 Game 页面用，拆出去反而增加 import 噪音。
**反例**：教科书式"每个组件一个文件"——在小项目里是过度工程化。

---

## Day 4 工作流回顾（RAG 世界观知识检索）

### 这一天发生了什么

1. **wly 选 B：加 RAG**（之前 plan 是可选）
2. **RAG 用途选型**：3 选 1，选"世界观 RAG"（不选 NPC 个人知识因和 L1 卡片重叠，不选玩家行为 RAG 因复杂 ROI 低）
3. **嵌入端点验证**：智谱 embedding-3 兼容 OpenAI 协议，2048 维 PASS
4. **反转 1：不用 ChromaDB**——自写内存索引 ~30 行核心（D-020）
5. **写 16 段世界观文档**：4 地理 / 2 历史 / 1 宗教 / 3 传说 / 1 经济 / 1 魔法 / 1 生物 / 2 风俗 / 1 DM 元指南
   - 关键设计：legend_missing_adventurer 把卖菜老妇卡片 secret（失踪儿子）扩展进世界观，让 RAG 检索"家人/失踪"时能让两个 NPC 的剧情形成回声
6. **rag.py 实现**：ZhipuEmbedder + RAGIndex（add/query/save/load）+ build_world_lore_index（自动缓存）
7. **集成到 prompts.py**：set_rag_index() + build_dm_prompt 检索 top-3 注入
8. **集成到 main.py**：startup 自动构建索引（缓存到 data/rag_index.pkl）
9. **bug：numpy 没在 requirements.txt**——补一行 + 重装

### Day 4 的关键判断

**判断 1：自写向量索引而非 ChromaDB**
- 15 文档 O(N) < 1ms 不需要 ANN
- 自写 30 行让面试能讲底层（D-020）
- 最小依赖原则的延续（D-006 / D-019 同源）

**判断 2：嵌入用智谱 API 而非本地 BGE**
- 服务器内存 1G 装不下本地模型（D-021）
- 智谱 embedding-3 中文质量好
- 复用 wly 已有的智谱 key（D-017 同 provider）

**判断 3：世界观文档设计要与 NPC 卡片"对位"**
- legend_missing_adventurer 呼应卖菜老妇 secret
- legend_hero_blade 呼应铁匠"绝霜剑执念"
- 这样 RAG 检索结果能让 NPC 表现更深层、剧情线索可拼

**判断 4：RAG 失败时优雅降级**
- 智谱 API 短暂故障不让游戏崩
- try/except 包检索调用，失败时仅打日志、不注入 RAG 块
- 这是"高可用工程"思维（与 D-016 解析兜底同源）

### CC 在 Day 4 的表现观察

- **优点**：rag.py 设计干净（ABC-like Embedder + 单类 RAGIndex），自动缓存机制完善（mtime 检测）
- **bug**：忘记把 numpy 加进 requirements.txt——通过测试报错发现，5 秒修复
- **教训**：写完模块要单独 `pip install -r requirements.txt --dry-run` 验证依赖闭包

### Day 4 实测数据（这是面试材料）

| 维度 | 数据 |
|---|---|
| 世界观文档数 | 16 段（~4500 字总文本） |
| Embedding 维度 | 2048（智谱 embedding-3） |
| Index 文件大小 | 148 KB（pickle 持久化） |
| RAG 检索延迟 | 0.5-1s（含 query embedding API） |
| 总回合延迟（加 RAG） | 3.1-3.5s（vs 不加 RAG 2.4s，+~1s） |
| 检索语义准确率 | 4/4 query 都精准命中相关文档 |
| **关键观察** | "家人"召回"失踪儿子"——真语义理解，不是关键字匹配 |

### LLM 引用世界观的具体例子（面试演示用）

| 玩家问 | LLM 引用 | 来源文档 |
|---|---|---|
| 矿洞怪声 | "金属敲击声/喘气/人说话"三种猜测 + "封了两百年塌方" | `legend_mine_noises.txt` |
| 你有失踪家人吗 | 老妇沉默+反问 | `legend_missing_adventurer` + 卡片 secret 双注入 |
| 绝霜剑 | 铁匠锤子停半空、转身、直勾勾盯着 | `legend_hero_blade` + 卡片 dont_do 反向约束 |

---

## 用 CC 的几个具体技巧（Day 4 新增）

### 技巧 12：RAG 文档要和 NPC 卡片"对位设计"

第一次设计世界观时容易写"独立的世界设定"。
但如果 RAG 文档和 NPC 卡片设定有"对位"——比如 legend 提到的失踪冒险者和 NPC 卡片的 secret 是同一个人——
LLM 会在检索时"自然"地把两个信号关联起来，剧情纵深感大幅提升。
**反例**：纯粹的"世界百科"，与 NPC 完全独立——RAG 召回了也只是补背景，无法推进 NPC 互动。

### 技巧 13：自写小工具比引大依赖更值钱

15 个文档要做向量检索，主流做法是装 ChromaDB（200MB+ 依赖）。
但 numpy 余弦 + 排序 = 30 行核心代码。
**面试官眼中**：能自己实现 = 懂底层；只会调包 = 中级开发的天花板。
**反例**：为了"看起来主流"装一堆开箱即用库，最后讲解时讲不出每个库做什么。

---

## 后续 Day 5-7 计划

- Day 5：部署上线（systemd + Nginx + certbot + 服务器现状已探测）
  - 含真实 UI 浏览器测试
- Day 6：这份文档的最终版 + Demo 录屏（含"现场用 CC 加功能"）
- Day 7：简历描述 + 30 分钟讲述脚本 + 20 条 Q&A 预案

---

**写这份文档的元规则**：实时写、不补写。每个会话结束前必须更新到当天。
