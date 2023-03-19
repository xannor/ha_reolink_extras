"""DateTime Utilities"""

import dataclasses
import datetime
from typing import ClassVar, Final, Sequence, TypedDict, overload
from typing_extensions import (
    SupportsIndex,
    TypeVar,
    Unpack,
    NotRequired,
    Self,
    TypeGuard,
)


class MangleArgs(TypedDict):
    """mangle args"""

    prefix: NotRequired[str]
    suffix: NotRequired[str]
    title_case: NotRequired[bool]


K = TypeVar("K", infer_variance=True, default=str)


@overload
def mangle_key(key: K, /, **kwargs: Unpack[MangleArgs]) -> K:
    ...


def mangle_key(
    key: str,
    /,
    prefix: str | None = None,
    suffix: str | None = None,
    title_case: bool | None = None,
):
    """mangle Key"""
    if prefix:
        if not key:
            key = prefix
        elif title_case:
            key = prefix + key.title()
        else:
            key = prefix + key
    if suffix:
        if not key:
            return suffix
        if title_case:
            suffix = suffix.title()
        return key + suffix
    return key


def from_json(cls: type, json=None, **kwargs):
    """Create dataclass from JSON"""

    if json is None:
        return None

    return cls(
        **{
            field.name: json[mkey]
            for field in dataclasses.fields(cls)
            if (key := field.metadata.get("key"))
            and (mkey := mangle_key(key, **kwargs))
            and mkey in json
        }
    )


def _cmp(x: any, y: any):
    return 0 if x == y else 1 if x > y else -1


@dataclasses.dataclass(frozen=True, eq=False)
class SimpleTime:
    """Simple Time"""

    hour: int = dataclasses.field(default=0, metadata={"key": "hour"})
    minute: int = dataclasses.field(default=0, metadata={"key": "min"})

    def to_time(self):
        """as time"""
        return datetime.time(self.hour, self.minute)

    @classmethod
    def from_json(cls, json: dict, **kwargs: Unpack[MangleArgs]) -> Self:
        """Create value from JSON"""
        return from_json(cls, json, **kwargs)

    def _isinstance(self, value: any) -> TypeGuard["SimpleTime" | datetime.time]:
        return isinstance(value, (SimpleTime, datetime.time))

    def __eq__(self, __o: object):
        if self._isinstance(__o):
            return self._cmp(__o) == 0
        raise NotImplementedError

    def __le__(self, __o: object):
        if self._isinstance(__o):
            return self._cmp(__o) <= 0
        raise NotImplementedError

    def __lt__(self, __o: object):
        if self._isinstance(__o):
            return self._cmp(__o) < 0
        raise NotImplementedError

    def __ge__(self, __o: object):
        if self._isinstance(__o):
            return self._cmp(__o) >= 0
        raise NotImplementedError

    def __gt__(self, __o: object):
        if self._isinstance(__o):
            return self._cmp(__o) > 0
        raise NotImplementedError

    def _cmp(self, value: object):
        assert self._isinstance(value)
        return _cmp((self.hour, self.minute), (value.hour, value.minute))


_ZERO: Final = datetime.timedelta(0)


class _TzInfo(datetime.tzinfo):
    _cache: ClassVar[dict[(bool, int), "_TzInfo"]] = {}
    __slots__ = ("_hr_chg", "_ofs", "_start", "_end", "_point_cache")

    def __init__(self, dst: "DstInfo", time: "TimeInfo"):
        self._hr_chg = datetime.timedelta(dst.offset)
        # Reolink does positive offest python expects a negative one
        self._ofs = datetime.timedelta(seconds=-time.tz_offset)
        self._start = dst.start
        self._end = dst.end
        self._point_cache: dict[int, (datetime, datetime)] = {}

    def tzname(self, __dt: datetime.datetime | None) -> str | None:
        return None

    def _get_start_end(self, year: int):
        if year in self._point_cache:
            return self._point_cache[year]
        return self._point_cache.setdefault(
            year,
            (
                self._start.to_datetime(year),
                self._end.to_datetime(year),
            ),
        )

    def utcoffset(self, __dt: datetime.datetime | None) -> datetime.timedelta | None:
        if __dt is None:
            return self._ofs
        if __dt.tzinfo is not None:
            if __dt.tzinfo is not self:
                return __dt.utcoffset()
            __dt = __dt.replace(tzinfo=None)
        (start, end) = self._get_start_end(__dt.year)
        if start <= __dt < end:
            return self._ofs + self._hr_chg
        return self._ofs

    def dst(self, __dt: datetime.datetime | None) -> datetime.timedelta | None:
        if __dt is None:
            return self._hour_offset
        if __dt.tzinfo is not None:
            if __dt.tzinfo is not self:
                return __dt.dst()
            __dt = __dt.replace(tzinfo=None)
        (start, end) = self._get_start_end(__dt.year)
        if start <= __dt < end:
            return self._hr_chg
        return _ZERO

    @classmethod
    def get(cls, dst: "DstInfo", time: "TimeInfo"):
        """get or create timezone object"""
        key = (dst.enabled, time.tz_offset)
        return cls._cache.setdefault(key, cls(dst, time))


