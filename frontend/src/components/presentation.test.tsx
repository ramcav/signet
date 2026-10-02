import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { initialRunState, type RunState } from "../state";
import { CinematicOverlay } from "./CinematicOverlay";
import { LedgerPanel } from "./LedgerPanel";
import { PipelineDiagram } from "./PipelineDiagram";

const state: RunState = { ...initialRunState, runId: "run-123456", userMessage: "Send 75 XRP", intent: { id: "intent", from: "source", to: "destination", amount: 75, asset: "XRP", rationale: "rebalance" } };
const overlay = { active: true, scenario: "B" as const, onClose: vi.fn(), onApprove: vi.fn(), onReject: vi.fn(), escalationBusy: false };

it("does not invent protocol proof or savings from a policy refusal", () => {
  render(<CinematicOverlay {...overlay} state={{ ...state, refused: { reason: "Policy cap", failed: [] } }} />);
  expect(screen.queryByText(/tefBAD_QUORUM/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Funds never moved|saved/)).not.toBeInTheDocument();
});

it("shows an unknown single-signature result without claiming ledger rejection", () => {
  const unknown: RunState = { ...state, ledger: { phase: "single_sig_failed", result: { engine_result: "timeout", outcome: "unknown", validated: false, tx_hash: "hash" } } };
  render(<LedgerPanel state={unknown} />);
  expect(screen.getAllByText(/unknown/i).length).toBeGreaterThan(0);
  expect(screen.queryByText(/quorum not met|rippled rejected/)).not.toBeInTheDocument();
});

it("shows failed ledger results in the pipeline instead of tesSUCCESS", () => {
  render(<PipelineDiagram state={{ ...state, ledger: { phase: "failed", tx: { outcome: "failed", tx_hash: "hash", engine_result: "tecPATH_DRY", validated: true, memo_hex: "", explorer_url: "" } } }} />);
  expect(screen.getByText("tecPATH_DRY")).toBeInTheDocument();
  expect(screen.queryByText("tesSUCCESS")).not.toBeInTheDocument();
});

it("uses the actual submitted amount when displaying confirmed quorum rejection", () => {
  render(<CinematicOverlay {...overlay} state={{ ...state, ledger: { phase: "single_sig_failed", result: { outcome: "rejected", engine_result: "tefBAD_QUORUM", validated: false, tx_hash: "hash" } } }} />);
  expect(screen.getByText(/Attempted amount/)).toHaveTextContent("75 XRP");
  expect(screen.queryByText(/10,000|saved|\$5,000/)).not.toBeInTheDocument();
});

it("focuses and traps the dialog, handles Escape, and restores focus", () => {
  const trigger = document.createElement("button");
  document.body.appendChild(trigger);
  trigger.focus();
  const onClose = vi.fn();
  const { unmount } = render(<CinematicOverlay {...overlay} onClose={onClose} state={state} />);
  const dialog = screen.getByRole("dialog", { name: /Cinematic/ });
  expect(dialog).toHaveAttribute("aria-modal", "true");
  const close = within(dialog).getByRole("button", { name: /exit cinematic/i });
  expect(close).toHaveFocus();
  fireEvent.keyDown(close, { key: "Tab" });
  expect(close).toHaveFocus();
  fireEvent.keyDown(close, { key: "Escape" });
  expect(onClose).toHaveBeenCalledOnce();
  unmount();
  expect(trigger).toHaveFocus();
  trigger.remove();
});

it("does not present an unvalidated success response as a settled payment", () => {
  render(<LedgerPanel state={{ ...state, ledger: { phase: "settled", tx: { outcome: "success", tx_hash: "hash", engine_result: "tesSUCCESS", validated: false, memo_hex: "", explorer_url: "" } } }} />);
  expect(screen.getByText("outcome unknown")).toBeInTheDocument();
  expect(screen.queryByText("Payment settled on XRPL testnet.")).not.toBeInTheDocument();
});

it("does not infer compromised agent output from an ordinary policy refusal", () => {
  render(<PipelineDiagram state={{ ...state, refused: { reason: "Daily cap exceeded", failed: ["daily_cap"] } }} />);
  expect(screen.getByText("intent emitted")).toBeInTheDocument();
  expect(screen.getByText("not submitted")).toBeInTheDocument();
  expect(screen.queryByText(/compromised/)).not.toBeInTheDocument();
});

it("shows unknown ledger outcome even if policy previously refused", () => {
  render(<CinematicOverlay {...overlay} state={{ ...state, refused: { reason: "Policy cap", failed: [] }, ledger: { phase: "single_sig_failed", result: { engine_result: "timeout", outcome: "unknown", validated: false, tx_hash: "hash" } } }} />);
  expect(screen.getByRole("heading", { name: /Submission outcome unknown/ })).toBeInTheDocument();
  expect(screen.queryByText(/XRPL rejected|quorum was not met/)).not.toBeInTheDocument();
});

it("traps focus across approval actions and skips them while busy", () => {
  const pending: RunState = { ...state, escalationStatus: "pending", escalation: { id: "approval", reason: "Threshold", intent: state.intent!, notional_usd: 100 } };
  const { rerender } = render(<CinematicOverlay {...overlay} state={pending} />);
  const close = screen.getByRole("button", { name: /exit cinematic/i });
  const reject = screen.getByRole("button", { name: "Reject" });
  fireEvent.keyDown(close, { key: "Tab", shiftKey: true });
  expect(reject).toHaveFocus();
  fireEvent.keyDown(reject, { key: "Tab" });
  expect(close).toHaveFocus();
  rerender(<CinematicOverlay {...overlay} state={pending} escalationBusy />);
  fireEvent.keyDown(close, { key: "Tab", shiftKey: true });
  expect(close).toHaveFocus();
});
