from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeterministicHashEmbedder:
    dimension: int = 1024

    def __post_init__(self) -> None:
        if self.dimension < 1:
            raise ValueError("dimension must be positive")

    def embed(self, text: str) -> Sequence[float]:
        if not text:
            raise ValueError("text must not be empty")
        digest = hashlib.shake_256(text.encode("utf-8")).digest(self.dimension)
        vector = tuple((value - 127.5) / 127.5 for value in digest)
        if not any(math.isfinite(value) for value in vector):
            raise ValueError("deterministic embedding produced invalid values")
        return vector
