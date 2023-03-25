"""Search helpers"""

import datetime
from typing import (
    TYPE_CHECKING,
    Generic,
    Mapping,
)

if TYPE_CHECKING:
    from typing import cast
from typing_extensions import SupportsIndex, TypeVar, NamedTuple
from homeassistant.core import HomeAssistant, callback

from reolink_aio import typings
from reolink_aio.api import Host

from ..const import DOMAIN
from . import async_get_reolink_data


from ..util import dt

T = TypeVar("T", infer_variance=True)


class SimpleRange(NamedTuple, Generic[T]):
    """Simple Range"""

    start: T
    end: T


class YearMonth(NamedTuple):
    """Year and Month"""

    year: int
    month: int

    @staticmethod
    def from_date(value: datetime.date):
        """from date"""
        return YearMonth(value.year, value.month)

    def to_date(self, day=1):
        """to date"""
        return datetime.date(self.year, self.month, day)


class SearchStatus(dt.DateRange):
    """Search Status"""

    def __init__(self, status: typings.SearchStatus):
        start = datetime.date(status["year"], status["mon"], 1)
        end = datetime.date(*(dt.nextmonth(start.year, start.month) + (1,)))
        super().__init__(start, end)
        self._days = tuple(
            i for i, flag in enumerate(status["table"], start=1) if flag == "1"
        )

    def __contains__(self, value: object):
        if not isinstance(value, datetime.date):
            if isinstance(value, int):
                return value in self._days
            return False
        return self.start <= value < self.stop and value.day in self._days

    def __getitem__(self, __index: SupportsIndex):
        return self._start + datetime.timedelta(days=self._days[__index] - 1)

    def __len__(self):
        return len(self._days)


class SearchFileInfo(NamedTuple):
    """Search File Info"""

    frame_rate: int
    width: int
    height: int
    size: int
    type: str

    @staticmethod
    def from_json(json: typings.SearchFile):
        """from json"""

        return SearchFileInfo(
            json.get("frameRate"),
            json.get("width"),
            json.get("height"),
            json.get("size"),
            json.get("type"),
        )


class SearchFile(NamedTuple):
    """Search File"""

    name: str
    start: datetime.datetime
    info: SearchFileInfo
    end: datetime.datetime

    @staticmethod
    def from_json(json: typings.SearchFile, tzinfo: datetime.timezone | None = None):
        """from json"""

        return SearchFile(
            json.get("name"),
            dt.json_to_datetime(json.get("StartTime"), tzinfo),
            SearchFileInfo.from_json(json),
            dt.json_to_datetime(json.get("EndTime"), tzinfo),
        )


class SearchCache(Mapping[datetime.datetime, SearchFile]):
    """Reolink Search Cache"""

    def __init__(
        self, host: Host, entry_id: str, channel=0, /, unique_id: str | None = None
    ):
        self._host = host
        self._entry_id = entry_id
        self._channel = channel
        self._unique_id = unique_id
        self._statuses: dict[YearMonth, SearchStatus] = {}
        self._hard_start = YearMonth(-9999, -13)
        self._status_range = SimpleRange(
            YearMonth(-self._hard_start.year, -self._hard_start.month), self._hard_start
        )
        self._files: dict[datetime.datetime, SearchFile] = {}
        self._files_by_day: dict[datetime.date, list[datetime.datetime]] = {}
        self._file_range = SimpleRange(datetime.datetime.max, datetime.datetime.min)

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

    @property
    def min(self):
        """minimum possible date loaded"""
        return self._status_range.start.to_date()

    @property
    def max(self):
        """maximum possible date loaded"""
        return datetime.date(
            *(dt.nextmonth(*self._status_range.end) + (1,))
        ) + datetime.timedelta(days=-1)

    @property
    def start(self):
        """first video start loaded"""
        return self._file_range.start

    @property
    def end(self):
        """last video start loaded"""
        return self._file_range.end

    @property
    def _timezone(self) -> dt.Timezone:
        return dt.Timezone.get(**self._host._time_settings)

    def today(self):
        """ "today" of the camera"""
        return datetime.date.fromtimestamp(
            datetime.datetime.utcnow().timestamp()
            + self._host._subscription_time_difference
        )

    async def _async_host_search(
        self,
        start: datetime.date,
        end: datetime.date | None = None,
        stream: str = None,
        status_only=False,
    ):
        if isinstance(start, datetime.datetime) and start.tzinfo is not None:
            start = start.astimezone(self._timezone)
        if end is None:
            end = dt.date(start)
        if not isinstance(start, datetime.datetime):
            start = datetime.datetime.combine(start, datetime.time.min)

        if not isinstance(end, datetime.datetime):
            end = datetime.datetime.combine(end, datetime.time.max)
        elif end.tzinfo is not None:
            end = end.astimezone(self._timezone)

        (statuses, files) = await self._host.request_vod_files(
            self._channel, start, end, status_only, stream
        )
        if statuses is None:
            return False
        (low, high) = self._status_range
        for status in statuses:
            key = YearMonth(status["year"], status["mon"])
            if key < low:
                low = key
            if key > high:
                high = key
            self._statuses[key] = SearchStatus(status)
        self._status_range = SimpleRange(low, high)
        if files is None:
            return True
        (low, high) = self._file_range
        needs_sort: set[list] = set()
        for file in files:
            key = dt.json_to_datetime(file["StartTime"])
            if key < low:
                low = key
            if key > high:
                high = key
            self._files[key] = SearchFile.from_json(file, self._timezone)
            by_day = self._files_by_day.setdefault(key.date(), [])
            by_day.append(key)
            needs_sort.add(by_day)
        self._file_range = SimpleRange(low, high)
        for item in needs_sort:
            item.sort()

    async def async_update(self):
        """Update cache to most recent events"""
        if not await self._async_host_search(self.today()):
            # no files this month? is it bad or missing storage?
            return
        if self._status_range.start == self._hard_start:
            while (
                not await self._async_host_search(self._hard_start.to_date())
                and self._status_range.start < self._status_range.end
            ):
                self._status_range = SimpleRange(
                    YearMonth(*dt.nextmonth(*self._status_range.start)),
                    self._status_range.end,
                )
                self._hard_start = self._status_range.start

    async def async_search(
        self, start: datetime.date, end: datetime.date | None = None
    ):
        """Search for videos in range"""
        if start < self._hard_start.to_date():
            start = self._hard_start.to_date()
        today = datetime.datetime(self.today(), datetime.time.max)
        if end is None or end > today:
            end = today
        if start < self._file_range.start:
            if start >= self._status_range.start.to_date():
                status_key = self._status_range.start
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
            await self._async_host_search(start, self._file_range.start)
        if end > self._file_range.end:
            await self._async_host_search(self._file_range.end, end)
        for date in dt.DateRange(start, end):
            if TYPE_CHECKING:
                date = cast(dt.DateRangeType, date)
            time = None
            if isinstance(date, tuple):
                time: tuple[datetime.time, datetime.time]
                (date, *time) = date

            if (
                (status := self._statuses.get(YearMonth(date.year, date.month)))
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
    entry_data = domain_data.setdefault(entry_id, {})
    search_data: dict[int, SearchCache] = entry_data.setdefault("search", {})
    data = async_get_reolink_data(hass, entry_id)
    return search_data.setdefault(
        channel,
        SearchCache(data.host.api, entry_id, channel, unique_id=data.host.unique_id),
    )
