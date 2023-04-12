"""Search helpers"""

import dataclasses
import datetime
from enum import Enum, IntFlag, auto
import struct
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    Final,
    Mapping,
    Sequence,
)
from typing_extensions import SupportsIndex, TypeVar

from homeassistant.core import HomeAssistant, callback

from reolink_aio.api import Host

from ..const import DOMAIN
from . import async_get_reolink_data

from ..util.dataclasses import unpack_from_json
from ..util import dt

if TYPE_CHECKING:
    from typing import cast

T = TypeVar("T", infer_variance=True)


def _days_table(table: str):
    return tuple(i for i, flag in enumerate(table, start=1) if flag == "1")


@dataclasses.dataclass(frozen=True, slots=True, order=True)
class SearchStatus(dt.YearMonth, Sequence[datetime.date]):
    """Search Status"""

    days: tuple[int, ...] = dataclasses.field(
        default_factory=tuple, metadata={"json": "table", "transform": _days_table}
    )

    def __getitem__(self, __index: SupportsIndex):
        return self.date(self.days[__index])

    def __len__(self):
        return len(self.days)

    def __contains__(self, value: object):
        if not isinstance(value, (dt.YearMonth, datetime.date)):
            return isinstance(value, int) and value in self.days
        if self.year != value.year or self.month != value.month:
            return False
        if not isinstance(value, datetime.date):
            if isinstance(value, SearchStatus):
                return value == self or set(value.days).issubset(self.days)
            return False
        return value.day in self.days

    def __iter__(self):
        for day in self.days:
            yield self.date(day)


class Triggers(IntFlag):
    NONE = 0
    MOTION = auto()
    TIMER = auto()
    PERSION = auto()
    VEHICLE = auto()
    PET = auto()


@dataclasses.dataclass(frozen=True, slots=True)
class SearchFile:
    """Search File"""

    name: str
    frame_rate: int = dataclasses.field(metadata={"json": "frameRate"})
    trigger: Triggers = dataclasses.field(default=Triggers.NONE, init=False)
    width: int
    height: int
    size: int
    type: str

    # pylint: disable=invalid-name
    def __post_init__(self):
        (*_path, file) = self.name.split("/")
        (file, _ext) = file.split(".", 2)
        (_name, _start_date, _start_time, _end_time, *parts) = file.split("_")
        (a, b, c) = (int(p, 16) for p in parts[0][4:])
        trigger = self.trigger
        if a & 8 == 8 or c & 8 == 8:
            trigger |= Triggers.MOTION
        if a & 4 == 4:
            trigger |= Triggers.PERSION
        if b & 1 == 1:
            trigger |= Triggers.TIMER
        if b & 4 == 4:
            trigger |= Triggers.PET
        object.__setattr__(self, "trigger", trigger)

    @classmethod
    def from_json(cls, json: Mapping[str, any] = None, /, **kwargs: any):
        """from json"""
        return unpack_from_json(cls, json, **kwargs)


class StreamTypes(Enum):
    """Stream Types"""

    MAIN = auto()
    SUB = auto()
    EXT = auto()


_API_STREAM_MAP: Final = {
    StreamTypes.MAIN: "main",
    StreamTypes.SUB: "sub",
    StreamTypes.EXT: "ext",
}


