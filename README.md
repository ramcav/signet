# Signet

A demo of **cryptographic pre-trade compliance for AI agents**, settling real transactions on the XRP Ledger testnet.

## What this is, in plain words

Autonomous AI agents are starting to move money on users' behalf. The problem: an LLM can be tricked. A prompt injection, a cleverly worded request, or just a bad day can make an agent propose a trade nobody sanctioned — draining a wallet, paying the wrong counterparty, breaking a limit.

Signet fixes this by requiring **two signatures** on every payment:

- one from the **agent** (what it decided to do)
- one from a **policy engine** (a deterministic set of rules: allowlists, spending caps, sanctions, escalation thresholds)

Neither can move funds alone. The rule is enforced by the ledger itself — there's no middleware to bypass. If the policy engine refuses to sign, the transaction physically cannot settle.

The demo walks through three scenarios:

- **A — Benign trade.** Agent proposes a sensible rebalance. Rules pass. Both keys sign. The ledger settles it.
- **B — Jailbreak.** The user message contains a prompt injection. The real LLM obeys the injection and emits an attacker-drain intent. The policy engine refuses. Even if the agent tried to submit alone, the ledger rejects it (`tefBAD_QUORUM`) because only one signature is present. Nothing moves.
- **C — Over threshold.** A legitimate but large trade trips an escalation limit. The policy engine won't auto-sign; it routes the decision to a human. Click Approve → both keys sign → ledger settles.

Every settled transaction carries a cryptographic **receipt of the agent's reasoning** (a Merkle root) in its memo field, so anyone can later verify that the trade matched the agent's stated logic.

## How to run it

Requirements: [`uv`](https://docs.astral.sh/uv/) for Python, [`pnpm`](https://pnpm.io/) for Node, and an `OPENAI_API_KEY` in `.env` at the repo root.

**First-time setup** (funds three testnet wallets and configures a 2-of-2 multisig on the treasury):

```bash
cd backend
uv sync --extra dev
uv run python ../scripts/fund_wallets.py
```

If the master wallet runs low later, top it up:

```bash
uv run python ../scripts/topup.py 20
```

**Running the demo** — two terminals:

```bash
# terminal 1 — API (port 8000)
cd backend && uv run uvicorn src.main:app --port 8000

# terminal 2 — UI (port 5173)
cd frontend && pnpm install && pnpm dev
```

Open http://localhost:5173 and click through the three scenario tabs.

## Layout

```
signet/
├── backend/      FastAPI + pure domain layer + XRPL adapter + OpenAI adapter
├── frontend/     Vite + React + Tailwind, three scenario tabs, SSE-driven UI
├── scripts/      wallet bootstrap + top-up + smoke tests
└── .env          OPENAI_API_KEY lives here
```

## Tests

```bash
cd backend && uv run pytest
```

The policy engine is pure Python with no I/O dependencies, so the test suite covers all five rules (allowlist destination, allowlist asset, per-tx cap, daily cap, KYT sanctions) plus the escalation tiering and the Merkle commitment.
