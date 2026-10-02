import type { Intent, RuleCheck, RunSnapshot, SignetEvent, TxInfo } from "./types";

export interface SingleSigResult {
  outcome: TxInfo["outcome"];
  tx_hash: string;
  engine_result: string;
  validated: boolean;
}

export interface RunState {
  runId: string | null;
  inFlight: boolean;
  needsReconciliation: boolean;
  requestUnconfirmed: boolean;
  userMessage: string;
  thinking: boolean;
  error: string | null;
  actionError: string | null;
  decision: string | null;
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
  escalationStatus: "pending" | "approved" | "rejected" | "expired" | null;
  agentSigned: boolean;
  policySigned: boolean;
  policyRefused: boolean;
  ledger:
    | { phase: "idle" }
    | { phase: "submitting" }
    | { phase: "settled"; tx: TxInfo }
    | { phase: "failed" | "unknown"; tx: TxInfo }
    | { phase: "single_sig_failed"; result: SingleSigResult };
}

export const initialRunState: RunState = {
  runId: null,
  inFlight: false,
  needsReconciliation: false,
  requestUnconfirmed: false,
  userMessage: "",
  thinking: false,
  error: null,
  actionError: null,
  decision: null,
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

const unknownTx: TxInfo = { outcome: "unknown", tx_hash: "", engine_result: "unconfirmed", validated: false, memo_hex: "", explorer_url: "" };

function ledgerResult(tx: TxInfo): RunState["ledger"] {
  return { phase: tx.outcome === "success" && tx.validated && tx.engine_result === "tesSUCCESS"
    ? "settled" : tx.outcome === "unknown" ? "unknown" : "failed", tx };
}

export type Action =
  | { kind: "reset" }
  | { kind: "start"; runId: string; userMessage: string }
  | { kind: "event"; ev: SignetEvent }
  | { kind: "snapshot"; snapshot: RunSnapshot }
  | { kind: "transport_unknown"; runId: string }
  | { kind: "request_accepted"; runId: string }
  | { kind: "action_error"; runId: string; message: string | null }
  | { kind: "escalation_resolved"; runId: string; status: "approved" | "rejected"; tx?: TxInfo | null };

export function reducer(state: RunState, action: Action): RunState {
  switch (action.kind) {
    case "reset":
      if (state.escalationStatus === "pending" || state.needsReconciliation) return state;
      return { ...initialRunState };
    case "start":
      if (state.escalationStatus === "pending" || state.needsReconciliation) return state;
      return {
        ...initialRunState,
        runId: action.runId,
        userMessage: action.userMessage,
        inFlight: true,
      };
    case "transport_unknown":
      if (action.runId !== state.runId || state.decision) return state;
      return { ...state, inFlight: false, thinking: false, needsReconciliation: true, requestUnconfirmed: true,
        error: "Could not confirm the request outcome. Check run status before submitting another payment." };
    case "request_accepted":
      if (action.runId !== state.runId || state.decision) return state;
      return { ...state, requestUnconfirmed: false, needsReconciliation: false, inFlight: true, error: null };
    case "snapshot": {
      const snapshot = action.snapshot;
      if (snapshot.run_id !== state.runId) return state;
      const payload = snapshot.receipt?.payload;
      const intent = payload ? { id: payload.intent.id, from: payload.intent.from_account,
        to: payload.intent.to_account, amount: payload.intent.amount, asset: payload.intent.asset,
        rationale: payload.intent.rationale } : state.intent;
      const pending = snapshot.status === "escalate";
      return {
        ...state,
        intent,
        inFlight: snapshot.status === "accepted",
        thinking: snapshot.status === "accepted" && state.thinking,
        needsReconciliation: snapshot.status === "unknown",
        requestUnconfirmed: false,
        decision: snapshot.status === "accepted" ? null : payload?.evaluation.decision ?? snapshot.status,
        error: snapshot.status === "error" ? "The run failed or was interrupted. Pending approval has expired."
          : snapshot.status === "unknown" ? "The payment outcome is unknown. Check the ledger before submitting again." : null,
        actionError: pending || snapshot.status === "accepted" ? state.actionError : null,
        merkleRoot: snapshot.receipt?.root ?? state.merkleRoot,
        stepCount: payload?.trace.steps.length ?? state.stepCount,
        rules: payload?.evaluation.checks.map(check => ({ ...check, passed: check.status === "pass" })) ?? state.rules,
        refused: payload?.evaluation.decision === "refuse" ? { reason: payload.evaluation.reason,
          failed: payload.evaluation.checks.filter(check => check.status === "fail").map(check => check.name) } : state.refused,
        policyRefused: payload?.evaluation.decision === "refuse" || state.policyRefused,
        escalation: pending && snapshot.escalation_id && intent && payload ? {
          id: snapshot.escalation_id, intent, reason: payload.evaluation.reason,
          notional_usd: Number(payload.evaluation.notional_usd),
        } : state.escalation,
        escalationStatus: pending ? "pending" : payload?.approval?.action === "approve" ? "approved"
          : payload?.approval?.action === "reject" ? "rejected"
          : state.escalationStatus === "pending" ? "expired" : state.escalationStatus,
        ledger: snapshot.tx ? ledgerResult(snapshot.tx) : snapshot.status === "unknown" ? ledgerResult(unknownTx) : state.ledger,
      };
    }
    case "action_error":
      return action.runId === state.runId ? { ...state, actionError: action.message } : state;
    case "escalation_resolved":
      if (action.runId !== state.runId) return state;
      return {
        ...state,
        actionError: null,
        inFlight: false,
        thinking: false,
        needsReconciliation: action.tx?.outcome === "unknown",
        escalationStatus: action.status,
        ledger:
          action.status === "approved" && action.tx
            ? { phase: action.tx.outcome === "success" && action.tx.validated && action.tx.engine_result === "tesSUCCESS" ? "settled" : action.tx.outcome === "unknown" ? "unknown" : "failed", tx: action.tx }
            : state.ledger,
      };
    case "event": {
      const { ev } = action;
      if (ev.run_id !== state.runId) return state;
      if (state.requestUnconfirmed) state = { ...state, requestUnconfirmed: false, needsReconciliation: false, error: null, inFlight: true };
      const d = ev.data || {};
      switch (ev.type) {
        case "run.error":
          return {
            ...state, inFlight: false, thinking: false, error: d.message || "Run failed", decision: "error",
            needsReconciliation: !!d.outcome_unknown || state.ledger.phase === "submitting",
            escalationStatus: state.escalationStatus === "pending" ? "expired" : state.escalationStatus,
            ledger: state.ledger.phase === "submitting" ? { phase: "unknown", tx: { outcome: "unknown", tx_hash: "", engine_result: "unconfirmed", validated: false, memo_hex: "", explorer_url: "" } } : state.ledger,
          };
        case "run.completed":
          return { ...state, inFlight: false, thinking: false, decision: d.decision, error: null,
            needsReconciliation: d.outcome === "unknown" || state.ledger.phase === "unknown"
              || (state.ledger.phase === "single_sig_failed" && state.ledger.result.outcome === "unknown") };
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
                outcome: d.outcome ?? "unknown",
              },
            },
          };
        case "signature.agent":
          return { ...state, agentSigned: true };
        case "signature.policy":
          return { ...state, policySigned: true };
        case "ledger.submitting":
          return { ...state, inFlight: true, ledger: { phase: "submitting" } };
        case "ledger.settled":
        case "ledger.failed":
        case "ledger.unknown":
          return {
            ...state,
            ledger: {
              phase: d.outcome === "success" && d.validated && d.engine_result === "tesSUCCESS" ? "settled" : d.outcome === "unknown" || ev.type === "ledger.unknown" ? "unknown" : "failed",
              tx: {
                outcome: d.outcome ?? "unknown",
                tx_hash: d.tx_hash,
                explorer_url: d.explorer_url,
                engine_result: d.engine_result,
                validated: !!d.validated,
                memo_hex: d.memo_hex,
              },
            },
          };
        case "escalation.approved":
          return { ...state, inFlight: true, escalationStatus: "approved", actionError: null };
        case "escalation.rejected":
          return { ...state, escalationStatus: "rejected", actionError: null };
        default:
          return state;
      }
    }
    default:
      return state;
  }
}
