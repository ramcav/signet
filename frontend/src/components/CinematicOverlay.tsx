import { AnimatePresence, motion } from "framer-motion";
import type { RunState } from "../state";
import { truncMid } from "../util";
import type { ScenarioKey } from "../types";

interface Props {
  active: boolean;
  scenario: ScenarioKey;
  state: RunState;
  onClose: () => void;
  onApprove: () => void;
  onReject: () => void;
  escalationBusy: boolean;
}

function narrator(scenario: ScenarioKey, state: RunState): string | null {
  if (!state.userMessage) return null;
  if (state.thinking) return "The LLM is thinking…";
  if (state.refused) {
    if (scenario === "B") return "Policy engine refuses to co-sign — jailbreak detected.";
    return "Policy engine refused to co-sign.";
  }
  if (state.ledger.phase === "single_sig_failed")
    return "XRPL rejects the single-signature attempt. Quorum not met.";
  if (state.ledger.phase === "settled") return "Settled on XRPL. Receipt is on-chain.";
  if (state.ledger.phase === "submitting") return "Both keys signed. Submitting to XRPL testnet…";
  if (state.escalationStatus === "pending")
    return "Amount over autonomous threshold. Escalating to human.";
  if (state.escalationStatus === "approved") return "Human approved. Co-signing now…";
  if (state.merkleRoot) return "Merkle commit locked. Signing with key_a and key_b.";
  if (state.rules.length > 0)
    return `Policy engine evaluating rules (${state.rules.length}/5)…`;
  if (state.intent) return "Agent proposes an intent. Routing to policy engine.";
  return "Agent receives the operator's message…";
}

const ATTACKER_ADDR = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh";

function HeistMessage({ msg }: { msg: string }) {
  const parts = msg.split("--- SYSTEM OVERRIDE");
  const benign = parts[0];
  const inject = parts[1] ? "--- SYSTEM OVERRIDE" + parts[1] : null;
  return (
    <div className="font-mono text-[13px] leading-relaxed whitespace-pre-wrap">
      <span className="text-fg/80">{benign}</span>
      {inject && (
        <motion.span
          initial={{ backgroundColor: "rgba(226,109,90,0)" }}
          animate={{ backgroundColor: "rgba(226,109,90,0.18)" }}
          transition={{ delay: 0.4, duration: 0.6 }}
          className="text-fail block mt-2 border-l-2 border-fail pl-3"
        >
          {inject.replace(ATTACKER_ADDR, "")}
          <span className="bg-fail/40 text-fg px-1 rounded">{ATTACKER_ADDR}</span>
        </motion.span>
      )}
    </div>
  );
}

function StampRefused() {
  return (
    <motion.div
      initial={{ scale: 2.4, opacity: 0, rotate: -8 }}
      animate={{ scale: 1, opacity: 1, rotate: -6 }}
      transition={{ type: "spring", stiffness: 220, damping: 18 }}
      className="inline-block border-4 border-fail px-8 py-4 text-fail font-display text-4xl tracking-wider uppercase"
      style={{ boxShadow: "0 0 0 1px rgba(226,109,90,0.25) inset" }}
    >
      Refused · tefBAD_QUORUM
    </motion.div>
  );
}

function SavedCounter({ amount, xrpUsd }: { amount: number; xrpUsd: number }) {
  const usd = Math.round(amount * xrpUsd);
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.4 }}
      className="mt-6 border border-pass/60 bg-pass/5 px-6 py-4 rounded-lg"
    >
      <div className="text-[11px] font-mono text-pass uppercase tracking-widest mb-1">
        Funds never moved
      </div>
      <div className="font-display text-3xl text-fg">
        {amount.toLocaleString()} XRP <span className="text-muted text-lg">≈ ${usd.toLocaleString()} saved</span>
      </div>
      <div className="mt-2 text-xs font-mono text-muted">
        attacker address <span className="text-fail">{truncMid(ATTACKER_ADDR, 8, 8)}</span> · rejected by protocol
      </div>
    </motion.div>
  );
}

function SettledHero({ state }: { state: RunState }) {
  if (state.ledger.phase !== "settled") return null;
  const tx = state.ledger.tx;
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4 }}
      className="mt-6 border border-pass/60 bg-pass/5 rounded-lg p-6"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="text-[11px] font-mono text-pass uppercase tracking-widest">
          On-chain receipt
        </div>
        <span className="text-[11px] font-mono px-2 py-1 border border-pass text-pass rounded uppercase tracking-wider">
          {tx.engine_result}
        </span>
      </div>
      <div className="mb-3">
        <div className="text-[10px] font-mono uppercase text-muted tracking-wider mb-1">
          tx_hash
        </div>
        <div className="font-mono text-sm text-fg break-all">{tx.tx_hash}</div>
      </div>
      <div className="mb-4">
        <div className="text-[10px] font-mono uppercase text-muted tracking-wider mb-1">
          memo · reasoningCommit (Merkle root)
        </div>
        <div className="font-mono text-xs text-accent break-all">{tx.memo_hex}</div>
      </div>
      <a
        href={tx.explorer_url}
        target="_blank"
        rel="noreferrer"
        className="inline-block text-sm text-accent border-b border-accent hover:text-fg hover:border-fg"
      >
        verify on XRPL testnet explorer ↗
      </a>
    </motion.div>
  );
}