@dataclasses.dataclass(frozen=True)
class DstInfo:
    """Dst Info"""

    @dataclasses.dataclass(frozen=True, eq=False)
    class TimeInfo(SimpleTime):
        """Time Info"""

        month: int = dataclasses.field(default=0, metadata={"key": "mon"})
        week: int = dataclasses.field(default=0, metadata={"key": "week"})
        weekday: int = dataclasses.field(default=0, metadata={"key": "weekday"})

        def _isinstance(self, value: any) -> TypeGuard["DstInfo.TimeInfo"]:
            return isinstance(value, DstInfo.TimeInfo)

        def _cmp(self, value: object):
            res = super()._cmp(value)
            if res != 0:
                return res
            assert self._isinstance(value)
            return _cmp(
                (self.month, self.week, self.weekday),
                (value.month, value.week, value.weekday),
            )

        def to_date(self, year: int):
            """as date"""
            __date = datetime.date(year, self.month, 1)
            delta = datetime.timedelta(weeks=self.week, days=(self.weekday - 1) % 7)
            delta -= datetime.timedelta(days=__date.weekday())
            return __date + delta

        def to_datetime(self, year: int):
            """as datetime"""
            return datetime.datetime.combine(self.to_date(year), self.to_time())

    start: TimeInfo
    end: TimeInfo
    enabled: bool
    offset: int

    @classmethod
    def from_json(cls, json: dict) -> Self:
        """Create value from JSON"""
        if json is None:
            return None
        return cls(
            start=cls.TimeInfo.from_json(json, prefix="start", title_case=True),
            end=cls.TimeInfo.from_json(json, prefix="end", title_case=True),
            enabled=json.get("enabled"),
            offset=json.get("offset"),
        )


@dataclasses.dataclass(frozen=True, eq=False)
class Time(SimpleTime):
    """Time"""

    second: int = dataclasses.field(default=0, metadata={"key": "sec"})

    def _isinstance(self, value: any) -> TypeGuard["Time" | SimpleTime | datetime.time]:
        return super()._isinstance(value)

    def _cmp(self, value: object):
        res = super()._cmp(value)
        if res != 0 or not isinstance(value, (Time, datetime.time)):
            return res
        return _cmp(self.second, value.second)

    def to_time(self):
        """as time"""
        return datetime.time(self.hour, self.minute, self.second)


@dataclasses.dataclass(frozen=True, eq=False)
class Date:
    """Date"""

    year: int = dataclasses.field(default=0, metadata={"key": "year"})
    month: int = dataclasses.field(default=0, metadata={"key": "mon"})
    day: int = dataclasses.field(default=0, metadata={"key": "day"})

    def _isinstance(self, value: any) -> TypeGuard["Date" | datetime.date]:
        return isinstance(value, (Date, datetime.date))

    def __eq__(self, __o: object):
        if self._isinstance(__o):
            return self._cmp(__o) == 0
        raise NotImplementedError

    def __le__(self, __o: object):
        if self._isinstance(__o):
            return self._cmp(__o) <= 0
        raise NotImplementedError

    def __lt__(self, __o: object):
        if self._isinstance(__o):
            return self._cmp(__o) < 0
        raise NotImplementedError

    def __ge__(self, __o: object):
        if self._isinstance(__o):
            return self._cmp(__o) >= 0
        raise NotImplementedError

    def __gt__(self, __o: object):
        if self._isinstance(__o):
            return self._cmp(__o) > 0
        raise NotImplementedError

    def _cmp(self, value: object):
        assert self._isinstance(value)
        return _cmp(
            (self.year, self.month, self.day), (value.year, value.month, value.day)
        )

    def to_date(self):
        """as date"""
        return datetime.date(self.year, self.month, self.day)


@dataclasses.dataclass(frozen=True, eq=False)
class DateTime(Date, Time):
    """Datetime"""

    def _isinstance(
        self, value: any
    ) -> TypeGuard[
        "DateTime"
        | datetime.datetime
        | Date
        | datetime.date
        | Time
        | datetime.time
        | SimpleTime
    ]:
        return Date._isinstance(self, value) or Time._isinstance(self, value)

    def _cmp(self, value: object):
        assert self._isinstance(value)
        if Date._isinstance(self, value):
            res = Date._cmp(self, value)
            if res != 0:
                return res
        if Time._isinstance(self, value):
            return Time._cmp(self, value)
        return 0

    def time(self):
        """time"""
        return self.to_time()

    def date(self):
        """date"""
        return self.to_date()

    def to_datetime(self, tzinfo: datetime.tzinfo | None = None):
        """as datetime"""
        return datetime.datetime.combine(self.date(), self.time(), tzinfo)


