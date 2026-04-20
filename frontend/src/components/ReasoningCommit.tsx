import { motion } from "framer-motion";
import { truncMid } from "../util";
import { useTypeOn } from "../useTypeOn";

export function ReasoningCommit({
  merkleRoot,
  stepCount,
}: {
  merkleRoot: string | null;
  stepCount: number | null;
}) {
  const pretty = merkleRoot ? truncMid(merkleRoot, 10, 10) : "";
  const typed = useTypeOn(pretty, 14);

  const active = !!merkleRoot;
  return (
    <motion.div
      layout
      className={
        "border rounded-lg px-4 py-3 flex items-center justify-between transition-colors duration-300 " +
        (active ? "border-accent/70 bg-accent/5" : "border-dashed border-border/60")
      }
    >
      <div className="min-w-0">
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted">
          reasoning commit
        </div>
        <div className="font-mono text-sm mt-1 text-fg">
          {active ? (
            <>
              {typed}
              {typed.length < pretty.length && (
                <motion.span
                  className="inline-block w-[2px] h-[1em] align-[-2px] ml-0.5 bg-accent"
                  animate={{ opacity: [1, 0, 1] }}
                  transition={{ duration: 0.9, repeat: Infinity }}
                />
              )}
            </>
          ) : (
            <span className="text-muted/60 tracking-wider">0x▓▓▓▓▓▓▓▓▓▓…▓▓▓▓▓▓▓▓▓▓</span>
          )}
        </div>
      </div>
      <div className="text-[10px] font-mono uppercase tracking-wider text-muted whitespace-nowrap ml-4">
        {active ? `${stepCount} steps` : "Merkle(…)"}
      </div>
    </motion.div>
  );
}
