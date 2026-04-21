import type { Health } from "../types";
import { truncMid } from "../util";

export function Header({
  health,
  cinematic,
  onToggleCinematic,
}: {
  health: Health | null;
  cinematic: boolean;
  onToggleCinematic: () => void;
}) {
  return (
    <header className="flex items-start justify-between px-8 py-6 border-b border-border">
      <div>
        <h1 className="font-display text-3xl leading-none tracking-tight">
          Signet
        </h1>
        <p className="text-muted text-sm mt-2">
          cryptographic pre-trade compliance for AI agents
        </p>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleCinematic}
          className={
            "font-mono text-xs uppercase tracking-widest border rounded-lg px-3 py-2 transition-colors " +
            (cinematic
              ? "border-accent text-accent bg-accent/10"
              : "border-border text-muted hover:text-fg hover:border-fg/60")
          }
          title="Toggle cinematic mode"
        >
          <span className={"inline-block w-1.5 h-1.5 rounded-full mr-2 " + (cinematic ? "bg-accent" : "bg-muted/50")} />
          cinematic
        </button>
        {health && typeof health.xrp_usd === "number" ? (
          <div className="flex items-center gap-3 text-xs font-mono border border-border rounded-lg px-3 py-2">
            <span className="w-2 h-2 rounded-full bg-pass inline-block" />
            <span className="text-muted">XRP/USD</span>
            <span>${health.xrp_usd.toFixed(4)}</span>
            <span className="text-muted ml-2">master</span>
            <span>{truncMid(health.master, 6, 6)}</span>
            {typeof health.master_balance_xrp === "number" && (
              <>
                <span className="text-muted ml-2">balance</span>
                <span className={health.master_balance_xrp < 1000 ? "text-fail" : "text-pass"}>
                  {health.master_balance_xrp.toLocaleString(undefined, { maximumFractionDigits: 0 })} XRP
                </span>
              </>
            )}
          </div>
        ) : (
          <div className="text-xs font-mono text-muted border border-border rounded-lg px-3 py-2">
            connecting…
          </div>
        )}
      </div>
    </header>
  );
}
