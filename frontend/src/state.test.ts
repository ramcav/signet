import { describe, expect, it } from "vitest";
import { initialRunState, reducer } from "./state";
import type { SignetEvent } from "./types";

const started = () => reducer(initialRunState, { kind: "start", runId: "new-run", userMessage: "Send XRP" });
const event = (type: string, data = {}, run_id = "new-run"): SignetEvent => ({ type, data, run_id, ts: 1 });

describe("run lifecycle", () => {
  it("keeps unknown outcomes blocked even after completion", () => {
    const unknown = reducer(started(), { kind: "event", ev: event("run.error", { outcome_unknown: true }) });
    expect(unknown.needsReconciliation).toBe(true);
    expect(reducer(unknown, { kind: "start", runId: "duplicate", userMessage: "same" })).toBe(unknown);
  });

  it("restores a pending approval from a run snapshot", () => {
    const result = reducer(started(), { kind: "snapshot", snapshot: {
      run_id: "new-run", status: "escalate", tx: null, escalation_id: "restored-approval",
      receipt: { root: "abc", payload: {
        intent: { id: "intent", from_account: "source", to_account: "dest", amount: "5", asset: "XRP", rationale: "rebalance" },
        evaluation: { decision: "escalate", reason: "Over limit", notional_usd: "1000", checks: [] },
        trace: { steps: [] },
      } },
    } });
    expect(result).toMatchObject({ inFlight: false, merkleRoot: "abc", escalationStatus: "pending", escalation: { id: "restored-approval" } });
  });

  it("ends loading and thinking on a run error", () => {
    const thinking = reducer(started(), { kind: "event", ev: event("agent.thinking") });
    const result = reducer(thinking, { kind: "event", ev: event("run.error", { message: "Provider unavailable" }) });
    expect(result).toMatchObject({ inFlight: false, thinking: false, error: "Provider unavailable" });
  });

  it("ignores late events from an earlier run", () => {
    const state = started();
    expect(reducer(state, { kind: "event", ev: event("signature.policy", {}, "old-run") })).toBe(state);
  });

  it("waits for run.completed after refusal and a single signature result", () => {
    const refusal = reducer(started(), { kind: "event", ev: event("policy.refused", { reason: "Policy limit" }) });
    const proof = reducer(refusal, { kind: "event", ev: event("ledger.single_sig_result", { engine_result: "tefBAD_QUORUM", outcome: "rejected" }) });
    expect(proof.inFlight).toBe(true);
    const result = reducer(proof, { kind: "event", ev: event("run.completed", { decision: "refuse" }) });
    expect(result).toMatchObject({ inFlight: false, thinking: false, decision: "refuse" });
  });

  it("preserves a pending escalation against a new run", () => {
    const pending = reducer(started(), { kind: "event", ev: event("policy.escalated", { escalation_id: "esc-1" }) });
    expect(reducer(pending, { kind: "start", runId: "replacement", userMessage: "new" })).toBe(pending);
    expect(reducer(pending, { kind: "reset" })).toBe(pending);
  });

  it("records an unknown ledger result without claiming rejection or success", () => {
    const result = reducer(started(), { kind: "event", ev: event("ledger.unknown", { outcome: "unknown", engine_result: "timeout", tx_hash: "hash" }) });
    expect(result.ledger).toMatchObject({ phase: "unknown", tx: { outcome: "unknown", engine_result: "timeout" } });
  });

  it("does not treat a validated failed transaction as settled", () => {
    const result = reducer(started(), { kind: "event", ev: event("ledger.failed", { outcome: "failed", engine_result: "tecPATH_DRY", validated: true }) });
    expect(result.ledger).toMatchObject({ phase: "failed", tx: { validated: true, engine_result: "tecPATH_DRY" } });
  });
});
