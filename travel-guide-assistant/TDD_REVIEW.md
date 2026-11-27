# TravelMate 后续方案 — TDD 视角缺陷审查报告

> 审查对象：`FINAL_PLAN.md`（v1.0）、`ROADMAP.md`、`REVIEW.md`
> 审查方法：TDD 铁律「**无失败测试，无生产代码**」——把方案中的每个行为承诺转成验收测试，写不出断言或断言模糊的地方即为缺陷
> 审查日期：2026-08-01

---

## 一、核心结论（TL;DR）

方案在**架构、页面规划、知识库设计**层面完整度较高，但在**可测试性**层面存在系统性缺口：

| 严重度 | 缺陷数 | 一句话概括 |
|--------|--------|-----------|
| 🔴 致命 | 3 | 方案完全没有测试策略层；里程碑验收标准不可自动验证；SSE 协议契约未定义 |
| 🟠 高 | 5 | LLM 坏 JSON 无兜底；RAG 空库/低相关度无行为定义；上下文管理未定义；前端组件无测试框架；检索质量无度量 |
| 🟡 中 | 5 | 图标体系二选一未落地；无构建环境与共享组件模块化矛盾；执行顺序与时间线不一致；知识库幂等性缺失；无端到端关键路径测试 |

**一句话：** 当前方案是「做什么」清单，不是「怎么验证做对了」的规格。TDD 要求每个承诺先有测试，而方案中大部分行为连断言都没定义。

---

## 二、致命缺陷（必须先补）

### D1. 方案通篇没有测试策略层

**问题：** `FINAL_PLAN.md` 从 Phase 0 到 Phase 5、13 个页面、6 类 API、16 个组件，没有任何一节定义测试方案：测试框架、测试分层、目录、运行方式、CI 门禁。

**TDD 暴露点：** TDD 的起点是「先写测试」，而方案没有告诉开发者测试文件写在哪、用什么框架跑、何时算通过。铁律无法执行。

**缺失的规格：**
```markdown
## 测试策略（需补入方案）
- 后端：pytest + pytest-asyncio + httpx（FastAPI TestClient）
  - 单元：Pydantic schema / 预算计算 / retriever 排序
  - 集成：API 端点 + Chroma（临时 collection）/ SQLite 替换 PG
  - 契约：SSE 事件格式 / Itinerary JSON
- 前端：Vitest + React Testing Library（组件）；Playwright（E2E）
- CI：`pytest` + `npm test` + 设计校验脚本（0 error 门禁）
- 目录：backend/tests/、frontend/tests/
```

**先写的测试（RED）：**
```python
# backend/tests/test_chat_api.py
def test_chat_returns_sse_stream(client):
    """POST /api/chat 必须返回 SSE 流，含 done 事件"""
    with client.stream("POST", "/api/chat", json={"message": "五一去日本"}) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
```

---

### D2. 里程碑验收标准不可自动验证

**问题：** §10 的 M1-M5 验收标准依赖人工判断：

| 里程碑 | 验收标准 | 缺陷 |
|--------|----------|------|
| M1 | "`curl` 可测" | 手测 ≠ 自动化测试；无断言、不可回归 |
| M2 | "正确引用样例攻略" | **「正确」没有断言**——引用集合的期望值未定义 |
| M3 | "行程可保存/导出" | 无数据契约测试（保存后再取回是否一致） |
| M4 | "自动入库 → 可被检索" | 无幂等性测试（同一攻略入库两次会怎样） |
| M5 | "设计校验 0 error" | 可脚本化但未定义 CI 门禁 |

**TDD 暴露点：** 验收标准里出现了无法断言的形容词（"正确""可"），而 TDD 的黄金测试（golden test）要求精确输入输出。

