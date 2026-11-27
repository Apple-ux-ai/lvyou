# Assistant Response and Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render assistant text cleanly and generate a 5-day itinerary for destination-only travel requests.

**Architecture:** Keep Markdown-like rendering in the static React page as safe React nodes. Extend the existing backend intent pipeline with conservative phrase-based destination extraction and let the chat service supply the default duration. The preview panel uses existing `streaming` state for a compact generation state.

**Tech Stack:** Python/FastAPI/Pydantic, React via Babel in `pages/assistant.html`, Vitest, pytest, Playwright.

---

### Task 1: Destination-only plan intent

**Files:**
- Modify: `backend/app/rag/pipeline.py`
- Modify: `backend/tests/unit/test_rag_pipeline.py`

- [ ] **Step 1: Write failing unit tests**

```python
def test_detect_destination_extracts_destination_from_travel_phrase():
    assert detect_destination("我想去贵州玩") == "贵州"

def test_destination_only_request_is_plan_intent():
    assert is_plan_intent("我想去贵州玩") is True

def test_informational_question_is_not_plan_intent():
    assert is_plan_intent("贵州五一期间天气怎么样？") is False
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/unit/test_rag_pipeline.py -q`

- [ ] **Step 3: Implement conservative phrase extraction**

```python
TRAVEL_DESTINATION_PATTERN = re.compile(r"(?:想|准备|打算)?去(?P<destination>[\u4e00-\u9fff]{2,8})(?:玩|旅游|旅行|逛)")

def detect_destination(message: str) -> Optional[str]:
    # Keep existing known mappings first, then extract a destination from travel phrasing.
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/unit/test_rag_pipeline.py -q`

### Task 2: Default duration in itinerary responses

**Files:**
- Modify: `backend/app/services/rag_chat.py`
- Modify: `backend/tests/unit/test_rag_chat.py`

- [ ] **Step 1: Write failing service tests**

```python
async def test_destination_only_plan_uses_five_day_default():
    result = await service.respond(ChatRequest(message="我想去贵州玩"))
    assert "Generate exactly a 5-day itinerary" in llm.calls[0]["messages"][0]["content"]

async def test_explicit_duration_overrides_default():
    result = await service.respond(ChatRequest(message="去贵州玩3天"))
    assert result.itinerary.days == 3
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/unit/test_rag_chat.py -q`

- [ ] **Step 3: Implement the 5-day default only for planning messages without an explicit duration**

```python
if itinerary and detect_days(user_text) is None:
    instruction += " Generate exactly a 5-day itinerary because the traveller did not specify a duration."
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/unit/test_rag_chat.py -q`

### Task 3: Safe structured chat text and preview loading state

**Files:**
- Modify: `pages/assistant.html`
- Modify: `frontend/tests/assistant-contract.test.js`

- [ ] **Step 1: Write failing frontend source-contract tests**

```javascript
expect(assistantSource).toContain("function StructuredMessage")
expect(assistantSource).toContain("preview-loading")
expect(assistantSource).not.toContain("dangerouslySetInnerHTML")
```

- [ ] **Step 2: Run the frontend test and verify RED**

Run: `npm test -- frontend/tests/assistant-contract.test.js`

- [ ] **Step 3: Implement a React-node parser and loading panel**

```jsx
function StructuredMessage({ text }) {
  // Render headings, paragraphs, ordered/unordered lists, and **bold** spans as text nodes.
}

{itinerary ? <ItineraryCard ... /> : streaming ? <div className="preview-loading">正在生成行程...</div> : <div className="preview-empty">...</div>}
```

- [ ] **Step 4: Run the frontend test and verify GREEN**

Run: `npm test -- frontend/tests/assistant-contract.test.js`

### Task 4: Regression and rendered QA

**Files:**
- Modify: `frontend/e2e/key-path.spec.js`

- [ ] **Step 1: Add a destination-only E2E case**

```javascript
await page.locator(".chat-input").fill("我想去贵州玩");
await page.getByRole("button", { name: "发送" }).click();
await expect(page.getByTestId("itinerary-card")).toContainText("贵州 5 天行程");
```

- [ ] **Step 2: Run the new case, then the full suites**

Run: `npm run test:e2e -- --grep "destination-only"`

Run: `backend/.venv/Scripts/python.exe -m pytest -q`

Run: `npm test`

Run: `npm run test:e2e`

- [ ] **Step 3: Verify in the Browser**

Navigate to `/pages/assistant.html`, submit `我想去贵州玩`, and verify a populated 5-day Guizhou preview plus clean formatted bot text on desktop and mobile.
