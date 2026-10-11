"""Step ledger: a structured copy of what each attempt did.

Every entry here is also a neatlogs span (tools are decorated with
``@neatlogs.span``). The checker reads the ledger so its verdicts can cite exact
steps, and the console shows those steps to Maya as evidence.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Step:
    id: str
    kind: str  # "tool" | "source" | "commit" | "verify" | "llm"
    name: str
    args: dict[str, Any]
    result: Any
    ok: bool
    started_at: float
    duration_ms: int

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "args": self.args,
            "result": self.result,
            "ok": self.ok,
            "duration_ms": self.duration_ms,
        }


@dataclass
class Ledger:
    prefix: str
    steps: list[Step] = field(default_factory=list)
    elapsed_ms: int = 0

    def record(self, kind: str, name: str, args: dict, fn) -> Any:
        started = time.time()
        ok = True
        try:
            result = fn()
        except Exception as exc:  # tool errors are data for the agent, not crashes
            ok = False
            result = {"error": str(exc)}
        self.steps.append(
            Step(
                id=f"{self.prefix}.{len(self.steps) + 1}",
                kind=kind,
                name=name,
                args=args,
                result=result,
                ok=ok,
                started_at=started,
                duration_ms=int((time.time() - started) * 1000),
            )
        )
        return result

    def last(self) -> Step:
        return self.steps[-1]

    def find(self, name: str) -> list[Step]:
        return [s for s in self.steps if s.name == name]
