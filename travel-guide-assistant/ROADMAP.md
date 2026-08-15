# TravelMate 旅游攻略助手 — 后续开发方案

## 当前状态

- ✅ 首页 `home.html`（已完成，基于谷歌设计系统）
- ✅ 核心演示闭环：首页 → AI 助手 → 规划器 → SQLite 保存 → 个人中心 → 重新打开
- ✅ FastAPI / SSE / RAG fallback / 行程 CRUD / 自动化测试已完成
- 设计系统：Google Design Library（`#4285f4` 主色，DM Sans 字体，8px 圆角，扁平化风格）
- 前端技术栈：React 18 + Babel + 内联样式（核心演示页运行时已本地化）
- 后端技术栈（已确定）：**Python + FastAPI + RAG**（见 Phase 1.5）
- ✅ DeepSeek 真实链路已通过联网、JSON 行程输出与 SSE 端到端验收
- ✅ 个人本地版支持双击启动/停止、健康检查和 SQLite/Chroma 备份恢复
- 下一优先级：按个人实际使用反馈优化；账号体系和服务器部署暂缓

---

## 技术架构总览

```
┌─────────────────────────────────────────────────────────┐
│  前端（现有 HTML/React 页面）                              │
│  pages/*.html  →  SSE/WebSocket  →  FastAPI             │
└─────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────┐
│  Python 后端（backend/）                                   │
│  FastAPI ──► RAG Pipeline ──► LLM                        │
│           ──► 向量库（Chroma / Qdrant）                   │
│           ──► PostgreSQL（用户 / 行程 / 攻略元数据）        │
└─────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────┐
│  知识源（RAG 入库）                                        │
│  目的地 / 景点 POI / 社区攻略 / 行程模板 / 签证·汇率工具数据  │
└─────────────────────────────────────────────────────────┘
```

### 技术选型

| 层级 | 选型 | 说明 |
|------|------|------|
| 前端 | React 18 + Babel 多 HTML 页 | 核心演示页已脱离 CDN，后续可迁移 Vite |
| API | **FastAPI** | 异步、SSE 流式、Pydantic 校验 |
| RAG 编排 | **LangChain** 或 **LlamaIndex** | 对话链 + 知识库检索 |
| 向量库 | **Chroma**（开发）→ **Qdrant**（上线） | 本地零配置起步 |
| 业务库 | SQLite（开发）→ **PostgreSQL**（上线） | 行程已持久化；用户与内容数据后续迁移 |
| 缓存 | Redis（可选） | 会话、限流 |
| 大模型 | 通义 / DeepSeek / OpenAI | 国内用户优先国内模型 |

---

## Phase 0 — 前端工程基础（优先级：高）

> 在批量开发页面前，先解决重复代码和路由问题

- [x] 抽取 `shared/theme.css`，统一设计 token
- [ ] 完成 `shared/components.js` 的 Topbar / Footer / Button 迁移（当前仅部分共享）
- [x] 建立 `shared/utils.js`（路由跳转、主题切换、API 基址）
- [x] 修复首页入口与导航问题
- [ ] 修复设计校验 3 条 warning（secondary/accent 色变量）
- [x] 确定页面间链接规范（`pages/xxx.html?id=...`）

---

## Phase 1 — 首页（已完成）

- ✅ `pages/home.html`

---

## Phase 1.5 — Python RAG 后端骨架（优先级：高）

> 核心能力层，AI 助手页依赖此阶段