@dataclasses.dataclass(frozen=True, eq=False)
class TimeInfo(DateTime):
    """Time Info"""

    hour_format: int = dataclasses.field(default=0, metadata={"key": "hourFmt"})
    time_format: str = dataclasses.field(
        default="DD/MM/YYYY", metadata={"key": "timeFmt"}
    )
    tz_offset: int = dataclasses.field(default=0, metadata={"key": "timeZone"})

    def _isinstance(
        self, value: any
    ) -> TypeGuard[
        "TimeInfo"
        | DateTime
        | datetime.datetime
        | Date
        | datetime.date
        | Time
        | datetime.time
        | SimpleTime
    ]:
        return isinstance(value, TimeInfo) or super()._isinstance(value)

    def __eq__(self, __o: object):
        if not super().__eq__(__o):
            return False
        if not isinstance(__o, TimeInfo):
            return True
        return (
            _cmp(
                (self.hour_format, self.time_format), (__o.hour_format, __o.time_format)
            )
            == 0
        )

    def _cmp(self, value: object):
        res = super()._cmp(value)
        if res != 0 or not isinstance(value, TimeInfo):
            return res
        return _cmp(self.tz_offset, value.tz_offset)

    def to_datetime(self, tzinfo: datetime.tzinfo | None = ...):
        if tzinfo is ...:
            tzinfo = datetime.timezone(datetime.timedelta(seconds=-self.tz_offset))
        return super().to_datetime(tzinfo)


@dataclasses.dataclass(frozen=True)
class DeviceTime:
    """Device Time"""

    dst: DstInfo
    time: TimeInfo

    def to_timezone(self):
        """as timezone"""
        return _TzInfo.get(self.dst, self.time)

    def to_datetime(self, include_tzinfo=True):
        """as datetime"""

        return self.time.to_datetime(self.to_timezone() if include_tzinfo else None)

    @classmethod
    def from_json(cls, json: dict):
        """Create value from JSON"""
        return cls(
            dst=DstInfo.from_json(json.get("Dst")),
            time=TimeInfo.from_json(json.get("Time")),
        )


DateRangeType = datetime.datetime | tuple[datetime.date, datetime.time, datetime.time]


class DateRange(Sequence[DateRangeType]):
    "Date(time) range"

    __slots__ = ("_start", "_stop", "_start_time", "_stop_time")

    def __init__(
        self,
        start: datetime.date | Date | datetime.datetime | DateTime,
        stop: datetime.date | Date | datetime.datetime | DateTime | None = None,
    ):
        super().__init__()
        if isinstance(start, DateTime):
            start = start.to_datetime()
        elif not isinstance(start, datetime.date):
            start = start.to_date()
        if isinstance(stop, DateTime):
            stop = stop.to_datetime()
        elif stop is not None and not isinstance(stop, datetime.date):
            stop = stop.to_date()
        if stop is not None and stop < start:
            (stop, start) = (start, stop)
        if isinstance(start, datetime.datetime):
            self._start: datetime.date = start.date()
            self._start_time: datetime.time = start.time()
        else:
            self._start = start
            self._start_time = None

        if isinstance(stop, datetime.datetime):
            self._stop: datetime.date = stop.date()
            self._stop_time: datetime.time = stop.time()
        else:
            self._stop = stop
            self._stop_time = None

    @property
    def start(self):
        """start"""
        if self._start_time is None:
            return self._start
        return datetime.datetime.combine(self._start, self._start_time)

    @property
    def stop(self):
        """stop"""
        if self._stop_time is None:
            return self._stop
        return datetime.datetime.combine(self._stop, self._start_time)

    def __getitem__(self, __index: SupportsIndex):
        date = self._start
        if __index > 0:
            date += datetime.timedelta(days=int(__index))
        _t = None
        if date == self._start:
            _t = self._start_time
        _t2 = None
        if date == self._stop:
            _t2 = self._stop_time
        if _t is None and _t2 is None:
            return date
        if _t is None:
            _t = datetime.time.min
        return (
            date,
            _t,
            _t2
            if _t2 is not None
            else datetime.time.max
            if self._stop is not None
            else _t,
        )

    def __len__(self):
        if self._stop is None:
            return 1
        return min((self._stop - self._start).days, 1)
