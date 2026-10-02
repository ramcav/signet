export function IntentComposer({
  userMessage,
  inFlight,
  approvalPending = false,
  needsReconciliation = false,
  setupRequired = false,
  onRun,
}: {
  userMessage: string;
  inFlight: boolean;
  approvalPending?: boolean;
  needsReconciliation?: boolean;
  setupRequired?: boolean;
  onRun: () => void;
}) {
  return (
    <section className="border border-border rounded-lg p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-display text-lg">User message</h2>
        <button
          onClick={onRun}
          disabled={setupRequired || inFlight || approvalPending || needsReconciliation}
          className={
            "text-sm px-4 py-2 rounded-lg border transition-colors " +
            (setupRequired || inFlight || approvalPending || needsReconciliation
              ? "border-border text-muted cursor-not-allowed"
              : "border-accent text-accent hover:bg-accent hover:text-bg")
          }
        >
          {setupRequired ? "Setup required" : needsReconciliation ? "Check status before rerunning" : approvalPending ? "Approval pending" : inFlight ? "Running…" : "Run"}
        </button>
      </div>
      <textarea
        aria-label="User message"
        readOnly
        value={userMessage}
        className="w-full h-32 bg-transparent border border-border rounded-lg p-3 font-mono text-sm text-fg/90 resize-none focus:outline-none focus:border-accent"
      />
    </section>
  );
}
