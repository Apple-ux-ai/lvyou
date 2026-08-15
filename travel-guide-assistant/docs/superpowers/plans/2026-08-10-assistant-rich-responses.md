# Assistant Rich Responses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace minimal assistant acknowledgements with adaptive, safe, structured responses for itinerary and general questions.

**Architecture:** Add a shared response parser and itinerary grouping helper that both Vitest and the assistant page use. Add reusable React response components to the existing global component registry, wire itinerary SSE payloads into the active conversation message, and update only the general backend prompt/fallback behavior. Keep the existing SSE contract and full right-side itinerary preview unchanged.

**Tech Stack:** Vanilla JavaScript globals, React 18 UMD, Babel Standalone, Vitest, Testing Library, FastAPI/Pydantic service tests, in-app Browser QA.

---

### Task 1: Shared response parsing and itinerary grouping

**Files:**
- Create: `shared/assistant-response.js`
- Create: `frontend/tests/assistant-response.test.js`

- [ ] **Step 1: Write failing parser and grouping tests**

```javascript
import "../../shared/assistant-response.js";

const helpers = window.TravelMate.assistantResponses;

test("parses headings, facts, quotes, and paragraphs without HTML", () => {
  expect(helpers.parseStructuredBlocks([
    "## 需要提前办理日本签证",
    "五一建议提前准备。",
    "- **建议预留**：4-6 周",
    "- **常见类型**：单次旅游签",
    "> 材料要求以使领馆通知为准。",
    "<img src=x onerror=alert(1)>"
  ].join("\n"))).toEqual([
    { type: "heading", level: 2, text: "需要提前办理日本签证" },
    { type: "paragraph", text: "五一建议提前准备。" },
    { type: "facts", items: [
      { label: "建议预留", value: "4-6 周" },
      { label: "常见类型", value: "单次旅游签" }
    ] },
    { type: "quote", text: "材料要求以使领馆通知为准。" },
    { type: "paragraph", text: "<img src=x onerror=alert(1)>" }
  ]);
});

test("keeps one sentence compact", () => {
  expect(helpers.parseStructuredBlocks("建议提前购买可退改机票。")).toEqual([
    { type: "paragraph", text: "建议提前购买可退改机票。" }
  ]);
});

test("groups seven day plans into no more than four contiguous ranges", () => {
  const groups = helpers.buildItineraryRouteGroups(
    Array.from({ length: 7 }, (_, index) => ({ day: index + 1, title: `路线 ${index + 1}` }))
  );
  expect(groups).toHaveLength(4);
  expect(groups.map((group) => group.label)).toEqual(["D1-2", "D3-4", "D5-6", "D7"]);
  expect(groups[0].title).toBe("路线 1 · 路线 2");
});

test("detects presentation topics from the originating question", () => {
  expect(helpers.detectResponseTopic("日本签证怎么办")).toBe("visa");
  expect(helpers.detectResponseTopic("五一去日本玩 7 天")).toBe("itinerary");
  expect(helpers.detectResponseTopic("有什么建议")).toBe("general");
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `npm test -- frontend/tests/assistant-response.test.js`  
Expected: FAIL because `shared/assistant-response.js` does not exist.

- [ ] **Step 3: Implement the shared helper API**

Create an IIFE at `shared/assistant-response.js` exposing:

```javascript
(function (global) {
  "use strict";

  function parseFact(text) {
    var match = text.match(/^\*\*([^*]+)\*\*[：:]\s*(.+)$/);
    return match ? { label: match[1].trim(), value: match[2].trim() } : null;
  }

  function parseStructuredBlocks(text) {
    var lines = String(text || "").split("\n");
    var blocks = [];
    var index = 0;
    while (index < lines.length) {
      var line = lines[index].trim();
      if (!line) { index += 1; continue; }
      var heading = line.match(/^(#{1,3})\s+(.+)$/);
      if (heading) {
        blocks.push({ type: "heading", level: heading[1].length, text: heading[2].trim() });
        index += 1;
        continue;
      }
      if (line.indexOf("> ") === 0) {
        blocks.push({ type: "quote", text: line.slice(2).trim() });
        index += 1;
        continue;
      }
      var marker = line.match(/^([-*]|\d+[.)])\s+(.+)$/);
      if (marker) {
        var ordered = /^\d/.test(marker[1]);
        var items = [];
        while (index < lines.length) {
          var candidate = lines[index].trim();
          var next = candidate.match(ordered ? /^\d+[.)]\s+(.+)$/ : /^[-*]\s+(.+)$/);
          if (!next) break;
          items.push(next[1].trim());
          index += 1;
        }
        var facts = ordered ? [] : items.map(parseFact);
        blocks.push(!ordered && facts.every(Boolean)
          ? { type: "facts", items: facts }
          : { type: "list", ordered: ordered, items: items });
        continue;
      }
      blocks.push({ type: "paragraph", text: line });
      index += 1;
    }
    return blocks;
  }

  function buildItineraryRouteGroups(dayPlans, maxGroups) {
    var plans = Array.isArray(dayPlans) ? dayPlans.filter(Boolean) : [];
    var limit = Math.max(1, Number(maxGroups) || 4);
    if (!plans.length) return [];
    var size = Math.ceil(plans.length / limit);
    var groups = [];
    for (var index = 0; index < plans.length; index += size) {
      var slice = plans.slice(index, index + size);
      var start = slice[0].day == null ? index + 1 : slice[0].day;
      var end = slice[slice.length - 1].day == null ? index + slice.length : slice[slice.length - 1].day;
      groups.push({
        label: start === end ? "D" + start : "D" + start + "-" + end,
        title: slice.map(function (plan) { return plan.title; }).filter(Boolean).join(" · ")
      });
    }
    return groups.slice(0, limit);
  }

  function detectResponseTopic(text) {
    var value = String(text || "");
    if (/签证|入境|护照/.test(value)) return "visa";
    if (/天气|气温|下雨|穿什么/.test(value)) return "weather";
    if (/预算|花费|费用|多少钱/.test(value)) return "budget";
    if (/交通|地铁|火车|高铁|航班/.test(value)) return "transport";
    if (/行程|路线|规划|玩\s*\d+\s*天|去.+玩/.test(value)) return "itinerary";
    return "general";
  }

  global.TravelMate = global.TravelMate || {};
  global.TravelMate.assistantResponses = {
    parseStructuredBlocks: parseStructuredBlocks,
    buildItineraryRouteGroups: buildItineraryRouteGroups,
    detectResponseTopic: detectResponseTopic
  };
})(window);
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `npm test -- frontend/tests/assistant-response.test.js`  
Expected: 4 tests pass.

