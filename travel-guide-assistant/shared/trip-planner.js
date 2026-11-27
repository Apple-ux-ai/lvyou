(function () {
  function fromApi(plan) {
    return {
      id: plan.id,
      title: plan.destination + " " + plan.days + " 天行程",
      destination: plan.destination,
      days: plan.days,
      totalBudget: plan.total_budget ?? null,
      startDate: plan.start_date ?? "",
      adultCount: plan.adult_count ?? "",
      attractionCap: plan.attraction_cap_jpy ?? "",
      tips: plan.tips || [],
      dayPlans: (plan.day_plans || []).map((day) => ({
        day: day.day,
        title: day.title || "第 " + day.day + " 天",
        transport: day.transport ?? null,
        legacyBudget: day.budget == null ? null
          : Math.max(0, day.budget - (day.stops || []).reduce((sum, stop) => sum + (stop.budget ?? 0), 0)),
        items: (day.stops ?? (day.activities || []).map((name) => ({ name }))).map((stop, i) => ({
          id: day.day + "-" + i,
          text: stop.name,
          time: stop.visit_time ?? "",
          cat: stop.category ?? "other",
          budget: stop.budget ?? null
        }))
      }))
    };
  }

  function dayBudget(day) {
    if (day.legacyBudget == null && day.items.every((item) => item.budget == null)) return null;
    return day.items.reduce((sum, item) => sum + (item.budget ?? 0), day.legacyBudget ?? 0);
  }

  function optionalNumber(value) {
    return value === "" || value == null ? null : Number(value);
  }

  function toApi(trip) {
    return {
      destination: trip.destination,
      days: trip.days,
      total_budget: trip.totalBudget ?? null,
      start_date: trip.startDate || null,
      adult_count: optionalNumber(trip.adultCount),
      attraction_cap_jpy: optionalNumber(trip.attractionCap),
      tips: trip.tips || [],
      day_plans: trip.dayPlans.map((day) => ({
        day: day.day,
        title: day.title,
        activities: day.items.map((item) => item.text),
        transport: day.transport ?? null,
        budget: dayBudget(day),
        stops: day.items.map((item) => ({
          name: item.text,
          visit_time: item.time || null,
          category: item.cat || "other",
          budget: item.budget ?? null
        }))
      }))
    };
  }
  window.TravelMate = window.TravelMate || {};
  window.TravelMate.planner = { fromApi, toApi, dayBudget };
})();
