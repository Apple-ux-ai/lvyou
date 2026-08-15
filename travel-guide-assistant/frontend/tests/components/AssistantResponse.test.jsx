import React from "react";
import { render, screen } from "@testing-library/react";

import "../../../shared/assistant-response.js";
import "../../../shared/components.js";

const { StructuredMessage, ItineraryConversationSummary } = window.TravelMate.components;

test("renders fact entries semantically and keeps model HTML inert", () => {
  const { container } = render(
    <StructuredMessage text={"- **建议预留**：4-6 周\n<img src=x onerror=alert(1)>"} />
  );

  expect(screen.getByText("建议预留")).toBeInTheDocument();
  expect(screen.getByText("4-6 周")).toBeInTheDocument();
  expect(container.querySelector("dl")).toBeInTheDocument();
  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
});

test("renders headings, lists, and material caveats as structured elements", () => {
  render(
    <StructuredMessage text={"## 办理建议\n- 提前准备材料\n- 选择可退改机票\n> 具体要求以使领馆为准。"} />
  );

  expect(screen.getByRole("heading", { name: "办理建议" })).toBeInTheDocument();
  expect(screen.getByRole("list")).toBeInTheDocument();
  expect(screen.getByRole("note")).toHaveTextContent("具体要求以使领馆为准。");
});

test("renders the balanced itinerary summary and omits absent optional fields", () => {
  render(
    <ItineraryConversationSummary
      itinerary={{
        destination: "日本",
        days: 2,
        total_budget: null,
        tips: [],
        day_plans: [
          { day: 1, title: "东京抵达" },
          { day: 2, title: "浅草漫步" }
        ]
      }}
      previewHref="#itinerary-preview"
    />
  );

  expect(screen.getByRole("heading", { name: "日本 2 天经典路线" })).toBeInTheDocument();
  expect(screen.getByText("东京抵达")).toBeInTheDocument();
  expect(screen.getByText("浅草漫步")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "查看完整行程" })).toHaveAttribute("href", "#itinerary-preview");
  expect(screen.queryByText(/预算/)).not.toBeInTheDocument();
  expect(screen.queryByText(/旅行提醒/)).not.toBeInTheDocument();
});

test("renders budget and the first itinerary tip when present", () => {
  render(
    <ItineraryConversationSummary
      itinerary={{
        destination: "日本",
        days: 1,
        total_budget: 10000,
        tips: ["五一住宿紧张，建议提前预订。", "准备交通卡。"],
        day_plans: [{ day: 1, title: "东京城市漫游" }]
      }}
    />
  );

  expect(screen.getByText("¥10,000 / 人")).toBeInTheDocument();
  expect(screen.getByText("五一住宿紧张，建议提前预订。")).toBeInTheDocument();
  expect(screen.queryByText("准备交通卡。")).not.toBeInTheDocument();
});
