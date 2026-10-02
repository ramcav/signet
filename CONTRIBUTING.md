# Contributing to Signet

Signet is a local XRPL testnet demonstration. Keep contributions focused on a reproducible behavior, add a regression test, and explain the observed result before and after the change.

## Setup and checks

Install Python 3.11 or newer, uv, Node 22 and pnpm 10. The test suites do not require wallet seeds, an OpenAI key or live ledger calls.

```sh
cd backend
uv sync --locked --extra dev
uv run pytest -q
```

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm test
pnpm build
```

CI runs the backend on Python 3.11 and 3.13, and frontend tests/build on Node 22. Run these checks before submitting a contribution. Network installation access is needed for dependencies; tests themselves use fakes or mocked transports.

## Where changes belong

- `backend/src/signet/domain`: validated values, deterministic policies and portable receipt verification. Keep network, filesystem and framework dependencies out.
- `backend/src/signet/application`: orchestration, approval lifecycle and events. Use injected agents, quotes and ledger adapters in tests.
- `backend/src/signet/adapters`: OpenAI, fresh quotes, XRPL protection/submission and SQLite audit state.
- `backend/src/signet/api`: request validation, service wiring and export endpoints. Importing this module must not load wallets or call services.
- `frontend/src`: run state and UI. Assert observed outcomes; a policy refusal or timeout is not proof of ledger rejection.
- `scripts`: explicit operator actions. Wallet bootstrap and smoke tests really transact on testnet and are never part of CI.

## Review expectations

Cover the failure that motivated the change. For payment work, test uncertain outcomes and duplicate/concurrent requests as well as successful transactions. For UI work, test HTTP failure, stale events, keyboard operation and narrow screens where relevant.

Never automatically retry an uncertain payment or remove its spending reservation. Preserve the signed transaction hash for reconciliation. Human escalation may override quantitative caps, but it must still pass destination, asset and KYT integrity rules using a fresh quote.

Do not commit `.env`, wallet recovery material, SQLite runtime data, dependency directories or build output. Keep real testnet checks opt-in and explain them separately from offline tests. Do not introduce production custody, authentication or real sanctions claims without a separate design and threat-model review.

Describe the concrete problem, resulting behavior and checks in the commit/PR message. Suitable examples are `fix: reject stale payment events after a rerun` or `feat: verify portable payment receipts offline`.
