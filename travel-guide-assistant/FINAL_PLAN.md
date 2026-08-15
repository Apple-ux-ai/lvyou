# TravelMate 旅游攻略助手 — 最终实施方案（v1.1）

> 汇总自 `ROADMAP.md`（开发方案）、`REVIEW.md`（评审建议）与 `TDD_REVIEW.md`（TDD 缺陷审查）。
> 制定日期：2026-08-01 · 更新：2026-08-08（DeepSeek 真实链路验收通过）
> 状态：个人本地版核心闭环、DeepSeek 真实链路、一键启动和数据备份已完成；账号体系与服务器部署暂缓

---

## 1. 产品定位

**RAG 驱动的智能旅游攻略助手**，核心价值链：

```
用户描述旅行想法 → RAG 检索知识库 → AI 生成个性化行程 → 可视化预览 → 导出/分享/保存
```

与纯 LLM 聊天不同，回答**基于真实攻略/POI 知识库**并标注引用来源（citations），减少「胡编」、提高可信度。产品覆盖内容消费（目的地、社区攻略）与工具辅助（预算、签证、汇率），形成「规划 → 决策 → 执行」完整闭环。

品牌名：**TravelMate**。当前阶段目标：**国内用户为主**（默认，可调整）。

### 1.1 当前实施状态（2026-08-05）

- ✅ 核心路径已打通：首页 → AI 助手 → 行程预览 → 规划器编辑 → SQLite 保存 → 个人中心 → 重新打开。
- ✅ FastAPI、SSE、RAG fallback、Chroma/JSON 检索、行程 CRUD 和前后端自动化测试已落地。
- ✅ 核心 4 个页面使用本地 React/Babel 运行时，演示不再依赖外部 CDN。
- ✅ DeepSeek Chat Completions 适配器、后端 `.env` 配置和请求失败自动降级已落地。
- ✅ 真实 DeepSeek 请求已通过 `/api/chat` SSE 端到端验收，可生成通过 Pydantic 校验的行程和 citations。
- ✅ 个人本地版支持双击启动/停止、健康检查、自动打开首页以及 SQLite/Chroma 备份恢复。
- ⏸ 下一阶段按个人使用反馈继续优化；正式账号和服务器部署暂缓。

---

## 2. 技术架构决策（已确定）

| 层级 | 选型 | 说明 |
|------|------|------|
| 前端 | React 18 + Babel 多 HTML 页 | 核心演示页运行时已本地化；后续可视情况迁移 Vite |
| 后端 | **Python + FastAPI** | RAG 生态最成熟；SSE 流式原生支持；Pydantic 校验 |
| RAG 编排 | LangChain / LlamaIndex | 对话链 + 知识库检索 |
| 向量库 | **Chroma**（开发）→ **Qdrant**（上线） | 本地零配置起步 |
| 业务库 | SQLite（开发）→ PostgreSQL（上线） | SQLite 已用于行程持久化；用户、攻略、评论后续迁移 PostgreSQL |
| 大模型 | 通义 / DeepSeek / OpenAI（**待选，§12**） | 国内用户优先国内模型 |
| 地图 | 国内高德 / 海外 Mapbox | 预留接口，P3 接入 |

**为什么是 Python：** RAG 编排、向量检索、Embedding/文档入库生态均为 Python 最优；FastAPI 对 SSE 流式输出原生友好；前端保持静态 React 页即可，前后端分离。

---

## 3. 目标目录结构

