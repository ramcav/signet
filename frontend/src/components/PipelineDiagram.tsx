import { motion, useReducedMotion } from "framer-motion";
import type { RunState } from "../state";

type NodeState = "idle" | "active" | "pass" | "fail";
interface PipelineNode { key: string; label: string; sublabel: string; state: NodeState; detail: string }

function derivePipeline(state: RunState): PipelineNode[] {
  const hasMessage = !!state.userMessage;
  const hasIntent = !!state.intent;
  const user: PipelineNode = {
    key: "user", label: "Operator", sublabel: "intent", state: hasMessage ? hasIntent ? "pass" : "active" : "idle", detail: hasMessage ? "message dispatched" : "awaiting",
  };
  const agent: PipelineNode = {
    key: "agent", label: "Agent", sublabel: "key_a",
    state: state.thinking ? "active" : hasIntent ? "pass" : state.error ? "fail" : "idle",
    detail: state.thinking ? "preparing intent..." : hasIntent ? "intent emitted" : state.error ? "run interrupted" : "standby",
  };
  const policy: PipelineNode = { key: "policy", label: "Policy", sublabel: "key_b", state: "idle", detail: "standby" };
  if (state.refused || state.escalationStatus === "rejected") {
    policy.state = "fail";
    policy.detail = state.escalationStatus === "rejected" ? "operator rejected" : "refused to sign";
  } else if (state.escalationStatus === "pending") {
    policy.state = "active";
    policy.detail = "awaiting operator approval";
  } else if (state.escalationStatus === "approved") {
    policy.state = "pass";
    policy.detail = "operator approved";
  } else if (state.escalationStatus === "expired") {
    policy.state = "fail";
    policy.detail = "approval request expired";
  } else if (state.rules.length > 0 && state.rules.every((rule) => rule.passed) && state.merkleRoot) {
    policy.state = "pass";
    policy.detail = "policy checks passed";
  } else if (state.rules.length > 0) {
    policy.state = "active";
    policy.detail = `evaluating (${state.rules.length} checked)`;
  }
  const ledger: PipelineNode = { key: "ledger", label: "XRPL", sublabel: "testnet", state: "idle", detail: "standby" };
  const current = state.ledger;
  const result = current.phase === "single_sig_failed" ? current.result : "tx" in current ? current.tx : null;
  if (result) {
    const success = result.outcome === "success" && result.validated && result.engine_result === "tesSUCCESS";
    ledger.state = success ? "pass" : result.outcome === "unknown" || result.outcome === "success" ? "active" : "fail";
    ledger.detail = !success && (result.outcome === "unknown" || result.outcome === "success")
      ? `Outcome unknown${result.engine_result ? ` · ${result.engine_result}` : ""}`
      : result.engine_result || "attempt failed";
  } else if (current.phase === "submitting") {
    ledger.state = "active";
    ledger.detail = "submitting...";
  } else if (state.refused || state.escalationStatus === "rejected") ledger.detail = "not submitted";
  return [user, agent, policy, ledger];
}

const nodeColors: Record<NodeState, { border: string; dot: string; text: string }> = {
  idle: { border: "border-border", dot: "bg-border", text: "text-muted" },
  active: { border: "border-accent", dot: "bg-accent", text: "text-accent" },
  pass: { border: "border-pass", dot: "bg-pass", text: "text-pass" },
  fail: { border: "border-fail", dot: "bg-fail", text: "text-fail" },
};

export function PipelineDiagram({ state }: { state: RunState }) {
  const nodes = derivePipeline(state);
  const reducedMotion = useReducedMotion();
  return (
    <section className="min-w-0 border border-border rounded-lg p-4 sm:p-5 bg-bg/60" aria-labelledby="pipeline-title">
      <div className="mb-4">
        <h2 id="pipeline-title" className="font-display text-lg leading-none">Pipeline</h2>
        <p className="text-[11px] text-muted mt-1">Operator → agent intent → policy evaluation → XRPL result</p>
      </div>
      <ol className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        {nodes.map((node, index) => {
          const colors = nodeColors[node.state];
          const animate = node.state === "active" && !reducedMotion;
          return (
            <li key={node.key} className={`min-w-0 border ${colors.border} rounded-lg px-4 py-3 bg-bg`}>
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="font-display text-base leading-none"><span className="text-muted text-xs mr-2">{index + 1}</span>{node.label}</div>
                  <div className="font-mono text-[10px] text-muted mt-1">{node.sublabel}</div>
                </div>
                <motion.span aria-hidden="true" className={`shrink-0 w-2.5 h-2.5 rounded-full ${colors.dot}`} animate={animate ? { opacity: [0.4, 1, 0.4] } : { opacity: 1 }} transition={{ duration: reducedMotion ? 0 : 1.2, repeat: animate ? Infinity : 0 }} />
              </div>
              <div className={`mt-3 text-[11px] font-mono break-words ${colors.text}`}>{node.detail}</div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
