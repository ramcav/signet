import { motion } from "framer-motion";
import type { RunState } from "../state";
import { truncMemo, truncMid } from "../util";
import { useTypeOn } from "../useTypeOn";

export function LedgerPanel({ state }: { state: RunState }) {
  const { ledger, refused } = state;
  const settledHash =
    ledger.phase === "settled" ? truncMid(ledger.tx.tx_hash, 12, 10) : "";
  const typed = useTypeOn(settledHash, 12);

  return (
    <section className="border border-border rounded-lg p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-display text-lg leading-none">XRPL Ledger</h2>
        <span className="font-mono text-[10px] text-muted">
          {ledger.phase === "settled"
            ? "settled"
            : ledger.phase === "submitting"
            ? "submitting"
            : ledger.phase === "single_sig_failed"
            ? "rejected"
            : refused
            ? "not submitted"
            : "standby"}
        </span>
      </div>

      {ledger.phase === "idle" && !refused && (
        <PreviewSkeleton />
      )}

      {ledger.phase === "idle" && refused && (
        <div className="rounded-lg border border-fail/60 bg-fail/5 px-3 py-2 text-sm text-fail/90">
          Not submitted — policy refused to co-sign.
        </div>
      )}

      {ledger.phase === "submitting" && (
        <div className="flex items-center gap-3 text-sm">
          <span className="spinner" />
          <span>submitting to XRPL testnet…</span>
        </div>
      )}

      {ledger.phase === "settled" && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="space-y-4"
        >
          <div className="flex items-center gap-2">
            <span
              className={
                "text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded border " +
                (ledger.tx.validated
                  ? "border-pass text-pass"
                  : "border-fail text-fail")
              }
            >
              {ledger.tx.engine_result}
            </span>
            {ledger.tx.validated && (
              <span className="text-[10px] font-mono uppercase tracking-wider text-muted">
                validated on testnet
              </span>
            )}
          </div>

          <div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-1">
              tx_hash
            </div>
            <div className="font-mono text-sm break-all">
              {typed}
              <BlinkingCursor shown={typed.length < settledHash.length} />
            </div>
          </div>

          <div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-1">
              memo &middot; reasoningCommit
            </div>
            <div className="font-mono text-sm text-accent/90">
              {truncMemo(ledger.tx.memo_hex)}
            </div>
          </div>

          <a
            href={ledger.tx.explorer_url}
            target="_blank"
            rel="noreferrer"
            className="inline-block text-sm text-accent border-b border-accent/40 hover:border-accent"
          >
            view on explorer ↗
          </a>
        </motion.div>
      )}

      {ledger.phase === "single_sig_failed" && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-3"
        >
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded border border-fail text-fail">
              {ledger.result.engine_result}
            </span>
            <span className="text-[10px] font-mono uppercase tracking-wider text-muted">
              rippled rejected
            </span>
          </div>
          <p className="text-sm text-fail/90">
            Single-signature fallback attempt — ledger refused: quorum not met.
          </p>
          {ledger.result.tx_hash && (
            <div className="font-mono text-xs text-muted break-all">
              {truncMid(ledger.result.tx_hash, 12, 10)}
            </div>
          )}
        </motion.div>
      )}
    </section>
  );
}

function PreviewSkeleton() {
  return (
    <div className="space-y-4 opacity-60">
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded border border-dashed border-border text-muted">
          engine_result
        </span>
        <span className="text-[10px] font-mono uppercase tracking-wider text-muted">
          will appear here
        </span>
      </div>
      <div>
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-1">
          tx_hash
        </div>
        <div className="font-mono text-sm text-muted/60 tracking-wider">
          ▓▓▓▓▓▓▓▓▓▓▓▓…▓▓▓▓▓▓▓▓▓▓
        </div>
      </div>
      <div>
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-1">
          memo · reasoningCommit
        </div>
        <div className="font-mono text-sm text-muted/60">0x▓▓▓▓▓▓▓▓…▓▓▓▓▓▓▓▓</div>
      </div>
      <div className="text-sm text-muted/70">
        on settle, the tx hash types in here and the memo carries the Merkle
        root of the agent's reasoning trace.
      </div>
    </div>
  );
}

function BlinkingCursor({ shown }: { shown: boolean }) {
  if (!shown) return null;
  return (
    <motion.span
      className="inline-block w-[2px] h-[1em] align-[-2px] ml-0.5 bg-accent"
      animate={{ opacity: [1, 0, 1] }}
      transition={{ duration: 0.9, repeat: Infinity }}
    />
  );
}