### 1.5.1 项目初始化

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── api/
│   │   ├── chat.py          # 对话接口（SSE 流式）
│   │   ├── trips.py         # 行程 CRUD
│   │   ├── guides.py        # 攻略列表/详情
│   │   └── destinations.py  # 目的地
│   ├── rag/
│   │   ├── retriever.py     # 向量检索
│   │   ├── indexer.py       # 文档入库
│   │   ├── prompts.py       # Prompt 模板
│   │   └── pipeline.py      # RAG 编排主流程
│   ├── models/
│   │   ├── schemas.py       # Pydantic 模型（行程 JSON Schema）
│   │   └── db.py            # SQLAlchemy 模型
│   ├── services/
│   │   ├── llm.py           # 大模型调用（流式）
│   │   └── embedding.py     # Embedding 模型
│   └── core/
│       ├── config.py        # 环境变量
│       └── deps.py          # 依赖注入
├── scripts/
│   └── ingest.py            # 知识库批量入库脚本
├── data/                    # 样例知识库（Markdown/JSON）
├── requirements.txt
└── docker-compose.yml       # PostgreSQL + Qdrant
```

### 1.5.2 核心 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | RAG 对话，SSE 流式返回 |
| POST | `/api/chat/rag` | 带 citations 的检索增强回答 |
| GET | `/api/trips/{id}` | 获取行程 |
| POST | `/api/trips` | 保存行程 |
| GET | `/api/trips` | 获取已保存行程列表 |
| PUT | `/api/trips/{id}` | 更新已保存行程 |
| GET | `/api/destinations` | 目的地列表 |
| GET | `/api/guides` | 攻略列表（分页 + 筛选） |
| POST | `/api/knowledge/ingest` | 管理端：攻略/POI 入库 |

### 1.5.3 RAG 知识库设计

分库检索，避免单一向量库混杂：

```
knowledge/
├── destinations/     # 目的地概览、最佳季节、签证概要
├── pois/             # 景点、餐厅、酒店 POI
├── guides/           # 社区攻略全文（Markdown）
├── itineraries/      # 优质行程模板
└── tools/            # 签证材料、汇率、安全贴士
```

**对话流程：**

1. 用户输入 → 意图识别（行程规划 / 问答 / 预算咨询）
2. 按意图选择知识库 → 向量检索 Top-K
3. 检索结果 + 用户上下文 → LLM 生成
4. 行程类意图 → 输出结构化 JSON（Pydantic 校验）
5. 返回答案 + citations（「参考：xxx 攻略」）

### 1.5.4 行程 JSON Schema（Pydantic）

```python
class DayPlan(BaseModel):
    day: int
    title: str
    activities: list[str]
    transport: str | None
    budget: float | None

class Itinerary(BaseModel):
    destination: str
    days: int
    total_budget: float
    day_plans: list[DayPlan]
    tips: list[str] | None
