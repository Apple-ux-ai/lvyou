# Assistant Rich Responses Design

**Date:** 2026-08-10
**Status:** User-approved design, pending specification review

## Goal

Make the assistant conversation useful on its own instead of showing a generic `行程已生成。` acknowledgement. Every assistant response should be easy to scan, while the full itinerary preview remains the detailed planning surface.

The accepted visual direction is:

- Itinerary replies use the balanced summary option: conclusion, total budget, grouped route highlights, one important tip, and a `查看完整行程` action.
- General replies use the approved adaptive option: conclusion, supporting paragraph, sections, key facts, one warning when relevant, and citations.
- Short answers remain short. Rich structure is conditional on the response content rather than a mandatory fixed template.

## Scope

This change covers assistant-message content, rendering, and the general-answer generation instruction.

In scope:

- Enrich itinerary messages from the existing structured `itinerary` SSE event.
- Improve safe structured rendering for all ordinary assistant answers.
- Add a responsive link from the itinerary summary to the complete preview.
- Preserve streaming, citation, save, and planner workflows.
- Add focused frontend, backend, and browser tests.

Out of scope:

- Replacing the current SSE event contract.
- Redesigning the full assistant page, top navigation, input bar, or complete itinerary preview.
- Fixing citation destinations, session history, retrieval quality, or trip persistence.
- Introducing a full Markdown library or allowing model-generated HTML.
- Migrating the page to Vite as part of this change.

## Content Model

### Itinerary replies

The `message` SSE event may continue to contain the backend acknowledgement. The `itinerary` event is the source of truth for the rich conversation summary.

The frontend attaches the received itinerary payload to the bot message created for the active request. The conversation summary derives:

- Title: `<destination> <days> 天经典路线`.
- Lead: a short route description assembled from the available day titles.
- Budget: `total_budget` formatted per person, omitted when absent.
- Route: at most four contiguous day groups. Each group shows a day range and the distinct day titles in that range.
- Tip: the first non-empty itinerary tip, omitted when no tips exist.
- Action: a real anchor labeled `查看完整行程` targeting the existing preview region.

The full day activities, transport, all tips, saving controls, and planner actions remain only in the right-side preview. This avoids duplicating the complete itinerary in the conversation.

### General replies

The backend general-answer instruction asks for concise Chinese Markdown-like output with adaptive structure:

- Start with a direct conclusion.
- Add headings and bullet or numbered lists only when the answer benefits from them.
- Use at most three content sections.
- Express compact facts as `- **标签**：值` entries when useful.
- Use one blockquote for a material warning or policy caveat when relevant.
- Do not emit HTML, tables, decorative headings, or filler sections.
- Keep a one-sentence answer as one sentence.

The frontend supports only the following safe subset:

- Paragraphs.
- Level 1-3 headings.
- Bold inline spans.
- Ordered and unordered lists.
- Consecutive label-value list entries rendered as a compact fact row.
- Blockquotes rendered as a warning note.

Unsupported syntax stays visible as plain text. Model output is never passed to `dangerouslySetInnerHTML`.

## Frontend Architecture

### Message state

Each bot message keeps its existing `text` and `citations` fields and may add:

- `itinerary`: the structured payload for itinerary replies.
- `topic`: a small presentation hint derived from the originating user message, such as itinerary, visa, weather, budget, transport, or general.

The `onItinerary` handler updates both the page-level preview state and the active bot message in one functional state update. The update uses the existing request message index so an itinerary cannot attach to a previous response.

### Components and helpers

Keep the change within the current page architecture, but separate responsibilities into focused functions:

- `StructuredMessage`: parses and renders the safe response subset.
- `ItineraryConversationSummary`: renders the accepted balanced itinerary summary.
- `buildItineraryRouteGroups`: pure helper that turns day plans into at most four display groups.
- `detectResponseTopic`: pure helper used only to select a relevant existing icon.
- `ChatBubble`: selects itinerary-summary or general structured-message presentation and owns citations.

