# Signet

A local demonstration of cryptographic pre-trade policy enforcement for AI agents, using native XRP payments on XRPL testnet.

An agent proposes a payment. A deterministic policy engine checks the destination, asset, USD limits and a mock KYT score. The treasury requires both the agent and policy signatures. Bootstrap disables master-key authorization and removes any regular key; startup and each signing attempt audit the validated account configuration.

The three scenarios demonstrate an allowed payment, an attempted prompt injection, and a payment requiring local operator approval. Model output varies: the UI reports the actual policy and ledger outcomes rather than assuming that an injection worked or a transaction settled.

## Run locally

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 22, pnpm 10, and an OpenAI API key. Copy `backend/.env.example` to `backend/.env` and set `OPENAI_API_KEY`. A root `.env` is also supported.

Without a configured API key, the server and UI still start, but the UI displays setup instructions and disables new scenarios. Add the key to `backend/.env` and restart the backend. A failed treasury protection audit includes the migration command below; startup never silently changes wallet authorization.

Install the backend and create protected **testnet** wallets:

```sh
cd backend
uv sync --locked --extra dev
uv run python ../scripts/fund_wallets.py
```

Wallet seeds are saved to `backend/config/wallets.json` before funding or account configuration. Re-running setup audits the existing wallets and never replaces their seeds. To resume interrupted setup or migrate wallets created by the earlier demo:

```sh
uv run python ../scripts/fund_wallets.py --secure-existing
```

That explicit command configures the saved treasury, removes any RegularKey and disables its master key after verifying the intended signer list. Keep the agent and policy seeds: both are required afterward. Application startup only audits protection; it never changes account settings.

Run in two terminals:

```sh
# From backend/, one worker
uv run uvicorn src.main:app --host 127.0.0.1 --port 8000
```

```sh
# From frontend/
pnpm install --frozen-lockfile
pnpm dev
```

Open http://localhost:5173. The Vite development proxy forwards API requests to port 8000.

To top up an existing treasury or run an optional real testnet smoke payment:

```sh
# From backend/
uv run python ../scripts/topup.py 20
uv run python ../scripts/smoke_multisig.py
```

The smoke script exports a receipt under `backend/data/smoke-receipts/`. These scripts contact testnet and are not run by tests or CI.

## Prices, spending and recovery

Live mode requires a positive, finite XRP/USD quote from CoinGecko with a provider timestamp less than 60 seconds old. A failed refresh, stale quote or invalid price stops signing. Quote freshness is checked again immediately before signing, including after waiting for another treasury submission.

For predictable demo scenarios, explicitly set `SIGNET_DEMO_XRP_USD=0.50` in your `.env`. This mode is labelled `explicit-demo` in quote metadata and receipts. There is no automatic fallback price.

Only native XRP is supported. Amounts must be positive, finite and exactly representable in drops. Unknown assets produce policy refusals.

Spending reservations, run IDs, receipts and returned transaction results persist in `backend/data/signet.sqlite3`; override the path with `SIGNET_STATE_DB`. The instant-tier cap counts successful payments recorded on the current UTC day plus all unresolved reservations. SQLite reserves budget atomically before submission, including across connections. Confirmed failures release reservations; uncertain submissions retain them across restart and midnight.

Human escalation intentionally overrides quantitative caps after fresh integrity checks. It records a local operator action, not an authenticated human signature.

A timeout is an **unknown outcome**, not proof that nothing moved. Inspect the transaction hash through the explorer or `GET /runs/{run_id}` before taking further action. Do not delete the state database or repeat a payment to clear uncertainty. There is no automatic retry or automatic release of uncertain reservations.

Run one backend worker: signer sequence locks, pending approvals and live event history are process-local. A restart expires pending approvals and marks interrupted runs as errors or unknown outcomes without resubmitting them. Spending and receipts survive. SSE IDs replay up to 2,048 recent events while the server is running. Reconnecting browsers also read persistent run snapshots to recover outcomes and pending approval details; browser refresh does not restore scenario tabs.

If the initial request response is lost, **Recover original request** resends the same request ID. The durable ID prevents a second execution. **Check run status** refreshes the existing run without submitting anything. An unknown ledger outcome keeps new runs disabled for that scenario; neither recovery action retries a recorded transaction. Preserve the state database for these guarantees.

## Export and verify receipts

The UI exposes a receipt download, also available at:

```text
GET /runs/{run_id}/receipt
```

Version 1 commits to the exact resolved payment, policy configuration/version, price/source/timestamp, evaluation, recorded agent evidence and any operator approval or rejection. Decimal quantities are canonical strings. The commitment uses domain-separated SHA-256 and is carried in the `signet/payment-receipt/v1` transaction memo; it replaces the original trace-only Merkle root format.

Copy the memo data independently from the ledger, then verify offline:

```sh
# From backend/
uv run python ../scripts/verify_receipt.py receipt.json --memo HEX_FROM_LEDGER
uv run python ../scripts/verify_receipt.py receipt.json --memo HEX_FROM_LEDGER --transaction transaction.json
```

The optional transaction JSON checks the source, destination, native XRP amount and receipt memo. Altering receipt-bound data fails verification. Refused or rejected proposals have downloadable audit receipts but no settlement commitment unless a transaction was actually submitted.

Verification establishes integrity against the supplied anchor. It does not independently establish ledger inclusion, authenticate the operator, prove truthful private model reasoning, or certify regulatory compliance.

## Tests

```sh
# From backend/
uv run pytest -q
```

```sh
# From frontend/
pnpm test
pnpm build
```


## Scope

This is a local testnet demo, not a production custody service. Both signer keys remain in the same backend process, the KYT feed is a mock, and operator endpoints have no authentication. Ledger protection enforces the required signing keys; it does not itself evaluate the off-chain policy or isolate the two signers from a compromised backend.

The original [build brief](signet-demo-brief.md) and pitch deck under `docs/` describe the initial prototype and future concepts. TEE attestation, genuine human co-signatures, real sanctions feeds, RLUSD exchange/trading, selective disclosure proofs and production deployment are not implemented.

```text
backend/      FastAPI, deterministic domain, adapters and offline tests
frontend/     React, TypeScript, Vite and component/state tests
scripts/      explicit wallet setup, top-up, smoke payment and offline verifier
docs/         historical pitch and implementation design/plan
```
