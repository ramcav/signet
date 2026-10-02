import { useEffect, useRef, useState } from "react";
import type { SignetEvent } from "./types";

const EVENT_TYPES = [
  "run.started",
  "run.completed",
  "run.error",
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
  "ledger.failed",
  "ledger.unknown",
  "escalation.approved",
  "escalation.rejected",
];

export function useEventStream(onEvent: (ev: SignetEvent) => void, onReconnect?: () => void) {
  const callback = useRef(onEvent);
  callback.current = onEvent;
  const recover = useRef(onReconnect);
  recover.current = onReconnect;
  const lastEventId = useRef("");
  const [connection, setConnection] = useState<"connecting" | "connected" | "reconnecting">("connecting");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const es = new EventSource(lastEventId.current ? `/events?last_event_id=${encodeURIComponent(lastEventId.current)}` : "/events");
    const handler = (e: MessageEvent) => {
      try {
        if (e.lastEventId && Number(e.lastEventId) <= Number(lastEventId.current)) return;
        const payload = JSON.parse(e.data) as SignetEvent;
        callback.current(payload);
        if (e.lastEventId) lastEventId.current = e.lastEventId;
      } catch (err) {
        // ignore
      }
    };
    const reset = () => { lastEventId.current = ""; recover.current?.(); };
    es.addEventListener("stream.reset", reset);
    for (const t of EVENT_TYPES) {
      es.addEventListener(t, handler as EventListener);
    }
    es.onopen = () => { setConnection("connected"); recover.current?.(); };
    es.onerror = () => setConnection("reconnecting");
    return () => {
      for (const t of EVENT_TYPES) {
        es.removeEventListener(t, handler as EventListener);
      }
      es.close();
      es.removeEventListener("stream.reset", reset);
    };
  }, [retry]);
  return { connection, reconnect: () => { setConnection("reconnecting"); setRetry(value => value + 1); } };
}
