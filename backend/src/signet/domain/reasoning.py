"""ReasoningTrace + MerkleCommit — canonical commitment to agent reasoning."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Sequence


def _h(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


@dataclass(frozen=True)
class MerkleCommit:
    root: str
    leaves: tuple[str, ...]

    @classmethod
    def from_steps(cls, steps: Sequence[str]) -> "MerkleCommit":
        if not steps:
            raise ValueError("cannot commit empty trace")
        leaves = [_h(s.encode("utf-8")) for s in steps]
        level = list(leaves)
        while len(level) > 1:
            if len(level) % 2 == 1:
                level.append(level[-1])
            level = [_h(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
        return cls(root=level[0].hex(), leaves=tuple(leaf.hex() for leaf in leaves))


@dataclass(frozen=True)
class ReasoningTrace:
    steps: tuple[str, ...] = field(default_factory=tuple)

    def append(self, step: str) -> "ReasoningTrace":
        return ReasoningTrace(steps=self.steps + (step,))

    def commit(self) -> MerkleCommit:
        return MerkleCommit.from_steps(self.steps)