Pure formatting helpers should live in a reusable shared script so Vitest can exercise the same logic used by the page. React components may remain in the existing inline page script to avoid a framework migration in this scope.

### Interaction and responsive behavior

The preview region receives a stable `id`. `查看完整行程` is an anchor, so it works without custom navigation code, keyboard users can activate it normally, and mobile users scroll to the stacked preview.

Desktop behavior:

- The conversation summary stays within the existing bot-message width.
- Route rows use a stable day-label column and a flexible text column.
- Key facts use up to three columns and wrap without changing the bubble width.

Mobile behavior:

- Header metadata stacks when necessary.
- Fact rows become vertical label-value rows.
- Route text wraps; no horizontal scrolling is introduced.
- The preview anchor scrolls to the preview below the chat panel.

## Visual System

Use existing theme tokens and page typography. Do not add a second card inside the bot bubble.

- The bot bubble remains the only framed response surface.
- Sections are separated with spacing and quiet dividers.
- One soft accent surface may identify a material warning.
- Topic icons use the existing icon family and current stroke treatment.
- Radius stays at 8px or the page's existing message radius.
- Text sizes remain appropriate for a dense product surface; no viewport-scaled type.
- Motion is limited to the existing streaming indicator and native smooth page navigation behavior.

## Backend Changes

The itinerary JSON-generation instruction is unchanged. The backend may keep `行程已生成。` as the message event because the frontend will replace its visual role with the structured itinerary summary.

Only the general-answer instruction in `RAGChatService._build_messages` changes. It must preserve retrieved source context and existing conversation history while requesting the adaptive Chinese structure described above.

The deterministic local fallback should return a useful Chinese answer instead of an English `Local response:` prefix, but it must not invent retrieved facts. When no evidence exists, it should clearly identify the response as a local fallback.

## Streaming and Failure States

- While text is streaming, the current typing state remains visible.
- General text progressively uses the structured renderer as complete lines arrive.
- The itinerary summary appears only after a valid `itinerary` event arrives.
- If itinerary generation fails, the normal backend error text remains in the bot bubble and no empty summary is shown.
- Missing destination, day plans, budget, tips, or citations causes the corresponding optional region to be omitted rather than replaced with invented data.
- A short or malformed Markdown-like answer falls back to safe paragraphs.

## Testing

Follow test-driven development for implementation.

Frontend unit tests cover:

- Day plans are grouped into no more than four contiguous route groups.
- Missing budget and tips omit those regions.
- Itinerary payload updates the correct bot message.
- General headings, lists, fact entries, and blockquotes render as semantic elements.
- Raw HTML remains text and never becomes executable markup.
- One-sentence answers remain visually compact.

Backend unit tests cover:

- The general-answer prompt requests adaptive Chinese structure and forbids HTML.
- The itinerary prompt and itinerary parsing behavior remain unchanged.
- The deterministic fallback is Chinese, explicit about degraded mode, and does not claim sources it did not receive.

Browser QA covers:

- An itinerary request renders the accepted balanced summary and the existing complete preview.
- `查看完整行程` reaches the preview on desktop and mobile.
- A visa or similar informational question renders the approved adaptive general-answer structure.
- A short answer does not gain empty sections.
- No clipping, horizontal overflow, framework overlay, or relevant console error appears at desktop and mobile widths.

## Acceptance Criteria

- The screenshot case no longer shows only `行程已生成。` in the left conversation.
- Itinerary replies show the accepted balanced summary without duplicating full day details.
- All ordinary assistant replies support the approved adaptive structure.
- Short responses remain concise.
- The preview link is keyboard-accessible and works in both responsive layouts.
- Model text is rendered without HTML injection.
- Existing trip preview, save, and planner behavior remains intact.
- Focused tests and the existing frontend/backend suites pass.