```

前端 `ItineraryCard` 组件直接消费此结构。

### 1.5.5 里程碑

- [x] FastAPI 项目骨架 + `/api/chat` SSE 响应
- [x] Chroma 本地向量库 + 10 篇样例攻略入库
- [x] RAG Pipeline 跑通（检索 → 生成/降级 → 流式输出）
- [x] 行程 JSON Schema 定义 + 校验
- [x] SQLite 行程持久化与列表/读取/更新接口
- [ ] docker-compose 一键启动（暂缓：个人本地版不需要）
- [x] 接入 DeepSeek Provider（Chat Completions + 后端环境配置 + 本地 fallback）
- [x] 使用真实 DeepSeek API Key 完成联网、JSON 行程输出与 SSE 端到端验收

---

## Phase 2 — 核心功能页面（优先级：高）

### 2.1 AI 对话助手页 `pages/assistant.html`
> 产品核心页，对接 Phase 1.5 RAG 后端

- 左侧对话面板（全屏聊天，SSE 流式显示 AI 回复）
- 右侧行程预览面板（解析后端返回的 `Itinerary` JSON 渲染卡片）
- 功能点：
  - 对话输入框 + 语音输入按钮（Web Speech API）
  - AI 回复中的行程卡片（可折叠/展开每天详情）
  - 检索引用展示（citations：「参考：关西攻略 by 小王」）
  - 预算概览组件（读取 `Itinerary.total_budget`）
  - 导出行程按钮（PDF / 分享链接，调用 `/api/trips`）
  - 历史对话列表侧边栏（localStorage → 登录后云端）
- 移动端：Tab 切换「对话 / 行程」，非左右分栏

### 2.2 目的地详情页 `pages/destination.html`
> 从首页卡片点击进入；数据可来自 RAG 知识库 `destinations/`

- 顶部 Hero 大图 + 地名/简介叠加
- 标签导航：概览 | 景点 | 美食 | 住宿 | 交通 | 贴士
- 景点卡片列表（图片 + 名称 + 评分 + 门票价格）
- 地图组件区域（国内：高德；海外：Mapbox，预留接口）
- 推荐行程路线（3-5 条预设，格式与 `Itinerary` Schema 对齐）
- 用户评价区
- 侧边栏：快速预算计算器（精简版 widget）

### 2.3 攻略列表页 `pages/guides.html`
> 对应首页 nav「社区」；数据来自 `/api/guides`

- 顶部搜索栏 + 筛选器（目的地 / 天数 / 预算 / 主题）
- 攻略卡片网格（封面图 + 标题 + 作者 + 天数 + 阅读量）
- 排序：最新 | 最热 | 好评
- 分页 / 无限滚动
- 骨架屏 loading 态

### 2.4 攻略详情页 `pages/guide-detail.html`
> 单篇攻略阅读；正文同时是 RAG 知识库来源

- 文章头部：标题 / 作者 / 发布时间 / 标签 / 点赞收藏
- 富文本正文（Markdown 渲染）
- 行程时间线组件（左侧时间轴 + 右侧每天详情）
- 费用明细表格
- 相关攻略推荐
- 评论区（需登录）

---

## Phase 3 — 用户体系页面（暂缓）

### 3.1 登录/注册页 `pages/auth.html`
- 表单：邮箱 + 密码 + 验证码
- 第三方登录（微信 / Google，原型期可只做邮箱）
- 「游客继续使用」入口（anonymous session + localStorage）
- 表单验证 + 错误提示

### 3.2 个人中心 `pages/profile.html`
- 用户信息卡片（头像 / 昵称 / 个人简介）
- Tab：我的行程 | 我的攻略 | 收藏夹 | 设置
- 我的行程：列表（状态：草稿 / 已完成 / 已分享）
- 我的攻略：用户发布的攻略（发布后自动触发 RAG 入库）
- 收藏夹：收藏的目的地和攻略
- 账户设置：昵称 / 头像 / 密码 / 通知偏好

---

## Phase 4 — 辅助功能页面（优先级：中低）

### 4.1 行程规划器 `pages/planner.html`
> 入口：仅从 assistant「手动编辑」进入；与 AI 助手分工明确

- 日历视图 + 拖拽式行程编排
- 每天时间轴（上午/下午/晚上）
- 交通衔接提示
- 预算追踪仪表盘
- 协作编辑（P4，可延后）

### 4.2 搜索/发现页 `pages/explore.html`
> 与 home 差异化：home = 转化入口；explore = 深度浏览 + 筛选

- 热门目的地轮播
- 主题分类（海岛 / 雪山 / 古城 / 美食 / 极光...）
- 热门攻略流
- AI 推荐卡片（调用 RAG 推荐接口）

### 4.3 对比页 `pages/compare.html`
- 2-3 个目的地横向对比
- 对比维度：费用 / 最佳季节 / 签证难度 / 适合人群 / 安全性
- 可视化对比图表（数据来自 `destinations/` 知识库）

---

## Phase 5 — 数据可视化与工具页（优先级：低）

### 5.1 预算计算器 `pages/budget.html`
- 输入：目的地 + 天数 + 人数 + 消费等级
- 输出：交通 / 住宿 / 餐饮 / 门票 / 其他 分项预估
- 饼图 + 条形图；与 assistant 内 `BudgetSummary` 共用计算逻辑

### 5.2 签证工具 `pages/visa.html`
- 按国家查询（数据来自 `tools/` 知识库 + RAG 问答）
- 材料清单 + 办理流程 + 办理时间线
- 标注数据更新日期和来源

### 5.3 汇率换算 `pages/currency.html`
- 实时汇率（接入 exchangerate-api 等免费 API）
- 多币种对比 + 消费水平参考

---

## 设计规范一致性

所有页面需遵循：
- **主色**：`#4285f4`（Google Blue）
- **字体**：DM Sans（界面） + JetBrains Mono（数据）
- **圆角**：8px 基准
- **间距**：3.84px 微单元
- **阴影**：零阴影，用边框和色调区分层次
- **暗色模式**：主色切换为 `#fc2c50`，背景 `#161616`
- **响应式**：桌面 / 平板（1024px）/ 手机（768px）三档

