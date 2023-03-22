"""List utils"""

from typing import Iterable, Sequence
from typing_extensions import TypeVar

T = TypeVar("T", infer_variance=True)


def last(value: Iterable[T]):
    """get last from value"""
    if not isinstance(value, Sequence):
        value = list(value)
    return value[-1] if len(value) > 0 else None
