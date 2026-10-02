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
  const hasPrice = health?.xrp_usd != null && Number.isFinite(health.xrp_usd);
  const quote = health?.quote;
  const quoteSource = typeof quote?.source === "string" ? quote.source : null;
  const quoteTime = typeof quote?.as_of === "string" ? quote.as_of : null;
  const quoteLabel = quote?.demo === true ? "Demo quote" : quote?.demo === false ? "Live quote" : "Quote";
  return (
    <header className="flex flex-col xl:flex-row items-start justify-between gap-5 px-4 sm:px-8 py-6 border-b border-border">
      <div className="min-w-0">
        <h1 className="font-display text-3xl leading-none tracking-tight">
          Signet
        </h1>
        <p className="text-muted text-sm mt-2">
          cryptographic pre-trade compliance for AI agents
        </p>
      </div>
      <div className="flex flex-wrap items-start gap-3 min-w-0 max-w-full">
        <button
          onClick={onToggleCinematic}
          type="button"
          aria-pressed={cinematic}
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
        {health ? (
          <div className="min-w-0 max-w-full space-y-2 text-xs font-mono border border-border rounded-lg px-3 py-2">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-muted">XRP/USD</span>
              {hasPrice ? <span>${health.xrp_usd!.toFixed(4)}</span> : <span className="text-accent">Quote unavailable</span>}
            </div>
            {hasPrice ? (
              <div className="text-muted break-words">
                <span>{quoteSource ? `${quoteLabel} · ${quoteSource}` : "Quote source unavailable"}</span>
                {quoteTime && <time className="block mt-1" dateTime={quoteTime}>{quoteTime}</time>}
              </div>
            ) : health.quote_error && <p className="text-muted break-words">{health.quote_error}</p>}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-muted">master</span>
              <span title={health.master}>{truncMid(health.master, 6, 6)}</span>
              {typeof health.master_balance_xrp === "number" && (
                <>
                  <span className="text-muted">balance</span>
                  <span className={health.master_balance_xrp < 1000 ? "text-fail" : "text-pass"}>
                    {health.master_balance_xrp.toLocaleString(undefined, { maximumFractionDigits: 0 })} XRP
                  </span>
                </>
              )}
            </div>
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