- [ ] **Step 5: Commit the isolated helper change**

```powershell
git add shared/assistant-response.js frontend/tests/assistant-response.test.js
git commit -m "feat: add assistant response parsing helpers"
```

### Task 2: Reusable rich response components

**Files:**
- Modify: `shared/components.js`
- Create: `frontend/tests/components/AssistantResponse.test.jsx`

- [ ] **Step 1: Write failing component tests**

Import both shared scripts, then assert:

```jsx
import "../../../shared/assistant-response.js";
import "../../../shared/components.js";

const { StructuredMessage, ItineraryConversationSummary } = window.TravelMate.components;

test("renders fact entries as a semantic definition list and keeps HTML inert", () => {
  const { container } = render(
    <StructuredMessage text={"- **建议预留**：4-6 周\n<img src=x onerror=alert(1)>"} />
  );
  expect(screen.getByText("建议预留")).toBeInTheDocument();
  expect(screen.getByText("4-6 周")).toBeInTheDocument();
  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
});

test("renders the balanced itinerary summary and omits absent optional fields", () => {
  render(<ItineraryConversationSummary itinerary={{
    destination: "日本",
    days: 2,
    total_budget: null,
    tips: [],
    day_plans: [
      { day: 1, title: "东京抵达" },
      { day: 2, title: "浅草漫步" }
    ]
  }} previewHref="#itinerary-preview" />);
  expect(screen.getByRole("heading", { name: "日本 2 天经典路线" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "查看完整行程" })).toHaveAttribute("href", "#itinerary-preview");
  expect(screen.queryByText(/预算/)).not.toBeInTheDocument();
  expect(screen.queryByText(/旅行提醒/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run focused component tests and verify RED**

Run: `npm test -- frontend/tests/components/AssistantResponse.test.jsx`  
Expected: FAIL because the two components are not exported.

- [ ] **Step 3: Add components to the global registry**

Extend `shared/components.js` without changing the existing `ItineraryCard` API:

```javascript
function renderInlineText(text, keyPrefix) {
  return String(text || "").split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map(function (part, index) {
    var bold = part.match(/^\*\*([^*]+)\*\*$/);
    return bold
      ? createElement("strong", { key: keyPrefix + "-bold-" + index }, bold[1])
      : createElement(global.React.Fragment, { key: keyPrefix + "-text-" + index }, part);
  });
}

