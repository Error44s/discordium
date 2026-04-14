"""Type-safe Discord Snowflake ID wrapper."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Self

# Discord epoch: 2015-01-01T00:00:00Z
_DISCORD_EPOCH = 1_420_070_400_000


class Snowflake:
    """Immutable, hashable Discord Snowflake ID.

    Snowflakes encode a timestamp, worker ID, process ID and increment.
    This wrapper exposes those fields and is usable as a dict key.

    Example::

        sid = Snowflake(175928847299117063)
        print(sid.created_at)  # datetime when the entity was created
        print(int(sid))        # raw int value
    """

    __slots__ = ("_value",)

    def __init__(self, value: int | str) -> None:
        self._value = int(value)

    # Snowflake bit fields

    @property
    def created_at(self) -> datetime:
        """UTC datetime when this snowflake was generated."""
        ms = (self._value >> 22) + _DISCORD_EPOCH
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)

    @property
    def worker_id(self) -> int:
        return (self._value >> 17) & 0x1F

    @property
    def process_id(self) -> int:
        return (self._value >> 12) & 0x1F

    @property
    def increment(self) -> int:
        return self._value & 0xFFF

    # Dunder methods

    def __int__(self) -> int:
        return self._value

    def __str__(self) -> str:
        return str(self._value)

    def __repr__(self) -> str:
        return f"Snowflake({self._value})"

    def __hash__(self) -> int:
        return hash(self._value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Snowflake):
            return self._value == other._value
        if isinstance(other, int):
            return self._value == other
        return NotImplemented

    def __lt__(self, other: Snowflake | int) -> bool:
        if isinstance(other, Snowflake):
            return self._value < other._value
        if isinstance(other, int):
            return self._value < other
        return NotImplemented  # type: ignore[return-value]

    # Constructors

    @classmethod
    def from_datetime(cls, dt: datetime) -> Self:
        """Create a snowflake whose timestamp matches *dt* (useful for pagination)."""
        ms = int(dt.timestamp() * 1000) - _DISCORD_EPOCH
        return cls(ms << 22)
