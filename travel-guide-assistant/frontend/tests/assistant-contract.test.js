import fs from "node:fs";
import path from "node:path";

import { expect, test } from "vitest";

const assistantSource = fs.readFileSync(
  path.join(process.cwd(), "pages", "assistant.html"),
  "utf8"
);

test("assistant page wires itinerary generation to trip saving", () => {
  expect(assistantSource).toContain("window.TravelMate.api.chatStream(");
  expect(assistantSource).toContain("window.TravelMate.api.saveTrip(itinerary");
  expect(assistantSource).toContain("setSavedTip(true)");
});

test("assistant safely renders streamed plain text and shows a preview loading state", () => {
  expect(assistantSource).toContain('../shared/assistant-response.js');
  expect(assistantSource).toContain('../shared/components.js');
  expect(assistantSource).toContain('className="plain-text-output"');
  expect(assistantSource).toContain('className="stream-cursor"');
  expect(assistantSource).toContain("cleanMarkdownForDisplay(streamTextRef.current)");
  expect(assistantSource).toContain("streamTargetCharsRef.current");
  expect(assistantSource).toContain("setTimeout(() => revealNextCharacter(question), 24)");
  expect(assistantSource).toContain('isStreaming={streaming && i === messages.length - 1 && m.role === "bot"}');
  expect(assistantSource).toContain("detectResponseTopic(text)");
  expect(assistantSource).toContain("itinerary: payload");
  expect(assistantSource).toContain('id="itinerary-preview"');
  expect(assistantSource).toContain("preview-loading");
  expect(assistantSource).not.toContain("StructuredMessage text={msg.text}");
  expect(assistantSource).not.toContain("ItineraryConversationSummary");
  expect(assistantSource).not.toContain("waitingForFirstChunk");
  expect(assistantSource).not.toContain('className="bubble bot streaming"');
  expect(assistantSource).not.toContain("dangerouslySetInnerHTML");
});

test("assistant can cancel an in-flight reply and start a new conversation", () => {
  expect(assistantSource).toContain("new AbortController()");
  expect(assistantSource).toContain("signal: abortRef.current.signal");
  expect(assistantSource).toContain("onAbort");
  expect(assistantSource).toContain("（已停止生成）");
  expect(assistantSource).toContain("停止生成");
  expect(assistantSource).toContain("新建对话");
  expect(assistantSource).toContain('className="stop-btn"');
  expect(assistantSource).toContain("createChatSessionId()");
});

test("assistant shows a specific message when the public demo is rate limited", () => {
  expect(assistantSource).toContain('payload.code === "rate_limited"');
  expect(assistantSource).toContain("payload.retry_after");
  expect(assistantSource).toContain("请求太频繁");
});
