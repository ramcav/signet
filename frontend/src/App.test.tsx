import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

class MockEventSource {
  static current: MockEventSource;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  handlers = new Map<string, EventListener>();
  readyState = 0;
  constructor() { MockEventSource.current = this; }
  addEventListener(name: string, handler: EventListener) { this.handlers.set(name, handler); }
  removeEventListener(name: string) { this.handlers.delete(name); }
  close() {}
  emit(type: string, run_id: string, data = {}, lastEventId = "") {
    act(() => this.handlers.get(type)?.(new MessageEvent(type, { data: JSON.stringify({ type, run_id, data, ts: 1 }), lastEventId })));
  }
}

let requestId: string;
let fetchMock: ReturnType<typeof vi.fn>;
const response = (body: unknown, ok = true, status = 200) => ({ ok, status, json: async () => body });

beforeEach(() => {
  requestId = "";
  vi.stubGlobal("EventSource", MockEventSource);
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/health") return response({});
    if (url === "/intents") {
      requestId = JSON.parse(init!.body as string).run_id ?? "server-run";
      return response({ run_id: requestId, status: "accepted" });
    }
    return response({ detail: "Approval service unavailable" }, false, 503);
  });
  vi.stubGlobal("fetch", fetchMock);
});

async function begin(scenario = "A") {
  render(<App />);
  if (scenario !== "A") fireEvent.click(screen.getByText(`Scenario ${scenario}: ${scenario === "B" ? "Jailbreak" : "Escalation"}`));
  fireEvent.click(screen.getByRole("button", { name: "Run" }));
  await waitFor(() => expect(requestId).toBeTruthy());
  await act(async () => {});
}

