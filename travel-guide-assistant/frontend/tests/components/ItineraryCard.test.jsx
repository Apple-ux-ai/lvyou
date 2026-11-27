import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import "../../../shared/components.js";

const { ItineraryCard } = window.TravelMate.components;

describe("ItineraryCard", () => {
  test("renders the empty state when there are no day plans", () => {
    render(
      <ItineraryCard
        itinerary={{ destination: "京都", days: 0, total_budget: null, day_plans: [] }}
      />
    );

    expect(screen.getByText("暂无行程安排")).toBeInTheDocument();
  });

  test("renders the pending budget label when total_budget is null", () => {
    render(
      <ItineraryCard
        itinerary={{ destination: "京都", days: 1, total_budget: null, day_plans: [] }}
      />
    );

    expect(screen.getByText("预算待估算")).toBeInTheDocument();
  });

  test("calls onSave when the save button is clicked", () => {
    const onSave = vi.fn();
    const itinerary = {
      destination: "京都",
      days: 1,
      total_budget: 3200,
      day_plans: []
    };

    render(<ItineraryCard itinerary={itinerary} onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "保存行程" }));

    expect(onSave).toHaveBeenCalledTimes(1);
  });

  test("renders day titles and activities for a normal itinerary", () => {
    render(
      <ItineraryCard
        itinerary={{
          destination: "京都",
          days: 1,
          total_budget: 3200,
          day_plans: [
            {
              day: 1,
              title: "古都漫步",
              activities: ["参观清水寺", "漫步祇园"]
            }
          ]
        }}
      />
    );

    expect(screen.getByText("古都漫步")).toBeInTheDocument();
    expect(screen.getByText("参观清水寺")).toBeInTheDocument();
    expect(screen.getByText("漫步祇园")).toBeInTheDocument();
  });
});
