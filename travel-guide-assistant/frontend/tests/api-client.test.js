import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

import { describe, expect, test, vi } from "vitest";

const apiSource = fs.readFileSync(
  path.join(process.cwd(), "shared", "api.js"),
  "utf8"
);

function loadApi(fetchImpl) {
  const context = {
    Error,
    JSON,
    Promise,
    TextDecoder,
    fetch: fetchImpl,
    window: { TravelMate: { utils: { API_BASE: "http://test" } } }
  };

  vm.runInNewContext(apiSource, context, { filename: "shared/api.js" });
  return context.window.TravelMate.api;
}

function sseResponse(chunks) {
  let index = 0;
  return {
    ok: true,
    body: {
      getReader() {
        return {
          read() {
            if (index >= chunks.length) return Promise.resolve({ done: true });
            return Promise.resolve({
              done: false,
              value: new TextEncoder().encode(chunks[index++])
            });
          }
        };
      }
    }
  };
}

describe("TravelMate API client", () => {
  test("uses the loopback API default when no runtime override is provided", () => {
    const context = {
      Error,
      JSON,
      Promise,
      TextDecoder,
      fetch: () => Promise.reject(new Error("not called")),
      window: { TravelMate: {} }
    };

    vm.runInNewContext(apiSource, context, { filename: "shared/api.js" });
    expect(context.window.TravelMate.api).toBeDefined();
    expect(apiSource).toContain("http://127.0.0.1:8000");
  });

  test("dispatches SSE message, itinerary, and done events", async () => {
    const itinerary = {
      destination: "京都",
      days: 7,
      total_budget: 8500,
      day_plans: [],
      tips: []
    };
    const api = loadApi(() => Promise.resolve(sseResponse([
      "event: message\ndata: {\"text\":\"ready\",\"citations\":[]}\n\n",
      `event: itinerary\ndata: ${JSON.stringify(itinerary)}\n\n`,
      "event: done\ndata: {\"id\":\"chat-1\"}\n\n"
    ])));
    const received = { message: null, itinerary: null, done: null };

    await new Promise((resolve) => {
      api.chatStream("春节去日本玩7天", {
        onMessage: (payload) => { received.message = payload; },
        onItinerary: (payload) => { received.itinerary = payload; },
        onDone: (payload) => { received.done = payload; resolve(); }
      });
    });

    expect(received.message).toEqual({ text: "ready", citations: [] });
    expect(received.itinerary).toEqual(itinerary);
    expect(received.done).toEqual({ id: "chat-1" });
  });

  test("sends the session id and bounded conversation history", async () => {
    let request;
    const api = loadApi((url, options) => {
      request = { url, options };
      return Promise.resolve(sseResponse([
        "event: done\\ndata: {}\\n\\n"
      ]));
    });

    await api.chatStream(
      "继续安排交通",
      { onDone: () => {} },
      [
        { role: "user", content: "我想去京都" },
        { role: "assistant", content: "可以先安排京都市内交通" }
      ],
      "session-123"
    );

    expect(request.url).toBe("http://test/api/chat");
    expect(JSON.parse(request.options.body)).toEqual({
      message: "继续安排交通",
      history: [
        { role: "user", content: "我想去京都" },
        { role: "assistant", content: "可以先安排京都市内交通" }
      ],
      session_id: "session-123"
    });
  });

  test("forwards the abort signal and invokes onAbort when cancelled", async () => {
    const controller = new AbortController();
    let forwardedSignal = null;
    const api = loadApi((url, options) => {
      forwardedSignal = options.signal;
      return new Promise((resolve, reject) => {
        controller.signal.addEventListener("abort", () => {
          const err = new Error("The user aborted a request.");
          err.name = "AbortError";
          reject(err);
        });
      });
    });
    const onAbort = vi.fn();
    const onError = vi.fn();

    api.chatStream("取消这次回答", { onAbort, onError, signal: controller.signal });
    await new Promise((resolve) => setTimeout(resolve, 0));
    controller.abort();

    await vi.waitFor(() => expect(onAbort).toHaveBeenCalledTimes(1));
    expect(forwardedSignal).toBe(controller.signal);
    expect(onError).not.toHaveBeenCalled();
  });

  test("surfaces a friendly error when the chat endpoint is rate limited", async () => {
    const api = loadApi(() => Promise.resolve({
      ok: false,
      status: 429,
      json: () => Promise.resolve({
        code: "rate_limited",
        message: "请求太频繁，请稍后再试。",
        retry_after: 42
      })
    }));
    const onError = vi.fn();

    await api.chatStream("再来一次", { onError });
    await vi.waitFor(() => expect(onError).toHaveBeenCalledTimes(1));

    expect(onError).toHaveBeenCalledWith({
      code: "rate_limited",
      message: "请求太频繁，请稍后再试。",
      retry_after: 42
    });
  });

  test("posts an itinerary and returns the saved trip", async () => {
    const itinerary = {
      destination: "京都",
      days: 7,
      total_budget: 8500,
      day_plans: [],
      tips: []
    };
    const savedTrip = { id: "trip-1", itinerary };
    let request;
    const api = loadApi((url, options) => {
      request = { url, options };
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(savedTrip)
      });
    });
    const onOk = vi.fn();

    api.saveTrip(itinerary, onOk);
    await vi.waitFor(() => expect(onOk).toHaveBeenCalledWith(savedTrip));

    expect(request.url).toBe("http://test/api/trips");
    expect(request.options.method).toBe("POST");
    expect(JSON.parse(request.options.body)).toEqual(itinerary);
  });

  test("lists saved trips", async () => {
    const trips = [{ id: "trip-1", destination: "京都" }];
    let request;
    const api = loadApi((url, options) => {
      request = { url, options };
      return Promise.resolve({ ok: true, json: () => Promise.resolve(trips) });
    });
    const onOk = vi.fn();

    api.listTrips(onOk);
    await vi.waitFor(() => expect(onOk).toHaveBeenCalledWith(trips));

    expect(request.url).toBe("http://test/api/trips");
    expect(request.options).toBeUndefined();
  });

  test("updates a saved trip", async () => {
    const itinerary = { destination: "大阪", days: 4, day_plans: [] };
    const savedTrip = { id: "trip-1", ...itinerary };
    let request;
    const api = loadApi((url, options) => {
      request = { url, options };
      return Promise.resolve({ ok: true, json: () => Promise.resolve(savedTrip) });
    });
    const onOk = vi.fn();

    api.updateTrip("trip-1", itinerary, onOk);
    await vi.waitFor(() => expect(onOk).toHaveBeenCalledWith(savedTrip));

    expect(request.url).toBe("http://test/api/trips/trip-1");
    expect(request.options.method).toBe("PUT");
    expect(JSON.parse(request.options.body)).toEqual(itinerary);
  });
});