```
travel-guide-assistant/
├── frontend/
│   ├── pages/
│   │   ├── home.html            # ✅ 已完成
│   │   ├── assistant.html       # P0 AI 对话助手
│   │   ├── destination.html     # P0 目的地详情
│   │   ├── guides.html          # P1 攻略列表
│   │   ├── guide-detail.html    # P1 攻略详情
│   │   ├── auth.html            # P1 登录/注册
│   │   ├── profile.html         # P2 个人中心
│   │   ├── explore.html         # P2 搜索/发现
│   │   ├── planner.html         # P3 行程规划器
│   │   ├── compare.html         # P3 目的地对比
│   │   ├── budget.html          # P4 预算计算器
│   │   ├── visa.html            # P4 签证工具
│   │   └── currency.html        # P4 汇率换算
│   ├── shared/
│   │   ├── theme.css            # 设计 token（消除重复）
│   │   ├── components.js        # 共享组件（16 个）
│   │   ├── api.js               # FastAPI 封装 + SSE
│   │   └── utils.js             # 路由/主题/工具
│   └── assets/icons/
├── backend/                     # Python RAG 后端
│   ├── app/
│   │   ├── main.py
│   │   ├── api/                 # chat / trips / guides / destinations
│   │   ├── rag/                 # retriever / indexer / prompts / pipeline
│   │   ├── models/              # schemas.py / db.py
│   │   ├── services/            # llm.py / embedding.py
│   │   └── core/                # config.py / deps.py
│   ├── tests/                   # 后端测试（见 §6 测试策略）
│   │   ├── unit/                # test_schemas / test_budget / test_retriever
│   │   ├── integration/         # test_chat_api / test_trips_api / test_ingest
│   │   ├── contract/            # test_sse_contract
│   │   └── golden_qa.json       # 20-30 组黄金问答对（检索质量基准）
│   ├── scripts/ingest.py        # 知识库入库
│   ├── data/                    # 样例知识库（10 篇攻略起步）
│   ├── requirements.txt
│   └── docker-compose.yml       # PostgreSQL + Qdrant
├── frontend/tests/              # 前端测试（见 §6 测试策略）
│   ├── components/              # ItineraryCard / ChatWindow / BudgetSummary
│   └── e2e/                     # key-path.spec.js（关键路径）
├── ROADMAP.md                   # 详细开发方案（保留）
├── REVIEW.md                    # 评审记录（保留）
├── TDD_REVIEW.md                # TDD 缺陷审查报告（保留）
└── FINAL_PLAN.md                # 本文档
```

---

## 4. 分阶段执行计划

### Phase 0 — 前端工程基础（P0，与 Phase 1.5 并行）

- [x] 抽取 `shared/theme.css`，统一全站设计 token
- [ ] 完成 `shared/components.js` 迁移：当前已建立组件入口，Topbar / Footer 等仍有页面内重复
  - **加载方式（已确定）：** 无构建 CDN 环境，组件经 `<script>` 全局注入，暴露于 `window.TravelMate.*`；不用 ES Module
- [x] 建立 `shared/api.js`：封装 SSE 与行程 create/list/get/update
- [x] 建立 `shared/utils.js`：路由跳转、主题切换、API 基址
- [x] 执行首页入口与导航修复（见 §7）
- [ ] 修复设计校验 3 条 warning（见 §8）
- [x] 确定页面链接规范：`pages/xxx.html?id=...`
- [x] **图标体系拍板（已确定）：** 采用内联 SVG 组件为主，`assets/icons/` 仅作管理/fallback 用途，全站统一（解决修复清单 #8）
- [x] 搭建前端测试环境：Vitest + React Testing Library + Playwright（见 §6）

### Phase 1.5 — Python RAG 后端骨架（P0）

- [x] FastAPI 项目骨架 + `/api/chat` SSE 响应
- [x] Pydantic 模型：`Itinerary` / `DayPlan` / `Trip`（前端 `ItineraryCard` 直接消费）
- [x] Chroma 本地向量库 + 10 篇样例攻略入库（`scripts/ingest.py`）
- [x] RAG Pipeline 跑通：检索 → 生成/降级 → SSE 流式输出 + citations
- [x] SQLite 行程持久化 + create/list/get/update API
- [ ] `docker-compose.yml` 一键启动（暂缓：个人本地版无需 PostgreSQL/Qdrant）
- [x] 接入 DeepSeek Provider：Chat Completions 请求、后端环境配置和本地 fallback
- [x] 使用真实 DeepSeek API Key 完成联网、JSON 行程输出与 SSE 端到端验收
- [x] 后端测试环境：pytest + pytest-asyncio + httpx（见 §6）
- [x] 建立 `golden_qa.json`（20-30 组黄金问答对，作为检索质量回归基准）

