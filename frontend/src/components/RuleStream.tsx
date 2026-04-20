import { AnimatePresence, motion } from "framer-motion";
import type { RuleCheck } from "../types";

const PREVIEW_RULES = [
  "allowlist_destination",
  "allowlist_asset",
  "per_tx_cap",
  "daily_cap",
  "kyt_sanctions",
];

export function RuleStream({ rules }: { rules: RuleCheck[] }) {
  const streamed = new Set(rules.map((r) => r.name));
  const pending = PREVIEW_RULES.filter((n) => !streamed.has(n));

  return (
    <section className="border border-border rounded-lg p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-display text-lg leading-none">Policy rules</h2>
        <span className="font-mono text-[10px] text-muted">
          {rules.length}/{PREVIEW_RULES.length} evaluated
        </span>
      </div>
      <ul className="space-y-2">
        <AnimatePresence initial={false}>
          {rules.map((r, i) => {
            const ok = r.status === "pass";
            return (
              <motion.li
                key={r.name + i}
                layout
                initial={{ opacity: 0, x: -8, backgroundColor: "rgba(217,119,87,0.08)" }}
                animate={{ opacity: 1, x: 0, backgroundColor: "rgba(0,0,0,0)" }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.35, ease: "easeOut" }}
                className="border border-border rounded-lg px-3 py-2 flex items-start gap-3"
              >
                <motion.span
                  initial={{ scale: 0.4 }}
                  animate={{ scale: 1 }}
                  transition={{ type: "spring", stiffness: 360, damping: 18 }}
                  className={
                    "font-mono text-base leading-5 pt-0.5 " +
                    (ok ? "text-pass" : "text-fail")
                  }
                >
                  {ok ? "✓" : "✗"}
                </motion.span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm">{r.name}</div>
                  <div className="font-mono text-[11px] text-muted mt-0.5 break-words">
                    {r.detail}
                  </div>
                </div>
              </motion.li>
            );
          })}
        </AnimatePresence>
        {pending.map((name) => (
          <li
            key={"pending-" + name}
            className="border border-dashed border-border/60 rounded-lg px-3 py-2 flex items-start gap-3 opacity-40"
          >
            <span className="font-mono text-base leading-5 pt-0.5 text-muted">○</span>
            <div className="flex-1 min-w-0">
              <div className="text-sm text-muted">{name}</div>
              <div className="font-mono text-[11px] text-muted/50 mt-0.5">
                pending…
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
