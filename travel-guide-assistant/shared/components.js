(function (global) {
  "use strict";

  function createElement(type, props) {
    var children = Array.prototype.slice.call(arguments, 2);
    return global.React.createElement.apply(global.React, [type, props].concat(children));
  }

  function formatBudget(totalBudget) {
    if (totalBudget == null) {
      return "预算待估算";
    }

    return "预算：¥" + Number(totalBudget).toLocaleString();
  }

  function ItineraryCard(props) {
    var itinerary = props.itinerary || {};
    var dayPlans = Array.isArray(itinerary.day_plans) ? itinerary.day_plans : [];
    var onSave = typeof props.onSave === "function" ? props.onSave : function () {};
    var dayPlanElements = dayPlans.map(function (dayPlan, index) {
      var activities = Array.isArray(dayPlan.activities) ? dayPlan.activities : [];

      return createElement(
        "li",
        { key: String(dayPlan.day == null ? index + 1 : dayPlan.day) },
        createElement("h3", null, dayPlan.title || "第" + (index + 1) + "天"),
        createElement(
          "ul",
          null,
          activities.map(function (activity, activityIndex) {
            return createElement("li", { key: activityIndex }, activity);
          })
        )
      );
    });

    return createElement(
      "article",
      { className: "itinerary-card", "data-testid": "itinerary-card" },
      createElement(
        "header",
        null,
        createElement("h2", null, itinerary.destination || "旅行行程"),
        createElement("p", null, formatBudget(itinerary.total_budget))
      ),
      dayPlans.length === 0
        ? createElement("p", { className: "empty-itinerary" }, "暂无行程安排")
        : createElement("ol", { className: "day-list" }, dayPlanElements),
      createElement(
        "button",
        { type: "button", onClick: function () { onSave(itinerary); } },
        "保存行程"
      )
    );
  }

  function renderInlineText(text, keyPrefix) {
    return String(text || "").split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map(function (part, index) {
      var bold = part.match(/^\*\*([^*]+)\*\*$/);
      return bold
        ? createElement("strong", { key: keyPrefix + "-bold-" + index }, bold[1])
        : createElement(global.React.Fragment, { key: keyPrefix + "-text-" + index }, part);
    });
  }

  function StructuredMessage(props) {
    var helpers = global.TravelMate && global.TravelMate.assistantResponses;
    var blocks = helpers ? helpers.parseStructuredBlocks(props.text) : [];
    var content = createElement(
      "div",
      { className: "structured-message" },
      blocks.map(function (block, index) {
        if (block.type === "heading") {
          return createElement(
            "h3",
            { className: "message-heading", key: index },
            renderInlineText(block.text, "heading-" + index)
          );
        }

        if (block.type === "quote") {
          return createElement(
            "aside",
            { className: "message-note", key: index, role: "note" },
            block.text
          );
        }

        if (block.type === "facts") {
          return createElement(
            "dl",
            { className: "message-facts", key: index },
            block.items.map(function (item, itemIndex) {
              return createElement(
                "div",
                { className: "message-fact", key: itemIndex },
                createElement("dt", null, item.label),
                createElement("dd", null, item.value)
              );
            })
          );
        }

        if (block.type === "list") {
          return createElement(
            block.ordered ? "ol" : "ul",
            { className: "message-list", key: index },
            block.items.map(function (item, itemIndex) {
              return createElement(
                "li",
                { key: itemIndex },
                renderInlineText(item, "list-" + index + "-" + itemIndex)
              );
            })
          );
        }

        return createElement(
          "p",
          { className: "message-paragraph", key: index },
          renderInlineText(block.text, "paragraph-" + index)
        );
      })
    );

    if (!props.leadingIcon) return content;

    return createElement(
      "div",
      { className: "structured-message-layout" },
      createElement("span", { className: "message-topic-icon", "aria-hidden": "true" }, props.leadingIcon),
      content
    );
  }

  function ItineraryConversationSummary(props) {
    var itinerary = props.itinerary || {};
    var helpers = global.TravelMate && global.TravelMate.assistantResponses;
    var groups = helpers ? helpers.buildItineraryRouteGroups(itinerary.day_plans) : [];
    var firstTip = Array.isArray(itinerary.tips) ? itinerary.tips.find(Boolean) : null;
    var leadTitles = groups.map(function (group) { return group.title; }).filter(Boolean).slice(0, 2);
    var lead = leadTitles.length
      ? "路线覆盖 " + leadTitles.join("、") + (groups.length > 2 ? "等" : "") + "，兼顾体验与通行效率。"
      : "已根据你的需求整理好路线，完整安排可在行程预览中查看。";
    var title = [itinerary.destination, itinerary.days, "天经典路线"].filter(Boolean).join(" ");

    return createElement(
      "article",
      { className: "conversation-itinerary" },
      createElement(
        "header",
        { className: "conversation-itinerary-head" },
        createElement(
          "div",
          { className: "conversation-itinerary-heading" },
          props.headerIcon
            ? createElement("span", { className: "conversation-itinerary-icon", "aria-hidden": "true" }, props.headerIcon)
            : null,
          createElement(
            "div",
            null,
            createElement("h3", null, title),
            createElement("p", null, lead)
          )
        ),
        itinerary.total_budget == null
          ? null
          : createElement(
              "strong",
              { className: "conversation-budget" },
              "¥" + Number(itinerary.total_budget).toLocaleString() + " / 人"
            )
      ),
      groups.length
        ? createElement(
            "div",
            { className: "conversation-route" },
            groups.map(function (group) {
              return createElement(
                "div",
                { className: "conversation-route-row", key: group.label },
                createElement("b", null, group.label),
                createElement("span", null, group.title)
              );
            })
          )
        : null,
      firstTip
        ? createElement(
            "p",
            { className: "conversation-tip" },
            props.tipIcon
              ? createElement("span", { "aria-hidden": "true" }, props.tipIcon)
              : null,
            createElement("span", null, firstTip)
          )
        : null,
      createElement(
        "a",
        { className: "conversation-preview-link", href: props.previewHref || "#itinerary-preview" },
        "查看完整行程",
        props.actionIcon
          ? createElement("span", { "aria-hidden": "true" }, props.actionIcon)
          : null
      )
    );
  }

  global.TravelMate = global.TravelMate || {};
  global.TravelMate.components = global.TravelMate.components || {};
  global.TravelMate.components.ItineraryCard = ItineraryCard;
  global.TravelMate.components.StructuredMessage = StructuredMessage;
  global.TravelMate.components.ItineraryConversationSummary = ItineraryConversationSummary;
})(window);