**先写的测试（RED）：**
```python
# M2 的黄金测试：固定问句 → 断言 citations 命中预期攻略集
def test_rag_citation_hits_expected_source():
    result = pipeline.ask("五一去日本玩7天，预算1万")
    sources = {c.source_id for c in result.citations}
    assert sources.issubset({"kyoto-guide-01", "japan-visa-02"})
    assert len(sources) >= 1
```

---

### D3. SSE 协议契约未定义（前后端无法对写测试）

**问题：** §5 只写了 `POST /api/chat` "SSE 流式返回"，但**事件类型、事件名、载荷结构、结束信号、心跳、错误、重连**全部未定义。后端不知道发什么事件，前端 `ChatWindow` 不知道监听什么，两端各自写测试必然不匹配。

**缺失的规格（需补入方案）：**
```
event: message      data: {"text": "...", "citations": [{"source_id","title"}]}
event: itinerary    data: {Itinerary JSON}
event: done         data: {"id": "...", "usage": {...}}
event: error        data: {"code": "retrieval_failed", "message": "..."}
心跳：>15s 无输出发 : ping
```

**先写的测试（RED，契约两侧各一个）：**
```python
def test_sse_emits_done_event(client):
    events = collect_events(client, "/api/chat", {"message": "hi"})
    assert events[-1].event == "done"          # 后端契约

def test_done_event_must_terminate_stream():   # 前端契约
    parser = parse_sse(stream_from_fixture())
    assert parser.last_event.name == "done"
```

---

## 三、高严重度缺陷

### H1. LLM 输出坏 JSON 无兜底行为

**问题：** §4 Phase 1.5 定义了 `Itinerary` Pydantic Schema，但 LLM 是概率模型，输出非法 JSON / 缺字段是**必然事件**。方案未定义：解析失败重试几次？降级为纯文本？部分字段缺失（如 `budget=null`）如何渲染？

**TDD 暴露点：** 一旦写 `test_parse_itinerary()`，立刻发现"输入什么、抛什么错、回退什么"全是未定义行为。

**先写的测试（RED）：**
```python
def test_malformed_llm_json_falls_back_to_text():
    raw = '{"day_plans": [bad json'
    result = parse_llm_output(raw)
    assert result.type == "text"          # 降级为纯文本，而不是崩溃
    assert result.error_code == "invalid_json"

def test_partial_itinerary_allows_null_budget():
    raw = '{"destination":"京都","days":7,"day_plans":[],"total_budget":null}'
    itin = parse_llm_output(raw).itinerary
    assert itin.total_budget is None       # 前端渲染为「待估算」
```

---

### H2. RAG 空库 / 低相关度 / 引用完整性的行为未定义

**问题：** 知识库分库设计（§4）很好，但以下路径没有行为定义：
- 用户提问时向量库为空（首次部署）→ 回答什么？
- Top-K 结果相关度低于阈值 → 拒绝回答还是硬答？
- citations 引用已被删除的攻略 → 前端点「参考」跳 404？

**TDD 暴露点：** retriever 是最容易 TDD 的纯函数（输入 query + 库，输出 Top-K），但方案没定义阈值和空态。

**先写的测试（RED）：**
```python
def test_retriever_empty_db_returns_no_citations():
    docs = retriever.search("冰岛", top_k=5)
    assert docs == []                      # 空库返回空，不抛异常

def test_retriever_low_relevance_is_rejected():
    docs = retriever.search("量子物理", top_k=5, min_score=0.3)
    assert docs == []                      # 低于阈值不放行

def test_citation_source_must_exist():
    # 任意 citation 的 source_id 必须存在于知识库
    for c in result.citations:
        assert store.exists(c.source_id)
```

---

### H3. 多轮对话上下文管理未定义

**问题：** assistant.html 是"多轮对话"，但方案未定义：上下文消息数上限？token 截断策略？滑动窗口？会话过期？每轮重发全部历史还是增量？这直接决定 RAG pipeline 的输入构造，无法写测试。

