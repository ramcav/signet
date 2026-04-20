import { motion } from "framer-motion";

export function RawAgentOutput({
  raw,
  thinking,
}: {
  raw: string | null;
  thinking: boolean;
}) {
  return (
    <section className="border border-border rounded-lg p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-display text-lg leading-none">Agent output</h2>
        <span className="font-mono text-[10px] text-muted">
          {raw ? "tool-call emitted" : thinking ? "LLM thinking…" : "standby"}
        </span>
      </div>
      <p className="text-xs text-muted mb-3">
        Raw arguments from the LLM's <span className="font-mono">submit_payment</span> tool call. In
        scenario B, the injection flips this to an attacker destination.
      </p>
      {thinking && !raw && (
        <div className="flex items-center gap-3 text-sm text-muted">
          <span className="spinner" />
          <span>awaiting LLM response…</span>
        </div>
      )}
      {!raw && !thinking && (
        <pre className="font-mono text-xs whitespace-pre-wrap break-words text-muted/60 bg-black/20 border border-dashed border-border/60 rounded-lg p-3">
{`{
  "destination": "…",
  "amount":      …,
  "asset":       "XRP",
  "rationale":   "…"
}`}
        </pre>
      )}
      {raw && (
        <motion.pre
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="font-mono text-xs whitespace-pre-wrap break-words text-fg/90 bg-black/30 border border-border rounded-lg p-3 max-h-72 overflow-auto"
        >
          {raw}
        </motion.pre>
      )}
    </section>
  );
}