**关键行为定义（v1.1 补充，消除 TDD 缺陷 H1-H3）：**

1. **LLM 输出兜底（H1）：** 解析非法 JSON / 缺字段时**不崩溃**，降级链为：
   - 合法 `Itinerary` JSON → 渲染行程卡片
   - 非法 JSON → 重试 1 次 → 仍失败则降级为纯文本回答（`type: "text"` + `error_code: "invalid_json"`）
   - 部分字段缺失（如 `total_budget: null`）→ 允许为 null，前端渲染「待估算」
2. **RAG 边界（H2）：**
   - 向量库为空 → 返回空 citations + 通用回答，不抛异常
   - Top-K 相关度低于阈值（`min_score=0.3`）→ 不放行该结果
   - 任意 citation 的 `source_id` 必须存在于知识库（引用完整性校验）
3. **多轮上下文管理（H3）：**
   - 滑动窗口：仅保留最近 3 轮对话（约 2000 token）
   - 单条超长消息按 token 截断
   - 会话有效期 24h，超时提示重新开始

**知识库分库设计（避免单一混杂向量库）：**

```
knowledge/
├── destinations/     # 目的地概览、最佳季节、签证概要
├── pois/             # 景点、餐厅、酒店 POI
├── guides/           # 社区攻略全文（Markdown）
├── itineraries/      # 优质行程模板
└── tools/            # 签证材料、汇率、安全贴士
```

用户发布攻略 → 自动触发 `ingest.py` 入库 → RAG 可检索。

**入库幂等性（M4 缺陷修复）：** `ingest.py` 必须幂等——同一 `source_id` 重复入库不产生重复 chunk；攻略更新按 `version` 字段替换旧 chunk（`test_ingest_is_idempotent` / `test_reingest_replaces_old_chunks`）。

### Phase 2 — 核心功能页面（P0/P1）

| 页面 | 路径 | 关键点 |
|------|------|--------|
| AI 对话助手 | `assistant.html` | 左侧对话 + 右侧行程预览；SSE 流式；ItineraryCard；citations；预算概览；导出/保存；历史会话；移动端 Tab 切换 |
| 目的地详情 | `destination.html` | Hero 大图；Tab：概览/景点/美食/住宿/交通/贴士；景点卡片；地图占位；推荐线路（对齐 Itinerary Schema）；评价；预算 widget |
| 攻略列表 | `guides.html` | 搜索 + 筛选（目的地/天数/预算/主题）；卡片网格；排序；分页/无限滚动；骨架屏 |
| 攻略详情 | `guide-detail.html` | 文章头；Markdown 正文；时间线；费用明细表；相关推荐；评论（需登录） |

### Phase 3 — 用户体系（暂缓）

- `auth.html`：邮箱 + 密码 + 验证码；第三方登录（原型期只做邮箱）；「游客继续使用」入口（anonymous session + localStorage）
- `profile.html`：Tab（我的行程 / 我的攻略 / 收藏夹 / 设置）；发布攻略自动触发 RAG 入库

### Phase 4 — 辅助功能（P2/P3）

- `explore.html`：与 home 差异化（home = 转化入口，explore = 深度浏览 + 筛选）；主题分类；AI 推荐卡片
- `planner.html`：仅从 assistant「手动编辑」进入；日历 + 拖拽编排；预算追踪；协作编辑可延后
- `compare.html`：2-3 目的地对比（费用/季节/签证/人群/安全）；可视化图表

### Phase 5 — 工具页（P4）

- `budget.html`：分项预估 + 饼图/条形图（与 `BudgetSummary` 共用计算逻辑）
- `visa.html`：按国家查询（数据来自 `tools/` 知识库）；标注数据更新日期
- `currency.html`：实时汇率（免费 API）+ 多币种对比

---

