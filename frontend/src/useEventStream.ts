import { useEffect } from "react";
import type { SignetEvent } from "./types";

const EVENT_TYPES = [
  "run.started",
  "agent.thinking",
  "agent.intent",
  "rule.check",
  "reasoning.commit",
  "policy.refused",
  "policy.escalated",
  "ledger.single_sig_attempt",
  "ledger.single_sig_result",
  "signature.agent",
  "signature.policy",
  "ledger.submitting",
  "ledger.settled",
  "escalation.approved",
  "escalation.rejected",
];

export function useEventStream(onEvent: (ev: SignetEvent) => void) {
  useEffect(() => {
    const es = new EventSource("/events");
    const handler = (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data) as SignetEvent;
        onEvent(payload);
      } catch (err) {
        // ignore
      }
    };
    for (const t of EVENT_TYPES) {
      es.addEventListener(t, handler as EventListener);
    }
    es.onerror = () => {
      // let browser auto-reconnect
    };
    return () => {
      for (const t of EVENT_TYPES) {
        es.removeEventListener(t, handler as EventListener);
      }
      es.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
