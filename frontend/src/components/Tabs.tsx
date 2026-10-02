import { useRef } from "react";
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
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  return (
    <div role="tablist" aria-label="Scenarios" className="flex gap-1 px-4 sm:px-8 pt-6 border-b border-border overflow-x-auto">
      {TABS.map((t, index) => {
        const on = t.key === active;
        return (
          <button
            key={t.key}
            ref={(element) => { buttons.current[index] = element; }}
            type="button"
            role="tab"
            id={`scenario-tab-${t.key}`}
            aria-controls={`scenario-panel-${t.key}`}
            aria-selected={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(t.key)}
            onKeyDown={(event) => {
              let next: number;
              switch (event.key) {
                case "ArrowRight": next = (index + 1) % TABS.length; break;
                case "ArrowLeft": next = (index + TABS.length - 1) % TABS.length; break;
                case "Home": next = 0; break;
                case "End": next = TABS.length - 1; break;
                default: return;
              }
              event.preventDefault();
              onChange(TABS[next].key);
              buttons.current[next]?.focus();
            }}
            className={
              "min-w-0 flex-1 sm:flex-none px-2 sm:px-4 py-3 text-xs sm:text-sm transition-colors border-b-2 -mb-px " +
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
