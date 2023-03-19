"""Search Utils"""

import dataclasses
import datetime
from typing import Sequence
from typing_extensions import SupportsIndex, Self

from reolink_aio.typings import SearchStatus, SearchFile

from .dt import DateTime


@dataclasses.dataclass(frozen=True)
class Status(Sequence[datetime.date]):
    """Status"""

    month: int
    days: tuple[int]
    year: int

    def __getitem__(self, __x: SupportsIndex):
        return datetime.date(self.year, self.month, self.days[__x])

    def __len__(self):
        return len(self.days)

    @classmethod
    def from_json(cls, json: SearchStatus) -> Self:
        """Create value from JSON"""
        return cls(
            month=json.get("mon"),
            days=(i for i, flag in enumerate(json.get("table", "")) if flag == "1"),
            year=json.get("year"),
        )


@dataclasses.dataclass(frozen=True)
class File:
    """File"""

    start_time: DateTime
    end_time: DateTime
    framerate: int
    height: int
    width: int
    name: str
    size: int
    type: str

    @classmethod
    def from_json(cls, json: SearchFile) -> Self:
        """Create value from JSON"""
        if json is None:
            return None
        return File(
            start_time=DateTime.from_json(json.get("StartTime")),
            end_time=DateTime.from_json(json.get("EndTime")),
            framerate=json.get("frameRate"),
            height=json.get("height"),
            width=json.get("width"),
            name=json.get("name"),
            size=json.get("size"),
            type=json.get("type"),
        )
