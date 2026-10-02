import { motion, useReducedMotion } from "framer-motion";
import type { RunState } from "../state";
import { truncMemo, truncMid } from "../util";
import { useTypeOn } from "../useTypeOn";

export function LedgerPanel({ state }: { state: RunState }) {
  const { ledger, refused } = state;
  const reducedMotion = useReducedMotion();
  const result = ledger.phase === "single_sig_failed"
    ? ledger.result
    : "tx" in ledger ? ledger.tx : null;
  const success = result?.outcome === "success" && result.validated && result.engine_result === "tesSUCCESS";
  const unknown = result && !success && (result.outcome === "unknown" || result.outcome === "success");
  const status = result
    ? success ? "settled" : unknown ? "outcome unknown" : result.outcome === "rejected" ? "rejected" : "failed"
    : ledger.phase === "submitting" ? "submitting" : refused ? "not submitted" : "standby";
  const hash = result?.tx_hash ? truncMid(result.tx_hash, 12, 10) : "";
  const typedHash = useTypeOn(hash, 12);
  const tx = "tx" in ledger ? ledger.tx : null;

  return (
    <section className="min-w-0 border border-border rounded-lg p-5" aria-label="XRPL ledger result">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h2 className="font-display text-lg leading-none">XRPL Ledger</h2>
        <span className="font-mono text-[10px] text-muted">{status}</span>
      </div>
      {ledger.phase === "idle" && !refused && (
        <p className="text-sm text-muted">Transaction results appear here after submission. A submitted payment includes the receipt commitment in its memo.</p>
      )}
      {ledger.phase === "idle" && refused && (
        <div className="rounded-lg border border-fail/60 bg-fail/5 px-3 py-2 text-sm text-fail/90">Not submitted: policy refused to co-sign.</div>
      )}
      {ledger.phase === "submitting" && (
        <div className="flex items-center gap-3 text-sm"><span className="spinner" aria-hidden="true" /><span>Submitting to XRPL testnet...</span></div>
      )}
      {result && (
        <motion.div initial={reducedMotion ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reducedMotion ? 0 : 0.35 }} className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded border break-all ${success ? "border-pass text-pass" : unknown ? "border-accent text-accent" : "border-fail text-fail"}`}>{result.engine_result || "No engine result"}</span>
            {result.validated && <span className="text-[10px] font-mono uppercase tracking-wider text-muted">Validated on testnet</span>}
          </div>
          <p className="text-sm text-muted">
            {success ? "Payment settled on XRPL testnet."
              : unknown ? "The submission outcome is unknown. Check the transaction before attempting another payment."
              : result.outcome === "rejected" ? "XRPL rejected this transaction."
              : "This attempt failed without a confirmed successful payment."}
          </p>
          {ledger.phase === "single_sig_failed" && (
            <p className="text-sm text-muted">{result.outcome === "rejected" && result.engine_result === "tefBAD_QUORUM"
              ? "The single-signature attempt was rejected because the signer quorum was not met."
              : "Result of the single-signature demonstration attempt."}</p>
          )}
          {hash && (
            <div><div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-1">tx_hash</div><div className="font-mono text-sm break-all">{reducedMotion ? hash : typedHash}</div></div>
          )}
          {tx?.memo_hex && (
            <div><div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-1">Memo · receipt commitment</div><div className="font-mono text-sm text-accent/90 break-all">{truncMemo(tx.memo_hex)}</div></div>
          )}
          {tx?.explorer_url && <a href={tx.explorer_url} target="_blank" rel="noreferrer" className="inline-block text-sm text-accent border-b border-accent/40 hover:border-accent">View on explorer ↗</a>}
        </motion.div>
      )}
    </section>
  );
}
