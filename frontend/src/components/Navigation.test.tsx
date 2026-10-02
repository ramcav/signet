import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { Health, ScenarioKey } from "../types";
import { Header } from "./Header";
import { Tabs } from "./Tabs";

function ScenarioTabs() {
  const [active, setActive] = useState<ScenarioKey>("A");
  return <Tabs active={active} onChange={setActive} />;
}

const health: Health = {
  master: "rTreasuryWalletAddress",
  agent: "rAgent",
  policy: "rPolicy",
  allowlist: [],
  xrp_usd: 0.5,
  master_balance_xrp: 2000,
};

it("connects the selected tab to its scenario panel with one tab stop", () => {
  render(<ScenarioTabs />);
  expect(screen.getByRole("tablist", { name: "Scenarios" })).toBeInTheDocument();
  const active = screen.getByRole("tab", { selected: true });
  expect(active).toHaveAttribute("id", "scenario-tab-A");
  expect(active).toHaveAttribute("aria-controls", "scenario-panel-A");
  expect(active).toHaveAttribute("tabindex", "0");
  for (const tab of screen.getAllByRole("tab", { selected: false })) {
    expect(tab).toHaveAttribute("tabindex", "-1");
  }
});

it("moves focus and selection with arrows, Home and End, including wrapping", async () => {
  const user = userEvent.setup();
  render(<ScenarioTabs />);
  await user.tab();
  await user.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { selected: true })).toHaveTextContent("Scenario B");
  expect(screen.getByRole("tab", { selected: true })).toHaveFocus();
  await user.keyboard("{End}");
  expect(screen.getByRole("tab", { selected: true })).toHaveTextContent("Scenario C");
  await user.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { selected: true })).toHaveTextContent("Scenario A");
  await user.keyboard("{ArrowLeft}");
  expect(screen.getByRole("tab", { selected: true })).toHaveTextContent("Scenario C");
  await user.keyboard("{Home}");
  expect(screen.getByRole("tab", { selected: true })).toHaveTextContent("Scenario A");
  expect(screen.getByRole("tab", { selected: true })).toHaveFocus();
});

it("shows unavailable quotes and wallet metadata after health loads", () => {
  render(<Header health={{ ...health, xrp_usd: null, quote: null, quote_error: "Fresh XRP/USD quote unavailable" }} cinematic={false} onToggleCinematic={vi.fn()} />);
  expect(screen.getByText("Quote unavailable")).toBeInTheDocument();
  expect(screen.getByText("Fresh XRP/USD quote unavailable")).toBeInTheDocument();
  expect(screen.getByText("master")).toBeInTheDocument();
  expect(screen.getByText("2,000 XRP")).toBeInTheDocument();
  expect(screen.queryByText(/connecting/i)).not.toBeInTheDocument();
});

it.each([
  [true, "explicit-demo", "Demo quote"],
  [false, "coingecko", "Live quote"],
])("identifies quote provenance for demo=%s", (demo, source, label) => {
  render(<Header health={{ ...health, quote: { demo, source, as_of: "2026-10-01T01:02:03Z" } }} cinematic={false} onToggleCinematic={vi.fn()} />);
  expect(screen.getByText(new RegExp(`${label}.*${source}`))).toBeInTheDocument();
  expect(screen.getByText("$0.5000")).toBeInTheDocument();
  expect(screen.getByText("2026-10-01T01:02:03Z")).toHaveAttribute("datetime", "2026-10-01T01:02:03Z");
});

it("does not label a quote live when provenance is absent", () => {
  render(<Header health={health} cinematic={false} onToggleCinematic={vi.fn()} />);
  expect(screen.getByText("Quote source unavailable")).toBeInTheDocument();
  expect(screen.queryByText(/Live quote/)).not.toBeInTheDocument();
});
