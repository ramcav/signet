import type { ScenarioKey } from "../types";

const TABS: { key: ScenarioKey; label: string }[] = [
  { key: "A", label: "Scenario A: Benign" },
  { key: "B", label: "Scenario B: Jailbreak" },
  { key: "C", label: "Scenario C: Escalation" },
];

export function Tabs({
  active,
  onChange,
}: {
  active: ScenarioKey;
  onChange: (k: ScenarioKey) => void;
}) {
  return (
    <div className="flex gap-1 px-8 pt-6 border-b border-border">
      {TABS.map((t) => {
        const on = t.key === active;
        return (
          <button
            key={t.key}
            onClick={() => onChange(t.key)}
            className={
              "px-4 py-3 text-sm transition-colors border-b-2 -mb-px " +
              (on
                ? "border-accent text-fg"
                : "border-transparent text-muted hover:text-fg")
            }
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
