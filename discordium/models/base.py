"""Lightweight base for all Discord data models.

Every model is a frozen slotted dataclass — immutable, memory-efficient,
and trivially serialisable. Mutation returns a *new* instance via `evolve()`.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Self, dataclass_transform


@dataclass_transform(frozen_default=True)
class _ModelMeta(type):
    """Metaclass that auto-wraps subclasses with @dataclass(frozen=True, slots=True)."""

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> _ModelMeta:
        cls = super().__new__(mcs, name, bases, namespace)
        if name == "Model":
            return cls  # skip the base itself
        # Avoid double-application: Python 3.12 slots=True rebuilds the class
        # via type(cls)(...) which re-triggers __new__
        if dataclasses.fields(cls) if hasattr(cls, "__dataclass_fields__") else None:
            return cls  # type: ignore[return-value]
        return dataclasses.dataclass(frozen=True, slots=True, kw_only=True)(cls)  # type: ignore[return-value]


class Model(metaclass=_ModelMeta):
    """Base class for all discordium data models.

    Subclasses are automatically frozen slotted dataclasses::

        class User(Model):
            id: Snowflake
            username: str
            avatar: str | None = None

    Instances are immutable. Use ``evolve()`` to derive a modified copy.
    """

    def evolve(self, **changes: Any) -> Self:
        """Return a shallow copy with *changes* applied."""
        return dataclasses.replace(self, **changes)  # type: ignore[type-var]

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (recursively)."""
        result: dict[str, Any] = {}
        for f in dataclasses.fields(self):  # type: ignore[arg-type]
            val = getattr(self, f.name)
            if isinstance(val, Model):
                val = val.to_dict()
            elif isinstance(val, list):
                val = [v.to_dict() if isinstance(v, Model) else v for v in val]
            result[f.name] = val
        return result

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        """Construct from a raw Discord API payload.

        Unknown keys are silently dropped so forward-compat is painless.
        """
        fields = {f.name for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
        filtered = {k: v for k, v in data.items() if k in fields}
        return cls(**filtered)