function EscalationHero({
  state,
  onApprove,
  onReject,
  busy,
}: {
  state: RunState;
  onApprove: () => void;
  onReject: () => void;
  busy: boolean;
}) {
  if (!state.escalation || state.escalationStatus !== "pending") return null;
  const esc = state.escalation;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-6 border-2 border-accent bg-accent/5 rounded-lg p-6"
    >
      <div className="text-[11px] font-mono text-accent uppercase tracking-widest mb-2">
        Human approval required · AI Act Art. 14
      </div>
      <div className="font-display text-3xl mb-1">
        {esc.intent.amount.toLocaleString()} {esc.intent.asset}
      </div>
      <div className="text-sm text-muted mb-4">
        ≈ ${Math.round(esc.notional_usd).toLocaleString()} · {esc.reason}
      </div>
      <div className="text-xs font-mono text-muted mb-4">
        destination {truncMid(esc.intent.to, 8, 8)}
      </div>
      <div className="flex gap-3">
        <button
          disabled={busy}
          onClick={onApprove}
          className="px-5 py-2 bg-accent text-bg rounded font-mono text-sm uppercase tracking-wider hover:bg-accent/90 disabled:opacity-50"
        >
          Approve
        </button>
        <button
          disabled={busy}
          onClick={onReject}
          className="px-5 py-2 border border-border text-fg rounded font-mono text-sm uppercase tracking-wider hover:border-fail hover:text-fail disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </motion.div>
  );
}

export function CinematicOverlay({
  active,
  scenario,
  state,
  onClose,
  onApprove,
  onReject,
  escalationBusy,
}: Props) {
  if (!active) return null;
  const line = narrator(scenario, state);
  const showB = scenario === "B";
  const showRefused =
    showB && (state.refused || state.ledger.phase === "single_sig_failed");
  const attackerAmount = 10000;
  const xrpUsd = 0.5;

  return (
    <AnimatePresence>
      <motion.div
        key="cinematic"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 bg-bg/95 backdrop-blur-sm overflow-auto"
      >
        <div className="max-w-4xl mx-auto px-8 py-10">
          <div className="flex items-center justify-between mb-8">
            <div className="font-mono text-[11px] uppercase tracking-widest text-accent">
              Cinematic · Scenario {scenario}
            </div>
            <button
              onClick={onClose}
              className="font-mono text-xs text-muted hover:text-fg border border-border rounded px-3 py-1.5"
            >
              exit cinematic ✕
            </button>
          </div>

          <AnimatePresence mode="wait">
            {line && (
              <motion.h2
                key={line}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.35 }}
                className="font-display text-3xl lg:text-4xl leading-tight mb-8 text-fg"
              >
                {line}
              </motion.h2>
            )}
          </AnimatePresence>

          {state.userMessage && (
            <div className="border border-border rounded-lg p-5 bg-[#141311] mb-4">
              <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-3">
                Operator message
              </div>
              {showB ? (
                <HeistMessage msg={state.userMessage} />
              ) : (
                <div className="font-mono text-[13px] leading-relaxed whitespace-pre-wrap text-fg/90">
                  {state.userMessage}
                </div>
              )}
            </div>
          )}

          {state.intent && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="border border-border rounded-lg p-5 bg-[#141311] mb-4"
            >
              <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-3">
                Agent intent
              </div>
              <div className="font-mono text-sm text-fg">
                send <span className="text-accent">{state.intent.amount} {state.intent.asset}</span>
                {"  →  "}
                <span className={showB && state.intent.to === ATTACKER_ADDR ? "bg-fail/30 text-fg px-1 rounded" : "text-fg"}>
                  {truncMid(state.intent.to, 10, 8)}
                </span>
              </div>
              <div className="text-xs text-muted mt-2 italic">"{state.intent.rationale}"</div>
            </motion.div>
          )}

          {state.rules.length > 0 && (
            <div className="border border-border rounded-lg p-5 bg-[#141311] mb-4">
              <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-3">
                Policy rules
              </div>
              <div className="space-y-2">
                {state.rules.map((r, i) => (
                  <motion.div
                    key={r.name + i}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="flex items-center gap-3 font-mono text-sm"
                  >
                    <span
                      className={
                        r.passed
                          ? "text-pass border border-pass w-5 h-5 rounded inline-flex items-center justify-center text-xs"
                          : "text-fail border border-fail w-5 h-5 rounded inline-flex items-center justify-center text-xs"
                      }
                    >
                      {r.passed ? "✓" : "✕"}
                    </span>
                    <span className="text-fg">{r.name}</span>
                    <span className="text-muted text-xs">· {r.detail}</span>
                  </motion.div>
                ))}
              </div>
            </div>
          )}

          {showRefused && (
            <div className="my-8 text-center">
              <StampRefused />
              <SavedCounter amount={attackerAmount} xrpUsd={xrpUsd} />
            </div>
          )}

          <EscalationHero
            state={state}
            onApprove={onApprove}
            onReject={onReject}
            busy={escalationBusy}
          />

          <SettledHero state={state} />
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