## 5. 核心 API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | RAG 对话，SSE 流式返回 |
| POST | `/api/chat/rag` | 带 citations 的检索增强回答 |
| GET/POST | `/api/trips`、`/api/trips/{id}` | 行程 CRUD |
| GET | `/api/destinations` | 目的地列表 |
| GET | `/api/guides` | 攻略列表（分页 + 筛选） |
| POST | `/api/knowledge/ingest` | 管理端：攻略/POI 入库 |

**行程 JSON Schema（Pydantic）：**

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

**SSE 协议契约（v1.1 补充，消除 TDD 缺陷 D3）：** 前后端按此契约对写测试

```
POST /api/chat   （请求体：{"message": "...", "history": [...], "session_id": "..."}）

event: message      data: {"text": "...", "citations": [{"source_id": "...", "title": "..."}]}
event: itinerary    data: {Itinerary JSON}
event: done         data: {"id": "...", "usage": {"prompt_tokens": n, "completion_tokens": n}}
event: error        data: {"code": "retrieval_failed|invalid_json|rate_limited", "message": "..."}
心跳：>15s 无输出发送注释行 ": ping"
约定：流必须以 event: done 或 event: error 终止
```

---

## 6. 测试策略（TDD，v1.1 新增）

> 采用 TDD 铁律：**无失败测试，无生产代码**。任何新功能先写 RED 测试，验证失败后写最小实现，再验证 GREEN。
> 本策略消除 TDD_REVIEW 缺陷 D1（无测试策略层）。

### 6.1 测试分层

| 层 | 框架 | 覆盖对象 | 运行时机 |
|----|------|----------|----------|
| 单元 | pytest（后端）/ Vitest + RTL（前端） | Schema、预算计算、retriever、组件渲染 | 每次提交 |
| 集成 | pytest + FastAPI TestClient | API 端点 + Chroma（临时 collection）/ SQLite 替换 PG | 每次提交 |
| 契约 | pytest（后端） / 前端 fixture 解析 | SSE 事件格式、Itinerary JSON | 每次提交 |
| E2E | Playwright | 关键路径（首页→助手→行程→保存） | 每次发版 |
| 设计校验 | `validate-design-workspace.mjs` | 0 error + 0 新增 warning | CI 门禁 |

### 6.2 后端测试要点

```
backend/tests/
├── unit/
│   ├── test_schemas.py          # Itinerary / DayPlan 校验（含 null 字段）
│   ├── test_budget.py           # 分项求和 = 总额等纯函数
│   ├── test_retriever.py        # 空库 / 阈值 / Top-K 排序 / 引用完整性
│   └── test_llm_output.py       # 坏 JSON 降级链（H1）
├── integration/
│   ├── test_chat_api.py         # SSE 流、error 事件、done 终止、超时
│   ├── test_trips_api.py        # CRUD + 401 + 权限
│   └── test_ingest.py           # 幂等性 / 版本替换（M4）
├── contract/
│   └── test_sse_contract.py     # 事件名 / 载荷 schema / done 终止（D3）
├── golden_qa.json               # 20-30 组黄金问答对（H5）
└── conftest.py
```

**首批 RED 测试（Phase 1.5 开工即写）：**

```python
# test_llm_output.py — 坏 JSON 必须降级而非崩溃
def test_malformed_llm_json_falls_back_to_text():
    raw = '{"day_plans": [bad json'
    result = parse_llm_output(raw)
    assert result.type == "text"
    assert result.error_code == "invalid_json"

# test_retriever.py — 空库不抛异常
def test_retriever_empty_db_returns_no_citations():
    assert retriever.search("冰岛", top_k=5) == []

# test_sse_contract.py — 流必须以 done/error 终止
def test_sse_emits_done_event(client):
    events = collect_events(client, "/api/chat", {"message": "hi"})
    assert events[-1].event in ("done", "error")

# test_ingest.py — 重复入库不产生重复 chunk
def test_ingest_is_idempotent():
    ingest("guides/kyoto.md")
    count1 = count_chunks("kyoto-guide-01")
    ingest("guides/kyoto.md")
    assert count1 == count_chunks("kyoto-guide-01")
```

