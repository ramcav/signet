import { motion } from "framer-motion";

export function SignaturePanel({
  agentSigned,
  policySigned,
  policyRefused,
}: {
  agentSigned: boolean;
  policySigned: boolean;
  policyRefused: boolean;
}) {
  return (
    <section className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <SigCard label="Agent" sub="key_a" active={agentSigned} />
      <SigCard
        label="Policy"
        sub="key_b"
        active={policySigned}
        refused={policyRefused}
      />
    </section>
  );
}

function KeyGlyph({
  state,
}: {
  state: "idle" | "signed" | "refused";
}) {
  const color =
    state === "signed" ? "#D97757" : state === "refused" ? "#E26D5A" : "#3A3732";
  return (
    <motion.svg
      width="36"
      height="36"
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      animate={
        state === "signed"
          ? { rotate: [0, -12, 0], scale: [1, 1.08, 1] }
          : state === "refused"
          ? { x: [0, -3, 3, -3, 0] }
          : { opacity: 0.7 }
      }
      transition={{ duration: 0.6 }}
    >
      <circle cx="8" cy="15" r="4" />
      <path d="M10.85 12.15 19 4" />
      <path d="M18 5l1.5 1.5" />
      <path d="M15 8l2 2" />
    </motion.svg>
  );
}

function SigCard({
  label,
  sub,
  active,
  refused,
}: {
  label: string;
  sub: string;
  active: boolean;
  refused?: boolean;
}) {
  const state: "idle" | "signed" | "refused" = refused
    ? "refused"
    : active
    ? "signed"
    : "idle";
  const border =
    state === "refused"
      ? "border-fail"
      : state === "signed"
      ? "border-accent"
      : "border-border";
  const glow =
    state === "signed"
      ? "shadow-[0_0_0_3px_rgba(217,119,87,0.12)]"
      : state === "refused"
      ? "shadow-[0_0_0_3px_rgba(226,109,90,0.14)]"
      : "";
  return (
    <motion.div
      layout
      className={
        "border rounded-lg p-4 transition-colors duration-300 " +
        border +
        " " +
        glow +
        (state === "signed" ? " bg-accent/5" : "")
      }
    >
      <div className="flex items-center gap-3">
        <KeyGlyph state={state} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-display text-base leading-none">{label}</div>
              <div className="font-mono text-[11px] text-muted mt-1">{sub}</div>
            </div>
          </div>
          <div className="mt-2">
            {state === "refused" ? (
              <span className="text-[10px] font-mono uppercase tracking-wider border border-fail text-fail px-2 py-0.5 rounded">
                refused
              </span>
            ) : state === "signed" ? (
              <span className="text-[10px] font-mono uppercase tracking-wider border border-accent text-accent px-2 py-0.5 rounded">
                signed
              </span>
            ) : (
              <span className="text-[10px] font-mono uppercase tracking-wider border border-border text-muted px-2 py-0.5 rounded">
                awaiting quorum
              </span>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
