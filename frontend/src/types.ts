export type Decision = "allow" | "refuse" | "escalate";

export interface Intent {
  id: string;
  from: string;
  to: string;
  amount: number;
  asset: string;
  rationale: string;
}

export interface TxInfo {
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
  xrp_usd: number;
  master_balance_xrp: number;
}

export type ScenarioKey = "A" | "B" | "C";