@dataclasses.dataclass(frozen=True, slots=True)
class SearchResult:
    """Search Result"""

    _stream: dict[StreamTypes, SearchFile] = dataclasses.field(
        default_factory=dict, init=False
    )
    stream: Mapping[StreamTypes, SearchFile] = dataclasses.field(init=False)
    start: datetime.datetime = dataclasses.field(
        metadata={"json": "StartTime", "transform": dt.from_json}
    )
    end: datetime.datetime = dataclasses.field(
        metadata={"json": "EndTime", "transform": dt.from_json}
    )
    tzinfo: dataclasses.InitVar[datetime.timezone] = dataclasses.field(
        default=None, kw_only=True
    )

    # pylint: disable = invalid-name
    def __post_init__(
        self,
        tzinfo: datetime.timezone = None,
    ):
        object.__setattr__(self, "stream", MappingProxyType(self._stream))
        if tzinfo is not None:
            if self.start.tzinfo != tzinfo:
                object.__setattr__(self, "start", self.start.replace(tzinfo=tzinfo))
            if self.end.tzinfo != tzinfo:
                object.__setattr__(self, "end", self.end.replace(tzinfo=tzinfo))

    @property
    def best_stream(self):
        return self._stream.get(
            StreamTypes.MAIN,
            self._stream.get(StreamTypes.SUB, self._stream.get(StreamTypes.EXT)),
        )

    @classmethod
    def from_json(
        cls,
        json: Mapping[str, any] = None,
        /,
        *,
        tzinfo: datetime.tzinfo = None,
        **kwargs: any,
    ):
        """from json"""
        if tzinfo is not None:
            kwargs["tzinfo"] = tzinfo
        return unpack_from_json(cls, json, **kwargs)