function StructuredMessage(props) {
  var blocks = global.TravelMate.assistantResponses.parseStructuredBlocks(props.text);
  return createElement("div", { className: "structured-message" }, blocks.map(function (block, index) {
    if (block.type === "heading") return createElement("h3", { className: "message-heading", key: index }, renderInlineText(block.text, "h" + index));
    if (block.type === "quote") return createElement("aside", { className: "message-note", key: index, role: "note" }, block.text);
    if (block.type === "facts") return createElement("dl", { className: "message-facts", key: index }, block.items.map(function (item, itemIndex) {
      return createElement("div", { className: "message-fact", key: itemIndex }, createElement("dt", null, item.label), createElement("dd", null, item.value));
    }));
    if (block.type === "list") return createElement(block.ordered ? "ol" : "ul", { className: "message-list", key: index }, block.items.map(function (item, itemIndex) {
      return createElement("li", { key: itemIndex }, renderInlineText(item, "li" + index + "-" + itemIndex));
    }));
    return createElement("p", { className: "message-paragraph", key: index }, renderInlineText(block.text, "p" + index));
  }));
}

function ItineraryConversationSummary(props) {
  var itinerary = props.itinerary || {};
  var groups = global.TravelMate.assistantResponses.buildItineraryRouteGroups(itinerary.day_plans);
  var firstTip = Array.isArray(itinerary.tips) ? itinerary.tips.find(Boolean) : null;
  return createElement("article", { className: "conversation-itinerary" },
    createElement("header", { className: "conversation-itinerary-head" },
      createElement("div", null,
        createElement("h3", null, [itinerary.destination, itinerary.days, "天经典路线"].filter(Boolean).join(" ")),
        groups.length ? createElement("p", null, "按经典动线安排，完整每日活动可在行程预览中查看。") : null
      ),
      itinerary.total_budget == null ? null : createElement("strong", { className: "conversation-budget" }, "¥" + Number(itinerary.total_budget).toLocaleString() + " / 人")
    ),
    groups.length ? createElement("div", { className: "conversation-route" }, groups.map(function (group) {
      return createElement("div", { className: "conversation-route-row", key: group.label }, createElement("b", null, group.label), createElement("span", null, group.title));
    })) : null,
    firstTip ? createElement("p", { className: "conversation-tip" }, firstTip) : null,
    createElement("a", { className: "conversation-preview-link", href: props.previewHref || "#itinerary-preview" }, "查看完整行程")
  );
}

