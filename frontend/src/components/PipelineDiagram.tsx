import { motion } from "framer-motion";
import type { RunState } from "../state";

type NodeState = "idle" | "active" | "pass" | "fail";

interface Node {
  key: string;
  label: string;
  sublabel: string;
  state: NodeState;
  detail?: string;
}

function derivePipeline(state: RunState): Node[] {
  const hasMessage = !!state.userMessage;
  const thinking = state.thinking;
  const hasIntent = !!state.intent;
  const compromised = hasIntent && !!state.refused;
  const rulesStarted = state.rules.length > 0;
  const rulesDone = state.merkleRoot != null;
  const refused = !!state.refused;
  const escalate = !!state.escalation && state.escalationStatus !== "approved";
  const ledgerPhase = state.ledger.phase;

  const user: Node = {
    key: "user",
    label: "Operator",
    sublabel: "intent",
    state: hasMessage ? (hasIntent ? "pass" : "active") : "idle",
    detail: hasMessage ? "message dispatched" : "awaiting",
  };

  let agentState: NodeState = "idle";
  let agentDetail = "standby";
  if (thinking) {
    agentState = "active";
    agentDetail = "LLM thinking…";
  } else if (compromised) {
    agentState = "fail";
    agentDetail = "compromised output";
  } else if (hasIntent) {
    agentState = "pass";
    agentDetail = "intent emitted";
  }
  const agent: Node = {
    key: "agent",
    label: "Agent",
    sublabel: "key_a",
    state: agentState,
    detail: agentDetail,
  };

  let policyState: NodeState = "idle";
  let policyDetail = "standby";
  if (refused) {
    policyState = "fail";
    policyDetail = "refused to sign";
  } else if (escalate) {
    policyState = "active";
    policyDetail = "escalated to human";
  } else if (rulesDone) {
    policyState = "pass";
    policyDetail = "all rules passed";
  } else if (rulesStarted) {
    policyState = "active";
    policyDetail = `evaluating (${state.rules.length}/5)`;
  }
  const policy: Node = {
    key: "policy",
    label: "Policy",
    sublabel: "key_b",
    state: policyState,
    detail: policyDetail,
  };

  let ledgerState: NodeState = "idle";
  let ledgerDetail = "standby";
  if (ledgerPhase === "submitting") {
    ledgerState = "active";
    ledgerDetail = "submitting…";
  } else if (ledgerPhase === "settled") {
    ledgerState = "pass";
    ledgerDetail = "tesSUCCESS";
  } else if (ledgerPhase === "single_sig_failed") {
    ledgerState = "fail";
    ledgerDetail = state.ledger.result?.engine_result || "rejected";
  }
  const ledger: Node = {
    key: "ledger",
    label: "XRPL",
    sublabel: "testnet",
    state: ledgerState,
    detail: ledgerDetail,
  };

  return [user, agent, policy, ledger];
}

const nodeColors: Record<NodeState, { border: string; dot: string; text: string; glow: string }> = {
  idle:   { border: "border-border",  dot: "bg-border",  text: "text-muted",        glow: "" },
  active: { border: "border-accent",  dot: "bg-accent",  text: "text-accent",       glow: "shadow-[0_0_0_3px_rgba(217,119,87,0.12)]" },
  pass:   { border: "border-pass",    dot: "bg-pass",    text: "text-pass",         glow: "shadow-[0_0_0_3px_rgba(127,176,105,0.12)]" },
  fail:   { border: "border-fail",    dot: "bg-fail",    text: "text-fail",         glow: "shadow-[0_0_0_3px_rgba(226,109,90,0.12)]" },
};

function Connector({ from, to }: { from: NodeState; to: NodeState }) {
  // Arrow "flows" only while data is transiting: one side active, the other
  // not yet terminal. Once both sides are terminal (pass/fail) or both idle,
  // it's a static line.
  const flowing = from === "active" || to === "active";
  const color =
    from === "fail" || to === "fail"
      ? "stroke-fail"
      : from === "pass" && to === "pass"
      ? "stroke-pass"
      : flowing
      ? "stroke-accent"
      : "stroke-border";
  return (
    <div className="flex-1 mx-2 min-w-[40px]">
      <svg
        viewBox="0 0 100 20"
        preserveAspectRatio="none"
        className="w-full h-5 overflow-visible"
      >
        <line x1="0" y1="10" x2="100" y2="10" className={`${color} opacity-40`} strokeWidth="2" strokeLinecap="round" />
        {flowing && (
          <motion.line
            x1="0"
            y1="10"
            x2="100"
            y2="10"
            className={color}
            strokeWidth="2"
            strokeLinecap="round"
            strokeDasharray="4 6"
            initial={{ strokeDashoffset: 100 }}
            animate={{ strokeDashoffset: 0 }}
            transition={{ repeat: Infinity, duration: 1.2, ease: "linear" }}
          />
        )}
        <polygon
          points="100,10 94,6 94,14"
          className={`fill-current ${color.replace("stroke-", "text-")}`}
        />
      </svg>
    </div>
  );
}

function NodeCard({ node }: { node: Node }) {
  const c = nodeColors[node.state];
  const pulse =
    node.state === "active"
      ? { scale: [1, 1.015, 1] }
      : { scale: 1 };
  return (
    <motion.div
      layout
      animate={pulse}
      transition={{ duration: 1.4, repeat: node.state === "active" ? Infinity : 0 }}
      className={`flex-none w-[180px] border ${c.border} ${c.glow} rounded-lg px-4 py-3 bg-bg transition-colors duration-300`}
    >
      <div className="flex items-center justify-between">
        <div>
          <div className="font-display text-base leading-none">{node.label}</div>
          <div className="font-mono text-[10px] text-muted mt-1">{node.sublabel}</div>
        </div>
        <motion.span
          className={`w-2.5 h-2.5 rounded-full ${c.dot}`}
          animate={node.state === "active" ? { opacity: [0.4, 1, 0.4] } : { opacity: 1 }}
          transition={{ duration: 1.2, repeat: node.state === "active" ? Infinity : 0 }}
        />
      </div>
      <div className={`mt-3 text-[11px] font-mono ${c.text}`}>{node.detail}</div>
    </motion.div>
  );
}

export function PipelineDiagram({ state }: { state: RunState }) {
  const nodes = derivePipeline(state);
  return (
    <div className="border border-border rounded-lg p-5 bg-bg/60">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-display text-lg leading-none">Pipeline</h2>
          <p className="text-[11px] text-muted mt-1">
            operator → agent signs (key_a) → policy engine co-signs (key_b) → XRPL settles
          </p>
        </div>
      </div>
      <div className="flex items-center">
        {nodes.map((n, i) => (
          <div key={n.key} className="flex items-center flex-1 last:flex-none min-w-0">
            <NodeCard node={n} />
            {i < nodes.length - 1 && (
              <Connector from={n.state} to={nodes[i + 1].state} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
