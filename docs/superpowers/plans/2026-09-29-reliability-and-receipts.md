# Reliability and receipts implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development and TDD. The user has authorized this scope and local commits. Do not push.

**Goal:** Make the demonstrated policy-to-ledger guarantees testable, recoverable and independently verifiable.

**Architecture:** Retain the pure domain layer. Add a small SQLite audit/reservation adapter, dependency-injected application wiring and explicit event outcomes. Divide edits by ownership so frontend, wallet and domain work can proceed independently.

**Tech Stack:** Python 3.11+, FastAPI, sqlite3, xrpl-py, pytest; React, TypeScript, Vitest, Vite.

## Tasks

- [x] Domain: regression tests for unknown assets and invalid amounts; validate before valuation, support XRP consistently, validate quote freshness/provenance, and replace the assertion-free escalation test. Files: domain/intent.py, policy.py, adapters/agent.py, prices.py, config/policy.yaml and domain/quote tests.
- [x] Receipts: canonical versioned schema, resolved payment/policy/quote/approval binding, portable verifier and tampering tests. Files: domain/receipt.py, scripts/verify_receipt.py and test_receipts.py. Integration uses build_receipt(...), receipt.root, receipt.to_dict(), and verify_receipt(document, memo_hex, transaction=None).
- [x] Wallets: mocked protection audit tests, resumable key persistence, explicit protection migration and truthful result classification. Files: adapters/xrpl_adapter.py, wallet setup scripts and wallet tests. Application calls assert_protected() and reads TxResult.outcome.
- [x] Application: tests for concurrent reservations, UTC rollover, restart persistence, failed/unknown submissions, approval failure and idempotency. Implement SQLite audit store, reservation lifecycle, receipt export and injected services. Files: adapters/audit_store.py, application/use_cases.py, api/app.py and application/API tests.
- [x] Events: explicit run.completed/run.error, replay IDs, bounded nonblocking subscriber handling. Test replay and disconnected/slow clients. Files: application/events.py and test_events.py.
- [x] Frontend: failing reducer/HTTP tests; implement failure states, client-established run IDs, stale-event filtering, truthful ledger views and receipt download. Add connection/replay handling, responsive layout and keyboard/reduced-motion support. Files: frontend/src and frontend test/package configuration.
- [x] Tooling/docs: CI backend tests plus frontend tests/build, CONTRIBUTING.md, accurate README security/setup/receipt instructions, local runtime ignores and explicit direct dependencies.
- [x] Integrate, review and verify. Run `backend/.venv/Scripts/python.exe -m pytest -q` in backend (using the equivalent relative executable there), `pnpm test` and `pnpm build` in frontend. Review all diffs and ensure no generated keys or local data are staged. Commit cohesive changes locally; inspect final Git status and log.

## Regression criteria

Two concurrent $250 payments with $99,600 already spent cannot both consume a $100,000 instant-tier budget. Restart and UTC midnight do not erase unresolved reservations. A validated non-success result does not count as a successful payment. Unknown assets yield a structured refusal. NaN, infinity, booleans and sub-drop XRP cannot reach signing. A run.error stops the UI spinner; HTTP 404/500 cannot approve an escalation; old run events cannot replace the active run. Changing any receipt-bound payment, policy or quote value breaks verification. Protection auditing rejects an enabled master key, a regular key or an unexpected signer list.