global.TravelMate.components.StructuredMessage = StructuredMessage;
global.TravelMate.components.ItineraryConversationSummary = ItineraryConversationSummary;
```

- [ ] **Step 4: Run component tests and the existing component suite**

Run: `npm test -- frontend/tests/components/AssistantResponse.test.jsx frontend/tests/components/ItineraryCard.test.jsx`  
Expected: all component tests pass.

- [ ] **Step 5: Commit the component change**

```powershell
git add shared/components.js frontend/tests/components/AssistantResponse.test.jsx
git commit -m "feat: render adaptive assistant responses"
```

### Task 3: Wire rich responses into the assistant page

**Files:**
- Modify: `pages/assistant.html`
- Modify: `frontend/tests/assistant-contract.test.js`

Preserve the pre-existing uncommitted `.itinerary-card{flex:0 0 auto;...}` change while editing this file.

- [ ] **Step 1: Add failing page contract assertions**

Add assertions that the page:

```javascript
expect(assistantSource).toContain('../shared/assistant-response.js');
expect(assistantSource).toContain('../shared/components.js');
expect(assistantSource).toContain('ItineraryConversationSummary');
expect(assistantSource).toContain('itinerary: payload');
expect(assistantSource).toContain('id="itinerary-preview"');
expect(assistantSource).toContain('detectResponseTopic(text)');
```

- [ ] **Step 2: Run the page contract test and verify RED**

Run: `npm test -- frontend/tests/assistant-contract.test.js`  
Expected: FAIL on the first missing shared response script assertion.

- [ ] **Step 3: Load shared scripts and select topic icons**

After the React UMD scripts and before the Babel page script, load:

```html
<script src="../shared/assistant-response.js"></script>
<script src="../shared/components.js"></script>
```

Inside the Babel script, bind:

```javascript
const { StructuredMessage, ItineraryConversationSummary } = window.TravelMate.components;
const { detectResponseTopic } = window.TravelMate.assistantResponses;
```

Delete the duplicate inline `renderInlineMarkdown` and `StructuredMessage` implementations. Keep topic icon selection in the page so it can use the existing SVG icon family.

- [ ] **Step 4: Attach itinerary payloads to the active bot message**

Create bot messages with a topic:

```javascript
const botMsg = { role: "bot", text: "", citations: [], topic: detectResponseTopic(text), itinerary: null };
```

Preserve `topic` and `itinerary` in every `onMessage` and `onDone` replacement. In `onItinerary`:

```javascript
onItinerary: (payload) => {
  setItinerary(payload);
  setMessages((prev) => {
    const next = [...prev];
    const idx = streamMsgIndexRef.current;
    if (idx >= 0 && idx < next.length) {
      next[idx] = { ...next[idx], itinerary: payload, citations: payload.citations || next[idx].citations || [] };
    }
    return next;
  });
},
```

- [ ] **Step 5: Render the selected response surface**

In `ChatBubble`, render:

```jsx
{msg.itinerary ? (
  <ItineraryConversationSummary itinerary={msg.itinerary} previewHref="#itinerary-preview" />
) : (
  <StructuredMessage text={msg.text} topic={msg.topic} />
)}
```

Keep citations below either response type. Add `id="itinerary-preview"` to the preview panel.

- [ ] **Step 6: Add accepted visual styles**

Add CSS for `.conversation-itinerary`, `.conversation-itinerary-head`, `.conversation-budget`, `.conversation-route`, `.conversation-route-row`, `.conversation-tip`, `.conversation-preview-link`, `.message-facts`, `.message-fact`, and `.message-note` using existing theme tokens. Use dividers rather than nested cards, keep radius at 8px, make fact rows three columns on desktop and one column on mobile, and ensure route text wraps.

- [ ] **Step 7: Run focused and full frontend tests**

Run: `npm test -- frontend/tests/assistant-contract.test.js frontend/tests/assistant-response.test.js frontend/tests/components/AssistantResponse.test.jsx`  
Expected: focused tests pass.

Run: `npm test`  
Expected: all frontend tests pass.

- [ ] **Step 8: Preserve the user's existing assistant hunk**

Run: `git diff -- pages/assistant.html`  
Expected: the original `flex:0 0 auto` itinerary-card change is still present along with the new rich-response changes. Do not stage or commit the file automatically because it contains overlapping user work.

### Task 4: Request adaptive general answers from the backend

**Files:**
- Modify: `backend/tests/unit/test_rag_chat.py`
- Modify: `backend/app/services/rag_chat.py`

- [ ] **Step 1: Write failing backend tests**

Add tests asserting the general system prompt contains the adaptive Chinese contract and the fallback is Chinese:

```python
@pytest.mark.asyncio
async def test_general_answer_prompt_requests_adaptive_chinese_structure():
    llm = SequenceLLM(["简短回答。"])
    service = RAGChatService(
        llm=llm,
        fallback_llm=SequenceLLM(["本地回答。"]),
        retriever=StubRetriever([], existing_ids=[]),
    )
    await service.respond(ChatRequest(message="日本签证怎么办"))
    system_prompt = llm.calls[0]["messages"][0]["content"]
    assert "Respond in Chinese" in system_prompt
    assert "Do not emit HTML" in system_prompt
    assert "Keep a one-sentence answer as one sentence" in system_prompt

