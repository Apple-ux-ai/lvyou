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
    {
      type: "facts",
      items: [
        { label: "建议预留", value: "4-6 周" },
        { label: "常见类型", value: "单次旅游签" }
      ]
    },
    { type: "quote", text: "材料要求以使领馆通知为准。" },
    { type: "paragraph", text: "<img src=x onerror=alert(1)>" }
  ]);
});

test("cleans Markdown presentation markers while preserving content and line breaks", () => {
  expect(helpers.cleanMarkdownForDisplay([
    "## 核心推荐",
    "- **南清园**：巨蟒出山",
    "1. 天游峰",
    "> 提醒：山上天气多变。"
  ].join("\n"))).toBe([
    "核心推荐",
    "南清园：巨蟒出山",
    "天游峰",
    "提醒：山上天气多变。"
  ].join("\n"));
});

test("keeps ordinary text and literal HTML as text", () => {
  expect(helpers.cleanMarkdownForDisplay("<img src=x> 建议早点出发。")).toBe("<img src=x> 建议早点出发。");
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