**先写的测试（RED）：**
```python
def test_context_truncates_oldest_messages():
    ctx = build_context(history, max_tokens=2000)
    assert ctx.first_message == history[-3]   # 只保留最近 3 轮

def test_oversized_single_message_is_truncated():
    ctx = build_context([{"text": "x" * 100_000}], max_tokens=2000)
    assert len(ctx.text) <= 2000
```

---

### H4. 前端组件零测试定义

**问题：** §8 列出 16 个共享组件，但没有任何一个组件定义了测试。尤其两个核心组件：
- `ItineraryCard`：`day_plans: []` 空数组？天数 > 10？预算 null？这些渲染边界未定义
- `ChatWindow`：SSE 连接中 / 中断 / 重连 / 错误事件如何渲染？

**先写的测试（RED，前端）：**
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

---

### H5. 检索质量无度量指标

**问题：** M2 "正确引用样例攻略"，但方案没有定义 RAG 的质量度量（recall@k / 精确率 / 黄金问题集）。没有度量，就无法判断检索「是否变好」，后续调参无从谈起。

**需补入方案：** 10 篇样例攻略 → 配套 20-30 个黄金问答对（golden QA），建立 `backend/tests/golden_qa.json`，作为回归基准。

---

## 四、中严重度缺陷

### M1. 无构建环境与「抽共享组件」的工程矛盾

**问题：** 方案保持 CDN + Babel 无构建模式，但 `shared/components.js` 要跨页面复用。无构建环境下 `import/export` 不可用，只能靠 `<script>` 全局注入（`window.TravelComponents`）。方案未说明共享组件的加载与暴露方式，Phase 0 会卡壳。

**需补入方案：**
```html
<!-- 页面引用方式 -->
<script src="../shared/utils.js"></script>
<script src="../shared/components.js"></script>
<!-- components.js 顶部 -->
window.TravelMate = window.TravelMate || {};
window.TravelMate.Topbar = function(props){...};
```

### M2. 图标体系「二选一」未落地

**问题：** 首页修复清单 #8 写"`assets/icons/` 或内联 SVG 二选一"，但最终方案没有拍板。38 个 SVG 已在库里，渲染方式（css-mask vs 直接 `<img>` vs 内联）影响所有组件和测试。

**建议：** 采用内联 SVG 组件 + `assets/icons/` 留作 fallback/管理用途，一次定义，全站统一。

### M3. 执行顺序表与时间线不一致

**问题：** §4 把 Phase 0 + 1.5 + assistant + destination 全标为 P0，但 §9"立即"阶段只含后端骨架 + Phase 0 + 首页修复，未列 assistant/destination 页面。P0 与实际安排冲突，执行时会无所适从。

**建议：** 明确「本周交付物」= Phase 0 + Phase 1.5 骨架 + 测试策略落地；assistant/destination 移至「短期」。

### M4. 知识库入库无幂等性 / 版本控制设计

**问题：** "用户发布攻略 → 自动触发 ingest.py 入库"，但未定义：同一攻略重复发布？攻略更新后旧 chunk 如何处理（删除重建 vs 版本标记）？citations 指向旧版本？

**先写的测试（RED）：**
```python
def test_ingest_is_idempotent():
    ingest("guides/kyoto.md")
    count1 = count_chunks("kyoto-guide-01")
    ingest("guides/kyoto.md")            # 重复入库
    count2 = count_chunks("kyoto-guide-01")
    assert count1 == count2              # 不产生重复 chunk

def test_reingest_replaces_old_chunks():
    ingest("guides/kyoto.md", version=2)
    assert all(c.version == 2 for c in chunks_of("kyoto-guide-01"))
```

### M5. 无端到端关键路径测试

**问题：** 产品最核心的用户旅程——「首页搜索 → assistant 对话 → 行程生成 → 保存」——没有任何一条 E2E 测试定义。方案每个页面都规划了，但没有"串联验证"。