@pytest.mark.asyncio
async def test_deterministic_fallback_is_explicit_chinese_degraded_answer():
    result = await DeterministicLocalLLM().complete(
        [{"role": "user", "content": "日本签证怎么办"}],
        itinerary=False,
    )
    assert "本地模式" in result
    assert "Local response:" not in result
```

- [ ] **Step 2: Run focused backend tests and verify RED**

Run: `cd backend; .venv\Scripts\python.exe -m pytest tests\unit\test_rag_chat.py -q`  
Expected: the two new tests fail on missing prompt/fallback text.

- [ ] **Step 3: Implement the general-answer instruction and fallback**

Add a constant such as:

```python
GENERAL_ANSWER_INSTRUCTION = (
    "Respond in Chinese. Start with a direct conclusion. Add at most three short sections "
    "with Markdown headings and ordered or unordered lists only when they improve clarity. "
    "Use '- **标签**：值' for compact facts and one '> 提醒' block only for a material caveat. "
    "Do not emit HTML, Markdown tables, decorative headings, or filler sections. "
    "Keep a one-sentence answer as one sentence. Use supplied sources when available."
)
```

Use it only when `itinerary` is false. Update the deterministic text fallback to:

```python
return f"本地模式暂时无法调用在线模型。关于“{user_text}”，请稍后重试，或补充更具体的问题以便使用本地规则处理。"
```

Do not alter itinerary JSON generation or parsing.

- [ ] **Step 4: Run focused and full backend tests**

Run: `cd backend; .venv\Scripts\python.exe -m pytest tests\unit\test_rag_chat.py -q`  
Expected: focused tests pass.

Run: `cd backend; .venv\Scripts\python.exe -m pytest -q`  
Expected: all backend tests pass.

- [ ] **Step 5: Commit the isolated backend change**

```powershell
git add backend/app/services/rag_chat.py backend/tests/unit/test_rag_chat.py
git commit -m "feat: request adaptive travel answers"
```

### Task 5: Browser fidelity and interaction verification

**Files:**
- No repository files unless verification exposes a defect.
- Save screenshots outside the repository.

- [ ] **Step 1: Start isolated review servers**

Start the frontend on a free local port and the backend with deterministic local-provider settings and a temporary trip database. Do not reuse a personal backend database.

- [ ] **Step 2: Verify the itinerary flow in the Browser plugin**

Target flow: `assistant.html -> submit 五一去日本玩7天，预算1万 -> balanced left summary + complete right preview -> activate 查看完整行程 -> preview reached`.

Check page identity, meaningful DOM, no framework overlay, console errors/warnings, and screenshot evidence.

- [ ] **Step 3: Verify adaptive general and compact answers**

Use a deterministic test response or Browser-safe interception to verify a structured visa answer renders heading/list/facts/note, and a one-sentence answer renders without empty sections.

- [ ] **Step 4: Verify responsive behavior**

Reset any previous viewport override, then test desktop and mobile sizes. Confirm fact rows stack, route text wraps, the preview link works, and no content overlaps or creates horizontal scrolling.

- [ ] **Step 5: Compare accepted concept and implementation**

Capture the latest desktop implementation screenshot outside the repository. Use `view_image` on the accepted concept screenshot and implementation screenshot. Compare copy hierarchy, bubble container, route rows, fact layout, warning treatment, spacing, and responsive behavior. Fix all material mismatches.

- [ ] **Step 6: Final regression and workspace audit**

Run: `npm test`  
Expected: all frontend tests pass.

Run: `cd backend; .venv\Scripts\python.exe -m pytest -q`  
Expected: all backend tests pass.

Run: `git diff --check`  
Expected: no whitespace errors in task changes.

Run: `git status --short`  
Expected: task files plus the preserved pre-existing `frontend/e2e/key-path.spec.js` and `pages/assistant.html` user work are visible; no temporary database, screenshot, or server log is tracked.
