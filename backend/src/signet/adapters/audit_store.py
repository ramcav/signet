"""Durable local audit data and atomic UTC-day spending reservations."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable


class AuditStore:
    def __init__(self, path: str | Path = ":memory:", *, clock: Callable[[], datetime] | None = None):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS reservations (
                run_id TEXT PRIMARY KEY, account TEXT NOT NULL, day TEXT NOT NULL,
                amount TEXT NOT NULL, status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, request TEXT NOT NULL, status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS receipts (
                run_id TEXT PRIMARY KEY, document TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transactions (
                run_id TEXT PRIMARY KEY, result TEXT NOT NULL
            );
        """)

    def _day(self) -> str:
        return self._clock().astimezone(timezone.utc).date().isoformat()

    def _used(self, account: str) -> Decimal:
        rows = self._db.execute(
            "SELECT amount FROM reservations WHERE account=? AND "
            "(status IN ('reserved','unknown') OR (status='success' AND day=?))",
            (account, self._day()),
        )
        return sum((Decimal(row["amount"]) for row in rows), Decimal(0))

    def used(self, account: str) -> Decimal:
        with self._lock:
            return self._used(account)

    def reserve(self, account: str, run_id: str, amount, cap, *, override: bool = False) -> bool:
        amount, cap = Decimal(str(amount)), Decimal(str(cap))
        if not amount.is_finite() or amount <= 0 or not cap.is_finite() or cap <= 0:
            raise ValueError("reservation amount and cap must be finite and positive")
        with self._lock, self._db:
            # Covers independent processes/connections, not only asyncio tasks.
            self._db.execute("BEGIN IMMEDIATE")
            prior = self._db.execute("SELECT * FROM reservations WHERE run_id=?", (run_id,)).fetchone()
            if prior:
                if prior["account"] != account or Decimal(prior["amount"]) != amount:
                    raise ValueError("reservation ID already used for another payment")
                # Never authorize a second submission for an existing reservation.
                return False
            if not override and self._used(account) + amount > cap:
                return False
            self._db.execute(
                "INSERT INTO reservations VALUES (?,?,?,?,?)",
                (run_id, account, self._day(), str(amount), "reserved"),
            )
            return True

    def resolve(self, run_id: str, outcome: str) -> None:
        if outcome not in {"success", "rejected", "failed", "unknown"}:
            raise ValueError("invalid transaction outcome")
        with self._lock, self._db:
            # Only unresolved entries may transition; duplicate callbacks cannot
            # turn a successful payment into a released reservation.
            self._db.execute(
                "UPDATE reservations SET status=?, day=CASE WHEN ?='success' THEN ? ELSE day END "
                "WHERE run_id=? AND status IN ('reserved','unknown')",
                (outcome, outcome, self._day(), run_id),
            )

    def get_reservation(self, run_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM reservations WHERE run_id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    def accept_run(self, run_id: str, request: dict) -> bool:
        body = json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._lock, self._db:
            self._db.execute("BEGIN IMMEDIATE")
            previous = self._db.execute("SELECT request FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if previous:
                if previous["request"] != body:
                    raise ValueError("run ID already used for a different request")
                return False
            self._db.execute("INSERT INTO runs VALUES (?,?,?)", (run_id, body, "accepted"))
            return True

    def finish_run(self, run_id: str, status: str) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE runs SET status=? WHERE run_id=?", (status, run_id))

    def recover_interrupted_runs(self) -> list[dict]:
        """Single-worker startup recovery; never resume or retry a payment."""
        recovered = []
        with self._lock, self._db:
            self._db.execute("BEGIN IMMEDIATE")
            rows = self._db.execute(
                "SELECT runs.run_id, reservations.status AS payment_status "
                "FROM runs LEFT JOIN reservations USING (run_id) "
                "WHERE runs.status IN ('accepted','escalate')"
            ).fetchall()
            for row in rows:
                payment_status = row["payment_status"]
                status = ("unknown" if payment_status in {"reserved", "unknown"}
                          else payment_status or "error")
                self._db.execute("UPDATE runs SET status=? WHERE run_id=?", (status, row["run_id"]))
                self._db.execute("UPDATE reservations SET status='unknown' WHERE run_id=? AND status='reserved'", (row["run_id"],))
                recovered.append({"run_id": row["run_id"], "status": status})
        return recovered

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT run_id,status FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            tx = self._db.execute("SELECT result FROM transactions WHERE run_id=?", (run_id,)).fetchone()
            result["tx"] = json.loads(tx["result"]) if tx else None
            return result

    def save_transaction(self, run_id: str, result: dict) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO transactions VALUES (?,?)",
                             (run_id, json.dumps(result, allow_nan=False)))

    def save_receipt(self, run_id: str, document: dict) -> None:
        encoded = json.dumps(document, sort_keys=True, allow_nan=False)
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO receipts VALUES (?,?)", (run_id, encoded))

    def get_receipt(self, run_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT document FROM receipts WHERE run_id=?", (run_id,)).fetchone()
            return json.loads(row["document"]) if row else None

    def close(self) -> None:
        with self._lock:
            self._db.close()