**需补入方案：**
```javascript
// Playwright E2E（关键路径）
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

## 五、建议的测试策略补充（需并入 FINAL_PLAN）

### 5.1 测试分层

| 层 | 框架 | 覆盖对象 | 运行 |
|----|------|----------|------|
| 单元 | pytest（后端）/ Vitest（前端） | Schema、预算计算、retriever、组件渲染 | 每次提交 |
| 集成 | pytest + FastAPI TestClient | API 端点 + Chroma/SQLite | 每次提交 |
| 契约 | pytest / 前端 parse fixture | SSE 事件、Itinerary JSON | 每次提交 |
| E2E | Playwright | 关键路径（§M5） | 每次发版 |
| 设计校验 | validate-design-workspace.mjs | 0 error + 0 新增 warning | CI 门禁 |

### 5.2 后端测试目录（并入目标结构）

```
backend/tests/
├── unit/
│   ├── test_schemas.py          # Itinerary / DayPlan 校验
│   ├── test_budget.py           # 分项求和 = 总额 等纯函数
│   └── test_retriever.py        # 空库 / 阈值 / Top-K 排序
├── integration/
│   ├── test_chat_api.py         # SSE 流、错误、超时
│   ├── test_trips_api.py        # CRUD + 401 + 权限
│   └── test_ingest.py           # 幂等性 / 版本替换
├── contract/
│   └── test_sse_contract.py     # 事件名 / 载荷 schema / done 终止
├── golden_qa.json               # 20-30 组黄金问答对
└── conftest.py
```

### 5.3 前端测试目录

```
frontend/tests/
├── components/
│   ├── ItineraryCard.test.jsx   # 空态 / 长天数 / null 预算
│   ├── ChatWindow.test.jsx      # 流式渲染 / 错误重试 / 重连
│   └── BudgetSummary.test.jsx   # 分项合计一致性
└── e2e/
    └── key-path.spec.js         # 首页 → 助手 → 行程 → 保存
```

---

## 六、缺陷 → 修复优先级对照

| 优先级 | 缺陷 | 修复动作 | 阻止什么 |
|--------|------|----------|----------|
| P0 | D1 无测试策略 | 补 §测试策略（5.1） | 整个 TDD 无法执行 |
| P0 | D3 SSE 契约未定义 | 补事件表 + 两侧契约测试 | assistant 前后端对接 |
| P0 | D2 验收标准不可验证 | M1-M5 每条配断言 | 里程碑无法收口 |
| P1 | H1 坏 JSON 兜底 | 定义降级链 + 3 个测试 | ItineraryCard 稳定性 |
| P1 | H2 RAG 边界 | 定义空库/阈值/引用完整性 | RAG 可靠性 |
| P1 | H3 上下文管理 | 定义窗口策略 | 多轮对话正确性 |
| P1 | H4 组件测试 | 补组件测试框架 | 共享组件复用安全 |
| P2 | H5 质量度量 | 建 golden_qa.json | 检索调参 |
| P2 | M1-M5 | 见各条 | 工程落地顺畅性 |

---

## 七、总结

| 维度 | 评价 |
|------|------|
| 架构与页面规划 | ✅ 完整、清晰 |
| 测试策略 | 🔴 **完全缺失（最高优先修复）** |
| 行为定义 | 🟠 SSE 契约、坏 JSON、RAG 边界、上下文均未定义 |
| 验收标准 | 🟠 依赖人工判断，不可自动验证 |
| 工程一致性 | 🟡 无构建 vs 共享组件、执行顺序冲突、图标未拍板 |

**下一步建议（按 TDD 顺序）：** 1）把 §五 测试策略并入 FINAL_PLAN；2）定义 SSE 契约（D3）；3）为 M1-M5 各写第一条 RED 测试再开工 Phase 0 / 1.5。

---

*可以继续帮你：1）把测试策略直接并入 FINAL_PLAN.md；2)为 Phase 0/1.5 逐条编写 RED 测试；3）起草 SSE 契约文档。*