### 6.3 前端测试要点

```
frontend/tests/
├── components/
│   ├── ItineraryCard.test.jsx   # 空态 day_plans / 长天数 / null 预算（H4）
│   ├── ChatWindow.test.jsx      # SSE 流式渲染 / 错误重试 / 重连（H4）
│   └── BudgetSummary.test.jsx   # 分项合计一致性
└── e2e/
    └── key-path.spec.js         # 首页→助手→行程→保存（M5 缺陷修复）
```

**首批 RED 测试：**

```javascript
test('ItineraryCard renders empty day_plans as empty state', () => {
  render(<ItineraryCard itinerary={EMPTY_ITINERARY} />);
  expect(screen.getByText(/暂无行程安排/)).toBeInTheDocument();
});

test('ChatWindow shows retry button on stream error', () => {
  mockEventSource.errorOnce();
  render(<ChatWindow />);
  expect(screen.getByRole('button', { name: /重试/ })).toBeInTheDocument();
});
```

### 6.4 E2E 关键路径

```javascript
test('user can plan a trip end-to-end', async ({ page }) => {
  await page.goto('/pages/home.html');
  await page.click('.search-btn');                 // → assistant.html?query=...
  await page.fill('.chat-input input', '五一去日本7天');
  await page.click('.chat-send');
  await expect(page.locator('.itinerary-card')).toBeVisible();
  await page.click('#save-trip');
  await expect(page.locator('.toast-success')).toBeVisible();
});
```

---

## 7. 首页修复清单（Phase 0 执行）

| # | 项 | 操作 |
|---|-----|------|
| 1 | 导航跳转 | 改为真实 `pages/xxx.html` 链接 |
| 2 | 移动端菜单 | 补全 `mobileOpen` 抽屉 nav（state 已存在，未渲染） |
| 3 | 暗色模式 | Topbar 加 toggle（CSS token 已定义） |
| 4 | Hero 搜索 | 跳转 `assistant.html?query=...` |
| 5 | DestCard 点击 | 跳转 `destination.html?id=xxx` |
| 6 | Chat 预览 | 跳转 `assistant.html` |
| 7 | 移除 lucide CDN | 未使用，删引用 |
| 8 | 统一图标 | `assets/icons/` 或内联 SVG 二选一（当前混用） |
| 9 | CSS 去重 | 引用外部 `shared/theme.css`，删内联 token |

---

## 8. 设计规范修正（消除 3 条校验 warning）

- 将 `--secondary` / `--accent` 品牌变量改为 `--muted` + primary 透明度变体（semantic 状态用 `--state-*`）
- 移除 `--google-radius-xl`，统一 `--radius-lg`（8px 基准）
- 同步修改 `colors_and_type.css` 与全部页面

**设计约束（全站一致）：** 主色 `#4285f4`；DM Sans + JetBrains Mono；8px 圆角；3.84px 微间距；零阴影（边框/色调分层）；暗色主色 `#fc2c50` + 背景 `#161616`；桌面/平板(1024px)/手机(768px) 三档响应。

---

## 9. 共享组件清单（`shared/components.js`）

Topbar、Footer、SearchBar、DestCard、ChatWindow（SSE 流式渲染）、ChatMessage（citations + 行程卡片）、ItineraryCard、BudgetSummary、GuideCard、Timeline、Rating、Tag/Badge、Button/IconButton、Avatar、Tabs、FilterBar。

异常态 UI 需各页覆盖：**loading / empty / error / offline** 四态。

> 每个共享组件须配测试（见 §6.3），核心组件 `ItineraryCard`、`ChatWindow`、`BudgetSummary` 优先。

---

## 10. 执行时间线

