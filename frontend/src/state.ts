import type { Intent, RuleCheck, SignetEvent, TxInfo } from "./types";

export interface SingleSigResult {
  tx_hash: string;
  engine_result: string;
  validated: boolean;
}

export interface RunState {
  runId: string | null;
  inFlight: boolean;
  userMessage: string;
  thinking: boolean;
  intent: Intent | null;
  rawAgentOutput: string | null;
  rules: RuleCheck[];
  merkleRoot: string | null;
  stepCount: number | null;
  refused: { reason: string; failed: string[] } | null;
  escalation: {
    id: string;
    reason: string;
    intent: Intent;
    notional_usd: number;
  } | null;
  escalationStatus: "pending" | "approved" | "rejected" | null;
  agentSigned: boolean;
  policySigned: boolean;
  policyRefused: boolean;
  ledger:
    | { phase: "idle" }
    | { phase: "submitting" }
    | { phase: "settled"; tx: TxInfo }
    | { phase: "single_sig_failed"; result: SingleSigResult };
}

export const initialRunState: RunState = {
  runId: null,
  inFlight: false,
  userMessage: "",
  thinking: false,
  intent: null,
  rawAgentOutput: null,
  rules: [],
  merkleRoot: null,
  stepCount: null,
  refused: null,
  escalation: null,
  escalationStatus: null,
  agentSigned: false,
  policySigned: false,
  policyRefused: false,
  ledger: { phase: "idle" },
};

export type Action =
  | { kind: "reset" }
  | { kind: "start"; runId: string; userMessage: string }
  | { kind: "finish" }
  | { kind: "event"; ev: SignetEvent }
  | { kind: "escalation_resolved"; status: "approved" | "rejected"; tx?: TxInfo | null };

export function reducer(state: RunState, action: Action): RunState {
  switch (action.kind) {
    case "reset":
      return { ...initialRunState };
    case "start":
      return {
        ...initialRunState,
        runId: action.runId,
        userMessage: action.userMessage,
        inFlight: true,
      };
    case "finish":
      return { ...state, inFlight: false };
    case "escalation_resolved":
      return {
        ...state,
        escalationStatus: action.status,
        ledger:
          action.status === "approved" && action.tx
            ? { phase: "settled", tx: action.tx }
            : state.ledger,
      };
    case "event": {
      const { ev } = action;
      // Map-level filter in App.tsx already routes by run_id; don't double-filter
      // here — it introduces a race between the map entry being set and the
      // next setStates call.
      const d = ev.data || {};
      switch (ev.type) {
        case "run.started":
          return { ...state, userMessage: d.user_message ?? state.userMessage };
        case "agent.thinking":
          return { ...state, thinking: true };
        case "agent.intent":
          return {
            ...state,
            thinking: false,
            intent: d.intent,
            rawAgentOutput: JSON.stringify(d.raw_tool_args ?? d.intent, null, 2),
          };
        case "rule.check":
          return {
            ...state,
            rules: [
              ...state.rules,
              {
                name: d.name,
                status: d.status,
                detail: d.detail,
                passed: !!d.passed,
              },
            ],
          };
        case "reasoning.commit":
          return {
            ...state,
            merkleRoot: d.merkle_root,
            stepCount: d.step_count,
          };
        case "policy.refused":
          return {
            ...state,
            refused: { reason: d.reason, failed: d.failed || [] },
            policyRefused: true,
          };
        case "policy.escalated":
          return {
            ...state,
            escalation: {
              id: d.escalation_id,
              reason: d.reason,
              intent: d.intent,
              notional_usd: d.notional_usd,
            },
            escalationStatus: "pending",
          };
        case "ledger.single_sig_attempt":
          return { ...state, ledger: { phase: "submitting" } };
        case "ledger.single_sig_result":
          return {
            ...state,
            ledger: {
              phase: "single_sig_failed",
              result: {
                tx_hash: d.tx_hash,
                engine_result: d.engine_result,
                validated: !!d.validated,
              },
            },
          };
        case "signature.agent":
          return { ...state, agentSigned: true };
        case "signature.policy":
          return { ...state, policySigned: true };
        case "ledger.submitting":
          return { ...state, ledger: { phase: "submitting" } };
        case "ledger.settled":
          return {
            ...state,
            ledger: {
              phase: "settled",
              tx: {
                tx_hash: d.tx_hash,
                explorer_url: d.explorer_url,
                engine_result: d.engine_result,
                validated: !!d.validated,
                memo_hex: d.memo_hex,
              },
            },
          };
        case "escalation.approved":
          return { ...state, escalationStatus: "approved" };
        case "escalation.rejected":
          return { ...state, escalationStatus: "rejected" };
        default:
          return state;
      }
    }
    default:
      return state;
  }
}