---

## 推荐执行顺序

| 优先级 | 任务 | 预计工作量 | 依赖 |
|--------|------|-----------|------|
| P0 | Phase 0 前端工程基础 | 小 | 无 |
| P0 | Phase 1.5 RAG 后端骨架 | 大 | 无 |
| P0 | AI 对话助手页 | 大 | Phase 0 + 1.5 |
| P0 | 目的地详情页 | 中 | Phase 0 |
| P1 | 攻略列表页 | 中 | Phase 0 + 1.5 |
| P1 | 攻略详情页 | 中 | 攻略列表页 |
| P1 | 登录/注册页 | 小 | Phase 0 |
| P2 | 个人中心 | 中 | 登录/注册 + 1.5 |
| P2 | 搜索/发现页 | 中 | Phase 0 |
| P3 | 行程规划器 | 大 | AI 助手页 |
| P3 | 对比页 | 小 | 目的地详情页 |
| P4 | 预算计算器 | 小 | 目的地详情页 |
| P4 | 签证工具 | 小 | RAG 知识库 |
| P4 | 汇率换算 | 小 | 无 |

---

## 项目目录结构（目标态）

```
travel-guide-assistant/
├── frontend/                    # 前端（现有内容迁移）
│   ├── pages/
│   │   ├── home.html            # ✅
│   │   ├── assistant.html
│   │   └── ...
│   ├── shared/
│   │   ├── theme.css
│   │   ├── components.js
│   │   ├── api.js               # 封装 FastAPI 调用 + SSE
│   │   └── utils.js
│   └── assets/icons/
├── backend/                     # Python RAG 后端
│   ├── app/                     # （见 Phase 1.5.1）
│   ├── scripts/ingest.py
│   ├── data/                    # 样例知识库
│   ├── requirements.txt
│   └── docker-compose.yml
├── ROADMAP.md
└── REVIEW.md
```

---

## 共享组件清单

以下组件在多页面复用，建议统一维护于 `frontend/shared/components.js`：

- `Topbar` — 顶部导航（已实现）
- `Footer` — 页脚（已实现）
- `SearchBar` — 搜索输入框
- `DestCard` — 目的地卡片
- `ChatWindow` — AI 对话窗口（含 SSE 流式渲染）
- `ChatMessage` — 单条消息气泡（含 citations + 行程卡片）
- `ItineraryCard` — 行程卡片（消费 `Itinerary` JSON）
- `BudgetSummary` — 预算概览
- `GuideCard` — 攻略卡片
- `Timeline` — 行程时间线
- `Rating` — 评分组件
- `Tag` / `Badge` — 标签/徽章
- `Button` / `IconButton` — 按钮体系
- `Avatar` — 头像
- `Tabs` — 标签页切换
- `FilterBar` — 筛选栏

---

## 部署方案（参考，当前暂缓）

| 组件 | 开发 | 上线 |
|------|------|------|
| 前端 | 静态文件 / Live Server | Nginx / Vercel / OSS |
| FastAPI | `uvicorn` 本地 | Docker + Gunicorn |
| 向量库 | Chroma 本地文件 | Qdrant Cloud / 自建 |
| PostgreSQL | Docker | 云 RDS |
| LLM | API Key 本地 | 同上，注意密钥管理 |
