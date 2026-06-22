"""Built-in sample payloads used by ``tokentrim perf`` to demonstrate savings."""

from __future__ import annotations

import json

_RECORDS = [
    {
        "id": i,
        "user": f"user_{i}@example.com",
        "status": "ok" if i % 7 else "error",
        "latency_ms": 40 + (i % 13),
        "region": ["us-east-1", "us-west-2", "eu-west-1"][i % 3],
        "retries": i % 3,
    }
    for i in range(180)
]

JSON_SAMPLE = json.dumps(_RECORDS, indent=2)

LOG_SAMPLE = "\n".join(
    [f"2026-06-20T10:{m:02d}:{s:02d} INFO  worker heartbeat ok shard={s % 4} lag=12ms" for m in range(5) for s in range(0, 60, 5)]
    + [
        "2026-06-20T10:05:13 ERROR  db connection refused host=10.0.2.4 port=5432",
        "2026-06-20T10:05:13 FATAL  worker crashed: ConnectionError after 5 retries",
    ]
    + [f"2026-06-20T10:06:{s:02d} INFO  worker heartbeat ok shard={s % 4} lag=11ms" for s in range(0, 60, 5)]
)

CODE_SAMPLE = '''\
import os
from typing import Optional


class PaymentProcessor:
    """Charges cards and records transactions."""

    def __init__(self, gateway, ledger):
        self.gateway = gateway
        self.ledger = ledger
        self._cache = {}

    def charge(self, customer_id: str, amount_cents: int) -> Optional[str]:
        """Charge a customer and return a transaction id."""
        if amount_cents <= 0:
            raise ValueError("amount must be positive")
        token = self.gateway.tokenize(customer_id)
        result = self.gateway.charge(token, amount_cents)
        if result.ok:
            self.ledger.record(customer_id, amount_cents, result.txn_id)
            return result.txn_id
        return None

    def refund(self, txn_id: str) -> bool:
        record = self.ledger.lookup(txn_id)
        if not record:
            return False
        return self.gateway.refund(txn_id, record.amount_cents).ok
'''

TEXT_SAMPLE = (
    "The deployment pipeline runs in three stages. First, the build stage compiles "
    "the service and produces a container image tagged with the commit SHA. This "
    "stage is mostly mechanical and rarely fails. Second, the test stage runs the "
    "unit and integration suites against an ephemeral database. The integration "
    "suite is the slowest part and accounts for roughly seventy percent of total "
    "pipeline time. It is important that the integration suite never shares state "
    "between test cases, because flaky state leakage was the root cause of last "
    "quarter's release incident. Third, the deploy stage promotes the image to "
    "staging, runs smoke tests, and then promotes to production behind a feature "
    "flag. Operators should note that the production promotion is gated on a manual "
    "approval, and that approval must come from someone other than the commit "
    "author. If smoke tests fail, the pipeline automatically rolls back to the "
    "previous image and pages the on-call engineer."
) * 3


SAMPLES = {
    "json": JSON_SAMPLE,
    "log": LOG_SAMPLE,
    "code": CODE_SAMPLE,
    "text": TEXT_SAMPLE,
}
