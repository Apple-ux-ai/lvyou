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
      if (!line) {
        index += 1;
        continue;
      }

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

  function cleanMarkdownForDisplay(text) {
    return String(text || "")
      .replace(/^#{1,6}\s+/gm, "")
      .replace(/^(?:[-*]|\d+[.)])\s+/gm, "")
      .replace(/^>\s?/gm, "")
      .replace(/\*\*([^*]+)\*\*/g, "$1");
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
      var end = slice[slice.length - 1].day == null
        ? index + slice.length
        : slice[slice.length - 1].day;

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
    cleanMarkdownForDisplay: cleanMarkdownForDisplay,
    buildItineraryRouteGroups: buildItineraryRouteGroups,
    detectResponseTopic: detectResponseTopic
  };
})(window);
