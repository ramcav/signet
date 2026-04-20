import type { RunState } from "../state";

export function EscalationCard({
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
  const esc = state.escalation;
  if (!esc) return null;
  const resolved = state.escalationStatus && state.escalationStatus !== "pending";
  return (
    <section className="border border-accent rounded-lg p-5 fade-in bg-accent/5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-display text-lg text-accent">Human approval required</h2>
        <span className="text-[10px] font-mono uppercase tracking-wider text-accent border border-accent px-2 py-1 rounded">
          {state.escalationStatus}
        </span>
      </div>
      <p className="text-sm text-fg/80 mb-4">{esc.reason}</p>
      <div className="grid grid-cols-2 gap-3 mb-4">
        <KV k="from" v={esc.intent.from} mono />
        <KV k="to" v={esc.intent.to} mono />
        <KV k="amount" v={`${esc.intent.amount} ${esc.intent.asset}`} />
        <KV k="notional" v={`$${esc.notional_usd.toLocaleString()}`} />
      </div>
      <div className="border-t border-border pt-3 mb-4">
        <div className="text-xs text-muted mb-1">rationale</div>
        <div className="text-sm">{esc.intent.rationale}</div>
      </div>
      {!resolved && (
        <div className="flex gap-3">
          <button
            onClick={onApprove}
            disabled={busy}
            className="px-4 py-2 rounded-lg bg-accent text-bg text-sm disabled:opacity-50"
          >
            Approve
          </button>
          <button
            onClick={onReject}
            disabled={busy}
            className="px-4 py-2 rounded-lg border border-border text-sm text-fg hover:border-fail hover:text-fail disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}
    </section>
  );
}

function KV({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-xs text-muted mb-0.5">{k}</div>
      <div className={mono ? "font-mono text-xs break-all" : "text-sm"}>{v}</div>
    </div>
  );
}
