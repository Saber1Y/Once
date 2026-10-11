"""ACME's order system (fixture): customers, orders, refunds and an async address service.

This is fixture data (see data/world.json), not a real store. The address service
behaves like many real ones: a write returns ``accepted`` and is applied by a
background job, so "accepted" is not the same as "done". An injected fault can
make that job fail, which is how the demo reproduces "confirmed an update after
the write failed".
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import date, timedelta
from pathlib import Path

WORLD_FILE = Path(__file__).parent / "data" / "world.json"

SCHEMA = """
CREATE TABLE customers (id TEXT PRIMARY KEY, name TEXT, email TEXT UNIQUE, plan TEXT,
    customer_since TEXT, address TEXT);
CREATE TABLE orders (id TEXT PRIMARY KEY, customer_id TEXT, product TEXT, amount REAL,
    purchased_at TEXT, shipping_address TEXT, refunded_amount REAL DEFAULT 0,
    credit_amount REAL DEFAULT 0);
CREATE TABLE refunds (id TEXT PRIMARY KEY, order_id TEXT, amount REAL, kind TEXT,
    reason TEXT, created_at TEXT);
CREATE TABLE address_jobs (id TEXT PRIMARY KEY, order_id TEXT, new_address TEXT,
    status TEXT, error TEXT);
CREATE TABLE faults (order_id TEXT, kind TEXT, remaining INTEGER, label TEXT);
"""


class WorldError(Exception):
    pass


class World:
    """One isolated copy of the ACME world. Drift runs each get their own."""

    def __init__(self, path: Path | str = ":memory:", today: date | None = None) -> None:
        self.today = today or date.today()
        self._lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row

    # -- lifecycle -----------------------------------------------------------

    @classmethod
    def seeded(cls, path: Path | str = ":memory:", today: date | None = None) -> World:
        world = cls(path, today)
        world.reset()
        return world

    def reset(self) -> None:
        seed = json.loads(WORLD_FILE.read_text())
        with self._lock:
            cur = self.db.cursor()
            for table in ("customers", "orders", "refunds", "address_jobs", "faults"):
                cur.execute(f"DROP TABLE IF EXISTS {table}")
            cur.executescript(SCHEMA)
            for c in seed["customers"]:
                since = self.today - timedelta(days=c["tenure_days"])
                cur.execute(
                    "INSERT INTO customers VALUES (?,?,?,?,?,?)",
                    (c["id"], c["name"], c["email"], c["plan"], since.isoformat(), c["address"]),
                )
            for o in seed["orders"]:
                purchased = self.today - timedelta(days=o["days_ago"])
                address = cur.execute("SELECT address FROM customers WHERE id=?", (o["customer_id"],)).fetchone()[0]
                cur.execute(
                    "INSERT INTO orders (id, customer_id, product, amount, purchased_at, shipping_address)"
                    " VALUES (?,?,?,?,?,?)",
                    (o["id"], o["customer_id"], o["product"], o["amount"], purchased.isoformat(), address),
                )
            for f in seed["faults"]:
                cur.execute(
                    "INSERT INTO faults VALUES (?,?,?,?)",
                    (f["order_id"], f["kind"], f["times"], f["label"]),
                )
            self.db.commit()

    # -- reads ---------------------------------------------------------------

    def customer(self, *, email: str | None = None, customer_id: str | None = None) -> dict:
        with self._lock:
            if email:
                row = self.db.execute(
                    "SELECT * FROM customers WHERE lower(email)=lower(?)", (email.strip(),)
                ).fetchone()
            else:
                row = self.db.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
        if not row:
            raise WorldError(f"No customer found for {email or customer_id}")
        data = dict(row)
        since = date.fromisoformat(data["customer_since"])
        data["tenure_years"] = round((self.today - since).days / 365.25, 1)
        data["orders"] = [o["id"] for o in self.orders_for(data["id"])]
        return data

    def orders_for(self, customer_id: str) -> list[dict]:
        with self._lock:
            rows = self.db.execute(
                "SELECT * FROM orders WHERE customer_id=? ORDER BY purchased_at DESC", (customer_id,)
            ).fetchall()
        return [self._order_view(dict(r)) for r in rows]

    def order(self, order_id: str) -> dict:
        with self._lock:
            row = self.db.execute("SELECT * FROM orders WHERE id=?", (order_id.strip(),)).fetchone()
        if not row:
            raise WorldError(f"No order found with id {order_id}")
        return self._order_view(dict(row))

    def _order_view(self, data: dict) -> dict:
        purchased = date.fromisoformat(data["purchased_at"])
        data["days_since_purchase"] = (self.today - purchased).days
        return data

    def address_job(self, job_id: str) -> dict:
        with self._lock:
            row = self.db.execute("SELECT * FROM address_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise WorldError(f"No address job {job_id}")
        return dict(row)

    def fault_label(self, order_id: str, kind: str) -> str | None:
        with self._lock:
            row = self.db.execute("SELECT label FROM faults WHERE order_id=? AND kind=?", (order_id, kind)).fetchone()
        return row[0] if row else None

    # -- writes --------------------------------------------------------------

    def refund(self, order_id: str, amount: float, reason: str, kind: str = "refund") -> dict:
        with self._lock:
            order = self.order(order_id)
            already = order["refunded_amount"] + order["credit_amount"]
            if amount <= 0 or amount + already > order["amount"] + 1e-9:
                raise WorldError(
                    f"Refund of {amount:.2f} exceeds the refundable balance "
                    f"{order['amount'] - already:.2f} on {order_id}"
                )
            refund_id = f"R-{uuid.uuid4().hex[:8]}"
            column = "credit_amount" if kind == "store_credit" else "refunded_amount"
            self.db.execute(
                "INSERT INTO refunds VALUES (?,?,?,?,?,?)",
                (refund_id, order_id, amount, kind, reason, self.today.isoformat()),
            )
            self.db.execute(f"UPDATE orders SET {column}={column}+? WHERE id=?", (amount, order_id))
            self.db.commit()
        return {"status": "completed", "refund_id": refund_id, "order_id": order_id, "amount": amount, "kind": kind}

    def request_address_change(self, order_id: str, new_address: str) -> dict:
        """Returns ``accepted``. The background job runs immediately and may fail."""
        with self._lock:
            self.order(order_id)
            job_id = f"J-{uuid.uuid4().hex[:8]}"
            fault = self.db.execute(
                "SELECT remaining FROM faults WHERE order_id=? AND kind='address_write'", (order_id,)
            ).fetchone()
            if fault and fault[0] > 0:
                self.db.execute(
                    "UPDATE faults SET remaining=remaining-1 WHERE order_id=? AND kind='address_write'",
                    (order_id,),
                )
                status, error = "failed", "address-service: upstream geocoder timeout"
            else:
                self.db.execute("UPDATE orders SET shipping_address=? WHERE id=?", (new_address, order_id))
                status, error = "done", None
            self.db.execute(
                "INSERT INTO address_jobs VALUES (?,?,?,?,?)",
                (job_id, order_id, new_address, status, error),
            )
            self.db.commit()
        return {"status": "accepted", "job_id": job_id, "order_id": order_id}
