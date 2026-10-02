import { useEffect, useRef } from "react";
import { motion, useReducedMotion } from "framer-motion";
import type { RunState } from "../state";
import type { ScenarioKey } from "../types";
import { LedgerPanel } from "./LedgerPanel";

interface Props {
  active: boolean;
  scenario: ScenarioKey;
  state: RunState;
  onClose: () => void;
  onApprove: () => void;
  onReject: () => void;
  escalationBusy: boolean;
}

function narrator(state: RunState): string {
  const ledger = state.ledger;
  const result = ledger.phase === "single_sig_failed" ? ledger.result : "tx" in ledger ? ledger.tx : null;
  if (result) {
    if (result.outcome === "success" && result.validated && result.engine_result === "tesSUCCESS") return "Payment settled on XRPL testnet.";
    if (result.outcome === "unknown" || result.outcome === "success") return "Submission outcome unknown. Check the ledger before retrying.";
    if (result.outcome === "rejected") return "XRPL rejected the transaction.";
    return "Payment attempt failed.";
  }
  if (ledger.phase === "submitting") return "Submitting to XRPL testnet...";
  if (state.error) return "The run could not be completed.";
  if (state.refused) return "Policy engine refused to co-sign.";
  if (state.escalationStatus === "pending") return "Operator approval required.";
  if (state.escalationStatus === "rejected") return "The operator rejected this payment.";
  if (state.escalationStatus === "expired") return "This approval request is no longer available.";
  if (state.escalationStatus === "approved") return "Operator approval recorded.";
  if (state.thinking) return "The agent is preparing an intent...";
  if (state.merkleRoot) return "Payment receipt committed.";
  if (state.rules.length > 0) return `Policy engine evaluating rules (${state.rules.length} checked)...`;
  if (state.intent) return "Agent proposes an intent. Routing to the policy engine.";
  return state.userMessage ? "Agent receives the operator's message..." : "Ready for an operator message.";
}

export function CinematicOverlay({ active, scenario, state, onClose, onApprove, onReject, escalationBusy }: Props) {
  const reducedMotion = useReducedMotion();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!active) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
      }
      if (event.key !== "Tab") return;
      const targets = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
      ) ?? []).filter((element) => !element.hidden && element.getAttribute("aria-hidden") !== "true");
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (!first || !last) {
        event.preventDefault();
        dialogRef.current?.focus();
      } else if (event.shiftKey && (document.activeElement === first || !dialogRef.current?.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialogRef.current?.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    }
    function containFocus(event: FocusEvent) {
      if (event.target instanceof Node && !dialogRef.current?.contains(event.target)) closeRef.current?.focus();
    }
    document.addEventListener("keydown", handleKey);
    document.addEventListener("focusin", containFocus);
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.removeEventListener("focusin", containFocus);
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [active]);

  if (!active) return null;
  const escalation = state.escalationStatus === "pending" ? state.escalation : null;
  const showResult = state.ledger.phase !== "idle" || !!state.refused;

  return (
    <motion.div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="cinematic-title" tabIndex={-1}
      initial={reducedMotion ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: reducedMotion ? 0 : 0.2 }}
      className="fixed inset-0 z-50 bg-bg/95 backdrop-blur-sm overflow-auto">
      <div className="max-w-4xl mx-auto px-4 sm:px-8 py-6 sm:py-10">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-8">
          <div id="cinematic-title" className="font-mono text-[11px] uppercase tracking-widest text-accent">Cinematic · Scenario {scenario}</div>
          <button ref={closeRef} onClick={onClose} className="font-mono text-xs text-muted hover:text-fg border border-border rounded px-3 py-2">Exit cinematic</button>
        </div>
        <h2 className="font-display text-2xl sm:text-3xl lg:text-4xl leading-tight mb-8 text-fg" aria-live="polite">{narrator(state)}</h2>
        {state.error && <p role="alert" className="text-fail mb-4 break-words">{state.error}</p>}
        {state.userMessage && (
          <section className="border border-border rounded-lg p-5 bg-[#141311] mb-4">
            <h3 className="text-[10px] font-mono text-muted uppercase tracking-widest mb-3">Operator message</h3>
            <div className="font-mono text-[13px] leading-relaxed whitespace-pre-wrap break-words text-fg/90">{state.userMessage}</div>
          </section>
        )}
        {state.intent && (
          <section className="border border-border rounded-lg p-5 bg-[#141311] mb-4">
            <h3 className="text-[10px] font-mono text-muted uppercase tracking-widest mb-3">Agent intent</h3>
            <p className="font-mono text-sm">Attempted amount: <span className="text-accent">{state.intent.amount.toLocaleString()} {state.intent.asset}</span></p>
            <p className="font-mono text-xs text-muted mt-2 break-all">Destination: {state.intent.to}</p>
            <p className="text-xs text-muted mt-2 italic break-words">{state.intent.rationale}</p>
          </section>
        )}
        {state.rules.length > 0 && (
          <section className="border border-border rounded-lg p-5 bg-[#141311] mb-4">
            <h3 className="text-[10px] font-mono text-muted uppercase tracking-widest mb-3">Policy rules</h3>
            <ul className="space-y-3">
              {state.rules.map((rule, index) => (
                <li key={rule.name + index} className="font-mono text-sm break-words">
                  <span className={rule.passed ? "text-pass" : "text-fail"}>{rule.passed ? "Passed" : "Failed"}: </span><span>{rule.name}</span>
                  <p className="text-muted text-xs mt-1">{rule.detail}</p>
                </li>
              ))}
            </ul>
          </section>
        )}
        {state.refused && <p className="mb-4 text-sm text-fail break-words">Policy refusal: {state.refused.reason}</p>}
        {escalation && (
          <section className="my-6 border-2 border-accent bg-accent/5 rounded-lg p-5">
            <h3 className="text-[11px] font-mono text-accent uppercase tracking-widest mb-2">Operator approval required</h3>
            <p className="font-display text-3xl mb-1">{escalation.intent.amount.toLocaleString()} {escalation.intent.asset}</p>
            <p className="text-sm text-muted mb-4 break-words">Approximately ${Number(escalation.notional_usd).toLocaleString()} · {escalation.reason}</p>
            {state.actionError && <p role="alert" className="mb-4 text-sm text-fail">{state.actionError}</p>}
            <div className="flex flex-wrap gap-3">
              <button disabled={escalationBusy} onClick={onApprove} className="px-5 py-2 bg-accent text-bg rounded font-mono text-sm uppercase tracking-wider hover:bg-accent/90 disabled:opacity-50">Approve</button>
              <button disabled={escalationBusy} onClick={onReject} className="px-5 py-2 border border-border text-fg rounded font-mono text-sm uppercase tracking-wider hover:border-fail hover:text-fail disabled:opacity-50">Reject</button>
            </div>
          </section>
        )}
        {showResult && <LedgerPanel state={state} />}
      </div>
    </motion.div>
  );
}
