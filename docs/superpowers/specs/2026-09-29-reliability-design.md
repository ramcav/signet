# Signet reliability and verifiable receipts

The user approved all findings in the repository review and requested local commits only.

## Scope and architecture

Keep the FastAPI/domain/adapter split and React UI. Strengthen the actual payment path instead of adding deployment or user-account infrastructure.

- Validate native XRP amounts and supported assets before policy evaluation. Quotes have a source, UTC timestamp and expiry; live quote failures stop signing. A fixed demo quote must be explicitly configured.
- Require the treasury's validated signer list to contain the two intended signers, disable master-key authorization and reject regular-key bypasses. Wallet setup persists keys before account configuration and supports explicit migration of existing wallets. No live wallet operations are needed to implement or test these changes.
- Reserve spending atomically in SQLite before submission. Count current UTC-day spending plus all unresolved reservations; persist them across restarts. Confirmed successful transactions commit reservations, confirmed failures release them, and uncertain submissions keep them. Human-approved escalation retains its documented ability to override quantitative caps.
- Commit a versioned canonical receipt to the resolved intent, policy snapshot, quote, decision, trace and approval action. Export receipts and verify them offline against an independently supplied memo and optionally a transaction. This attests to recorded data, not truthful model reasoning or an authenticated human identity.
- Use explicit run completion/error events and ledger outcomes. The browser establishes its run ID before submitting, rejects stale events and displays failures. Stream replay covers temporary disconnects in the running server. Approval HTTP failures cannot appear successful.
- Add offline integration tests, frontend tests, CI and contribution instructions. Preserve the demo's appearance while fixing responsive and keyboard interaction defects.

## Boundaries

The demo remains local/testnet-only, with both signer keys in one process, mock KYT and unauthenticated operator actions. It is not a production custody service. Unknown transaction outcomes are never automatically retried or cleared from the budget. Existing wallet protection is changed only by the explicit setup command, not application startup.

## Acceptance

Regression tests reproduce the reviewed failures before fixes. The final backend suite and frontend tests/build pass without live OpenAI, pricing or XRPL calls. Independent review checks the authorization, accounting and receipt boundaries. Only local Git commits are created; no push is performed.