describe("application event and request handling", () => {
  it.each([
    undefined,
    "Configure the agent API key before submitting a payment.",
  ])("shows missing agent setup and prevents new runs (%s)", async (configurationError) => {
    fetchMock.mockResolvedValue(response({ agent_configured: false, configuration_error: configurationError }));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(configurationError ?? "Set OPENAI_API_KEY in backend/.env, then restart the backend to run scenarios.");
    const run = screen.getByRole("button", { name: "Setup required" });
    expect(run).toBeDisabled();
    fireEvent.click(run);
    expect(fetchMock.mock.calls.some(([url]) => url === "/intents")).toBe(false);
  });

  it("prevents recovering an unconfirmed request when health reports missing setup", async () => {
    let finishHealth: (value: unknown) => void = () => {};
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/health") return new Promise(resolve => { finishHealth = resolve; });
      if (url === "/intents") requestId = JSON.parse(init!.body as string).run_id;
      throw new TypeError("Network disconnected");
    });
    await begin();
    expect(await screen.findByRole("button", { name: "Recover original request" })).toBeEnabled();
    await act(async () => finishHealth(response({ agent_configured: false })));
    const recover = screen.getByRole("button", { name: "Recover original request" });
    expect(recover).toBeDisabled();
    fireEvent.click(recover);
    expect(fetchMock.mock.calls.filter(([url]) => url === "/intents")).toHaveLength(1);
  });

  it("keeps Run disabled while an approved payment is submitting", async () => {
    await begin("C");
    MockEventSource.current.emit("policy.escalated", requestId, { escalation_id: "esc", reason: "Over limit", notional_usd: 500, intent: { from: "source", to: "dest", amount: 100, asset: "XRP", rationale: "rebalance" } });
    MockEventSource.current.emit("run.completed", requestId, { decision: "escalate" });
    MockEventSource.current.emit("escalation.approved", requestId);
    MockEventSource.current.emit("ledger.submitting", requestId);
    expect(screen.getByRole("button", { name: /Running/ })).toBeDisabled();
  });

  it("does not restore an old pending snapshot after the approval response", async () => {
    await begin("C");
    MockEventSource.current.emit("policy.escalated", requestId, { escalation_id: "esc", reason: "Over limit", notional_usd: 500, intent: { from: "source", to: "dest", amount: 100, asset: "XRP", rationale: "rebalance" } });
    MockEventSource.current.emit("run.completed", requestId, { decision: "escalate" });
    let finish: (value: unknown) => void = () => {};
    fetchMock.mockImplementation((url: string) => url.startsWith("/runs/")
      ? new Promise(resolve => { finish = resolve; })
      : Promise.resolve(response({ run_id: requestId, decision: "allow", tx: { outcome: "success", validated: true, engine_result: "tesSUCCESS" } })));
    act(() => MockEventSource.current.onopen?.());
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(screen.getByText("approved", { exact: true })).toBeInTheDocument());
    await act(async () => finish(response({ run_id: requestId, status: "escalate", tx: null })));
    expect(screen.getByText("approved", { exact: true })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run" })).toBeEnabled();
  });

  it("retries an unconfirmed request with the same idempotency ID", async () => {
    let calls = 0;
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/health") return response({});
      if (url.startsWith("/runs/")) return response({ detail: "unknown run" }, false, 404);
      requestId = JSON.parse(init!.body as string).run_id;
      if (calls++ === 0) throw new TypeError("Network disconnected");
      return response({ run_id: requestId, status: "accepted" });
    });
    await begin();
    const originalId = requestId;
    fireEvent.click(await screen.findByRole("button", { name: "Recover original request" }));
    await waitFor(() => expect(calls).toBe(2));
    expect(requestId).toBe(originalId);
    expect(screen.getByRole("button", { name: /Running/ })).toBeDisabled();
  });

  it("accepts lower event IDs after the server resets its stream", async () => {
    await begin();
    MockEventSource.current.emit("agent.thinking", requestId, {}, "99");
    MockEventSource.current.emit("stream.reset", "", { reason: "restart" }, "0");
    MockEventSource.current.emit("run.error", requestId, { message: "Restarted" }, "1");
    expect(screen.getByRole("alert")).toHaveTextContent("Restarted");
    await act(async () => {});
  });

  it("does not replace a newer event with a delayed status response", async () => {
    await begin();
    let finish: (value: unknown) => void = () => {};
    fetchMock.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    act(() => MockEventSource.current.onopen?.());
    MockEventSource.current.emit("run.completed", requestId, { decision: "refuse", outcome: "refuse" });
    await act(async () => finish(response({ run_id: requestId, status: "accepted", tx: null })));
    expect(screen.getByRole("button", { name: "Run" })).toBeEnabled();
  });

  it("keeps a lost POST response from enabling a duplicate payment", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/health") return response({});
      if (url === "/intents") requestId = JSON.parse(init!.body as string).run_id;
      throw new TypeError("Network disconnected");
    });
    await begin();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/unknown|could not confirm/i));
    expect(screen.getByRole("button", { name: /Check status before rerunning/i })).toBeDisabled();
    MockEventSource.current.emit("run.completed", requestId, { decision: "refuse", outcome: "refuse" });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run" })).toBeEnabled();
  });

  it("does not offer a receipt after a run failed before commitment", async () => {
    await begin();
    MockEventSource.current.emit("run.error", requestId, { message: "Quote unavailable" });
    expect(screen.queryByRole("link", { name: /Download run receipt/ })).not.toBeInTheDocument();
  });

  it("rejects an invalid successful approval response", async () => {
    await begin("C");
    MockEventSource.current.emit("policy.escalated", requestId, { escalation_id: "esc-1", reason: "Over limit", notional_usd: 500, intent: { from: "source", to: "destination", amount: 100, asset: "XRP", rationale: "rebalance" } });
    MockEventSource.current.emit("run.completed", requestId, { decision: "escalate" });
    fetchMock.mockResolvedValue(response({}));
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/unexpected approval response/i));
    expect(screen.getByText("pending", { exact: true })).toBeInTheDocument();
  });

  it.each(["open", "reset"])("reconciles a terminal run after stream %s", async (trigger) => {
    await begin();
    fetchMock.mockResolvedValue(response({ run_id: requestId, status: "error", tx: null }));
    if (trigger === "open") act(() => MockEventSource.current.onopen?.());
    else MockEventSource.current.emit("stream.reset", "", { reason: "restart" });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`/runs/${requestId}`));
    await waitFor(() => expect(screen.getByRole("button", { name: "Run" })).toBeEnabled());
    expect(screen.getByRole("alert")).toHaveTextContent(/failed|interrupted/i);
  });

  it("maps an SSE event received before the intent response", async () => {
    let finish: ((value: unknown) => void) | undefined;
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/health") return response({});
      requestId = JSON.parse(init!.body as string).run_id;
      return new Promise(resolve => { finish = resolve; });
    });
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    expect(requestId).toMatch(/^[a-f0-9]{32}$/);
    MockEventSource.current.emit("run.error", requestId, { message: "Provider unavailable" });
    expect(screen.getByRole("alert")).toHaveTextContent("Provider unavailable");
    expect(screen.getByRole("button", { name: "Run" })).toBeEnabled();
    await act(async () => finish?.(response({ run_id: requestId, status: "accepted" })));
  });

  it("keeps refusal running until the backend completes", async () => {
    await begin("B");
    MockEventSource.current.emit("policy.refused", requestId, { reason: "Policy limit" });
    expect(screen.getByRole("button", { name: /Running/ })).toBeDisabled();
    MockEventSource.current.emit("run.completed", requestId, { decision: "refuse" });
    expect(screen.getByRole("button", { name: "Run" })).toBeEnabled();
  });

  it.each(["Approve", "Reject"])("shows an HTTP failure for %s and preserves pending approval", async (label) => {
    await begin("C");
    MockEventSource.current.emit("policy.escalated", requestId, { escalation_id: "esc-1", reason: "Over limit", notional_usd: 500, intent: { from: "source", to: "destination", amount: 100, asset: "XRP", rationale: "rebalance" } });
    MockEventSource.current.emit("run.completed", requestId, { decision: "escalate" });
    fireEvent.click(screen.getByRole("button", { name: label }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Approval service unavailable"));
    expect(screen.getByText("pending", { exact: true })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Approval pending/ })).toBeDisabled();
  });

  it("shows stream reconnection and recovery", () => {
    render(<App />);
    act(() => MockEventSource.current.onerror?.());
    expect(screen.getByRole("status")).toHaveTextContent(/reconnecting/i);
    act(() => MockEventSource.current.onopen?.());
    expect(screen.getByRole("status")).toHaveTextContent(/connected/i);
  });
});
