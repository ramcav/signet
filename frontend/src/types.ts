export type Decision = "allow" | "refuse" | "escalate";

export interface Intent {
  id: string;
  from: string;
  to: string;
  amount: number | string;
  asset: string;
  rationale: string;
}

export interface TxInfo {
  outcome: "success" | "rejected" | "failed" | "unknown";
  tx_hash: string;
  explorer_url: string;
  engine_result: string;
  validated: boolean;
  memo_hex: string;
}

export interface IntentResponse {
  run_id: string;
  status: "accepted";
}

export interface RunSnapshot {
  run_id: string;
  status: "accepted" | "allow" | "refuse" | "escalate" | "success" | "rejected" | "failed" | "unknown" | "error";
  tx: TxInfo | null;
  escalation_id?: string | null;
  receipt?: {
    root: string;
    payload: {
      intent: { id: string; from_account: string; to_account: string; amount: string; asset: string; rationale: string };
      evaluation: { decision: Decision; reason: string; notional_usd: string; checks: Omit<RuleCheck, "passed">[] };
      trace: { steps: unknown[] };
      approval?: { action: string } | null;
    };
  } | null;
}

export interface RuleCheck {
  name: string;
  status: "pass" | "fail";
  detail: string;
  passed: boolean;
}

export interface SignetEvent {
  type: string;
  run_id: string;
  data: any;
  ts: number;
}

export interface Health {
  master: string;
  agent: string;
  policy: string;
  allowlist: string[];
  xrp_usd: number | null;
  quote?: { source?: string; fetched_at?: string; [key: string]: unknown } | null;
  quote_error?: string;
  master_balance_xrp: number;
}

export type ScenarioKey = "A" | "B" | "C";