class SearchCache(Mapping[datetime.datetime, SearchResult]):
    """Reolink Search Cache"""

    def __init__(
        self, host: Host, entry_id: str, channel=0, /, unique_id: str | None = None
    ):
        self._host = host
        self._entry_id = entry_id
        self._channel = channel
        self._unique_id = unique_id
        self._statuses: dict[dt.YearMonth, SearchStatus] = {}
        self._statuses_min = dt.YearMonth.max
        self._statuses_max = dt.YearMonth.min
        self._hard_start = dt.YearMonth.min

        self._files: dict[datetime.datetime, SearchResult] = {}
        self._files_by_day: dict[datetime.date, list[datetime.datetime]] = {}
        self._files_min = datetime.datetime.max
        self._files_max = datetime.datetime.min

    def __getitem__(self, __key: datetime.datetime):
        return self._files.__getitem__(__key)

    def __iter__(self):
        return self._files.__iter__()

    def __len__(self):
        return self._files.__len__()

    def keys(self):
        return self._files.keys()

    def values(self):
        return self._files.values()

    def items(self):
        return self._files.items()

    def timezone(self) -> dt.Timezone:
        """Camera Timezone"""
        # pylint: disable=protected-access
        return dt.Timezone.get(**self._host._time_settings)

    def today(self):
        """ "today" of the camera"""
        # pylint: disable=protected-access
        return datetime.date.fromtimestamp(
            datetime.datetime.utcnow().timestamp()
            + self._host._subscription_time_difference
        )

    @property
    def last(self):
        """the most recent file in cache"""
        return self._files_max

    async def _async_host_search(
        self,
        start: datetime.date,
        end: datetime.date | None = None,
        stream=StreamTypes.MAIN,
        status_only=False,
    ):
        if isinstance(start, datetime.datetime) and start.tzinfo is not None:
            start = start.astimezone(self.timezone())
        if end is None:
            end = dt.date(start)
        if not isinstance(start, datetime.datetime):
            start = datetime.datetime.combine(start, datetime.time.min)

        if not isinstance(end, datetime.datetime):
            end = datetime.datetime.combine(end, datetime.time.max)
        elif end.tzinfo is not None:
            end = end.astimezone(self.timezone())

        (statuses, files) = await self._host.request_vod_files(
            self._channel, start, end, status_only, _API_STREAM_MAP[stream]
        )
        if statuses is None:
            return False
        for status in statuses:
            _status = SearchStatus.from_json(status)
            key = dt.YearMonth(_status.year, _status.month)
            self._statuses_min = min(self._statuses_min, key)
            self._statuses_max = max(self._statuses_max, key)
            self._statuses[key] = _status
        if files is None:
            return True
        needs_sort: list[list] = []
        for file in files:
            key = dt.from_json(file["StartTime"])
            self._files_min = min(self._files_min, key)
            self._files_max = max(self._files_max, key)
            if (_file := self._files.get(key)) is None:
                result = SearchResult.from_json(file, tzinfo=self.timezone())
                _file = self._files.setdefault(key, result)
                if _file == result:
                    by_day = self._files_by_day.setdefault(key.date(), [])
                    by_day.append(key)
                    if by_day not in needs_sort:
                        needs_sort.append(by_day)
            # pylint: disable = protected-access
            _file._stream[stream] = SearchFile.from_json(file)
        for item in needs_sort:
            item.sort()

    async def async_find_start(self):
        """Update the cache status backwards to find start range"""
        month = self._statuses_min
        if month > self._statuses_max:
            today = self.today()
            month = dt.YearMonth(today.year, today.month)

        while self._hard_start != month:
            await self._async_host_search(
                month.to_date(1),
                month.next().to_date(1) - datetime.timedelta(days=1),
                status_only=True,
            )
            if self._hard_start != month:
                month = month.prev()

        # return SearchRange(self._statuses, self._status_range)

    async def async_update(self):
        """Update cache to most recent events"""
        if not await self._async_host_search(self.today()):
            # no files this month? is it bad or missing storage?
            return
        if self._hard_start == self._statuses_min:
            while (
                not await self._async_host_search(
                    self._hard_start.date(), status_only=True
                )
                and self._statuses_min < self._statuses_max
            ):
                self._statuses_min = self._statuses_min.prev()
                self._hard_start = self._statuses_min

    async def async_search(
        self, start: datetime.date, end: datetime.date | None = None
    ):
        """Search for videos in range"""
        if start < self._hard_start.date():
            start = self._hard_start.date()
        today = datetime.datetime(self.today(), datetime.time.max)
        if end is None or end > today:
            end = today
        if start < self._files_min:
            if start >= self._statuses_min.date():
                status_key = self._statuses_min
                near = None
                while near is None and status_key in self._statuses:
                    status = self._statuses[status_key]
                    last_date = None
                    for date in status:
                        if date >= start:
                            if last_date is None:
                                near = date
                            else:
                                near = last_date
                            break
                        last_date = date
                if near is not None:
                    start = near
            await self._async_host_search(start, self._files_min)
        if end > self._files_max:
            await self._async_host_search(self._files_max, end)
        for date in dt.DateRange(start, end):
            if TYPE_CHECKING:
                date = cast(dt.DateRangeType, date)
            time = None
            if isinstance(date, tuple):
                time: tuple[datetime.time, datetime.time]
                (date, *time) = date

            if (
                (status := self._statuses.get(dt.YearMonth(date.year, date.month)))
                is not None
                and date in status
                and (files := self._files_by_day.get(date))
            ):
                for start in files:
                    if (time is None or (time[0] <= start.time() <= time[1])) and (
                        file := self._files.get(start)
                    ):
                        yield file


@callback
def async_get_search_cache(hass: HomeAssistant, entry_id: str, channel=0):
    """Get search cache for reolink camera/channel"""

    domain_data: dict[str, dict[str, any]] = hass.data[DOMAIN]
    if (
        entry := hass.config_entries.async_get_entry(entry_id)
    ) is None or entry.disabled_by:
        raise KeyError("Missing/Disabled entry specified")

    search_data = domain_data.setdefault("search", {})

    entry_data: dict[int, SearchCache] = {}
    new_entry_data = entry_data
    if (
        entry_data := search_data.setdefault(entry_id, new_entry_data)
    ) is new_entry_data:
        # we want to cleanup if the entry gets unloaded so we dont hang
        # on to references
        def unload():
            del domain_data[entry_id]

        entry.async_on_unload(unload)

    data = async_get_reolink_data(hass, entry_id)
    return entry_data.setdefault(
        channel,
        SearchCache(data.host.api, entry_id, channel, unique_id=data.host.unique_id),
    )
