# Assistant Response and Preview Design

## Goal

Improve the assistant page so model formatting is readable and destination-only travel requests produce a useful itinerary preview. The target example is `我想去贵州玩`.

## Behavior

- Bot messages render common Markdown-like structure as React elements: paragraphs, headings, bold text, unordered lists, and ordered lists.
- Rendering must not inject model-generated HTML. Unsupported syntax remains plain text.
- A request that clearly expresses travel intent and contains a destination, such as `我想去贵州玩`, generates an itinerary even when duration and budget are absent.
- Missing duration defaults to 5 days. Missing budget remains model-estimated.
- Explicit durations continue to take precedence over the default.
- Informational questions such as visa, weather, and transport questions remain text-only unless they explicitly ask for a route or trip plan.

## Architecture

The frontend adds a small structured-text renderer beside `ChatBubble` in `pages/assistant.html`. It parses lines into React nodes and parses bold spans without using `dangerouslySetInnerHTML`.

The backend extends `backend/app/rag/pipeline.py` with conservative destination extraction for phrases such as `想去...玩`, while preserving the existing known-destination mappings. Planning intent requires a destination plus an action or planning hint. `RAGChatService` uses 5 days when planning intent has no explicit duration.

## Empty and Loading States

While itinerary generation is running, the preview shows a compact generation state instead of the generic empty prompt. If a text-only answer completes, the current empty preview remains and explains that adding a duration will generate a plan.

## Testing

- Unit tests cover arbitrary destination extraction, destination-only planning intent, default 5-day generation, explicit-day precedence, and informational-question exclusion.
- Frontend tests cover structured message rendering without raw Markdown markers or HTML injection.
- Browser QA covers `我想去贵州玩` from input through a populated 5-day Guizhou preview on desktop and mobile.
