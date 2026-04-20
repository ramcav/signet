export function IntentComposer({
  userMessage,
  inFlight,
  onRun,
}: {
  userMessage: string;
  inFlight: boolean;
  onRun: () => void;
}) {
  return (
    <section className="border border-border rounded-lg p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-display text-lg">User message</h2>
        <button
          onClick={onRun}
          disabled={inFlight}
          className={
            "text-sm px-4 py-2 rounded-lg border transition-colors " +
            (inFlight
              ? "border-border text-muted cursor-not-allowed"
              : "border-accent text-accent hover:bg-accent hover:text-bg")
          }
        >
          {inFlight ? "Running…" : "Run"}
        </button>
      </div>
      <textarea
        readOnly
        value={userMessage}
        className="w-full h-32 bg-transparent border border-border rounded-lg p-3 font-mono text-sm text-fg/90 resize-none focus:outline-none focus:border-accent"
      />
    </section>
  );
}