| 阶段 | 范围 | 周期 |
|------|------|------|
| **立即** | 测试策略落地（§6 首批 RED 测试）；backend FastAPI 骨架 + `/api/chat` mock；Phase 0 抽取 theme.css + 首页 9 项修复 + 前端测试环境；消除 3 条 warning；准备 10 篇样例攻略 + golden_qa.json | 本周 |
| **短期** | RAG 跑通（Chroma + 入库 + 流式，含 H1-H3 边界行为）；Itinerary Schema；assistant.html 静态 UI + 对接 SSE；destination.html | 2-4 周 |
| **当前** | 个人本地版稳定性、启动体验、备份恢复和实际使用反馈修复 | 持续 |
| **暂缓** | 正式账号、云端行程、PostgreSQL、Qdrant、Docker 与服务器部署 | 有多人/远程使用需求时再启动 |

> **测试先行原则：** 每个阶段的第一项任务都是写该阶段功能的 RED 测试，验证失败后再实现功能本体。

---

## 11. 里程碑与验收标准（可自动验证）

> v1.1 修订：每条验收标准对应自动化测试断言，替代人工判断（消除 TDD 缺陷 D2）。
> 验收 = 对应测试套件通过（pytest / vitest / Playwright）+ 设计校验 0 error。

| 里程碑 | 验收标准（测试断言） | 对应测试 |
|--------|----------------------|----------|
| M1：后端骨架 | `/api/chat` mock 返回 SSE 流，且流以 `done` 事件终止；content-type 为 `text/event-stream` | `test_chat_api.py` / `test_sse_contract.py` |
| M2：RAG 跑通 | 固定问句「五一去日本7天预算1万」→ 返回行程 JSON；citations 的 `source_id` 命中预期黄金攻略集且引用存在；检索结果全部通过 `min_score` 阈值 | `golden_qa.json` + `test_retriever.py` |
| M3：助手页上线 | `ItineraryCard` 正确渲染合法行程（含空态/长天数/null 预算）；SSE 断流出现重试按钮；保存行程后 `GET /api/trips/{id}` 返回一致数据 | `ItineraryCard.test.jsx` / `ChatWindow.test.jsx` / `test_trips_api.py` |
| M4：内容闭环 | 同一攻略重复入库 chunk 数不变（幂等）；攻略更新后旧 chunk 被版本替换；入库后可被检索引用 | `test_ingest.py` |
| M5：全站完成 | 13 页全部落地；关键路径 E2E（首页→助手→行程→保存）通过；设计校验 0 error + 0 新增 warning；移动端视口无溢出 | `key-path.spec.js` / 设计校验脚本 |

**CI 门禁（建议）：** 每次提交运行 `pytest` + `vitest run` + 设计校验脚本，任一失败即阻塞合并。

---

## 12. 待确认决策（2 项，其余均已确定）

| # | 问题 | 推荐默认 | 影响 |
|---|------|----------|------|
| 1 | **大模型选型** | DeepSeek（中文强、成本低）；备选通义 | API 成本、中文效果、合规 |
| 2 | **目标用户** | 国内为主 | 地图 SDK、模型、知识库语言（中文） |

> 采用推荐默认即可开工；如无异议，本方案按「国内用户 + DeepSeek」执行。

---

## 13. 风险与注意事项

- **内容合规**：攻略/POI 数据来源需标注；避坑内容避免绝对化表述
- **微信登录**：需开放平台资质，原型期先做邮箱 + 游客模式
- **SSE 跨域**：FastAPI 需配置 CORS，前端 API 基址统一管理
- **密钥安全**：LLM Key 只存后端环境变量，禁止进前端
- **知识库质量**：初始 10 篇样例攻略需覆盖多目的地，并配套 golden_qa.json 作为质量基准
- **LLM 不确定性**：坏 JSON / 低相关度 / 空库均有降级行为定义（§4 Phase 1.5），测试覆盖全部路径

---

*下一步可执行（按 TDD）：1）写入 §6 首批 RED 测试并确认失败；2）搭建 `backend/` 最小 FastAPI + RAG 骨架使其变绿；3）执行 Phase 0 前端重构 + 首页修复；4）准备样例知识库数据与 golden_qa.json。确认后即可开工。*
