"""DateTime Utilities"""

import dataclasses
import datetime
from typing import (
    TYPE_CHECKING,
    ClassVar,
    Final,
    Generic,
    Sequence,
    TypedDict,
    overload,
)
from typing_extensions import (
    SupportsIndex,
    TypeVar,
)

if TYPE_CHECKING:
    from typing import cast

K = TypeVar("K", infer_variance=True, default=str)


def mangle_key(
    key: K,
    /,
    prefix: str | None = None,
    suffix: str | None = None,
    title_case: bool | None = None,
) -> K:
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


Mangle = TypedDict(
    "Mangle",
    {"prefix": str | None, "suffix": str | None, "title_case": bool | None},
    total=False,
)


@dataclasses.dataclass(frozen=True, init=False)
class _DstRule:
    month: int = dataclasses.field(metadata={"key": "mon"})
    week: int
    weekday: int
    hour: int
    minute: int = dataclasses.field(metadata={"key": "min"})

    def __init__(self, prefix: str, json: dict) -> None:
        for field in dataclasses.fields(self):
            setattr(
                self,
                field.name,
                json.get(mangle_key(field.name, prefix, title_case=True)),
            )
        self.weekday = (self.weekday + 1) % 7

    def datetime(self, year: int):
        """datetime"""
        date = datetime.date(year, self.month, 1)
        delta = datetime.timedelta(weeks=self.week, days=self.weekday)
        delta -= datetime.timedelta(days=date.weekday())
        date += delta
        return datetime.datetime.combine(date, datetime.time(self.hour, self.minute))


USING_KEY: Final = str()

Dst = TypedDict(
    "Dst",
    {
        "enabled": bool,
        "offset": int,
    },
)

Time = TypedDict(
    "Time",
    {
        "year": int,
        "mon": int,
        "day": int,
        "hour": int,
        "min": int,
        "sec": int,
        "hourFmt": int,
        "timeFmt": str,
        "timeZone": int,
    },
)


def json_to_datetime(
    json: dict, tzinfo: datetime.timezone | None = None
) -> datetime.datetime:
    """convert json time data to datetime"""

    if json is None:
        return None

    if TYPE_CHECKING:
        # use Time type for static type checking of needed keys
        typed = cast(Time, json)
        json: Time = typed

    return datetime.datetime(
        json.get("year", datetime.date.today().year),
        json.get("mon"),
        json.get("day"),
        json.get("hour", 0),
        json.get("min", 0),
        json.get("sec", 0),
        tzinfo=tzinfo,
    )


_ZERO: Final = datetime.timedelta(0)


class Timezone(datetime.tzinfo):
    """Reolink Timezone"""

    _cache: ClassVar[dict[(bool, int), "Timezone"]] = {}
    __slots__ = ("_hr_chg", "_ofs", "_start", "_end", "_point_cache")

    @staticmethod
    def get(dst: Dst, time: Time) -> "Timezone":
        """Esnure single timezone instance"""
        if dst is None:
            return None
        key = (dst["enabled"], time["timeZone"])
        if t_z := Timezone._cache.get(key):
            return t_z
        return Timezone._cache.setdefault(key, Timezone(dst, time))

    def __init__(self, dst: Dst, time: Time):
        self._hr_chg = dst["offset"]
        # Reolink does positive offest python expects a negative one
        self._ofs = datetime.timedelta(seconds=-time["timeZone"])
        self._start = _DstRule("start", dst)
        self._end = _DstRule("end", dst)
        self._point_cache: dict[int, (datetime, datetime)] = {}

    def tzname(self, __dt: datetime.datetime | None) -> str | None:
        return None

    def _get_start_end(self, year: int):
        if year in self._point_cache:
            return self._point_cache[year]
        return self._point_cache.setdefault(
            year,
            (
                self._start.datetime(year),
                self._end.datetime(year),
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


DateTimeRangeType = tuple[datetime.date, datetime.time, datetime.time]
DateRangeType = datetime.date | DateTimeRangeType

D = TypeVar("D", bound=DateRangeType, default=datetime.date)


class DateRange(Sequence[D], Generic[D]):
    "Date(time) range"

    __slots__ = ("_start", "_stop")

    @overload
    def __init__(
        self,
        start: datetime.date,
    ) -> None:
        ...

    @overload
    def __init__(
        self,
        start: datetime.date,
        stop: datetime.date,
    ) -> None:
        ...

    @overload
    def __init__(self: "DateRange[DateRangeType]", start: datetime.datetime) -> None:
        ...

    @overload
    def __init__(
        self: "DateRange[DateRangeType]",
        start: datetime.datetime,
        stop: datetime.datetime,
    ) -> None:
        ...

    def __init__(
        self,
        start: datetime.date,
        stop: datetime.date | None = None,
    ):
        super().__init__()
        if stop is not None and stop < start:
            (stop, start) = (start, stop)
        self._start = start
        self._stop = stop

    @property
    def start(self):
        """start"""
        return self._start

    @property
    def stop(self):
        """stop"""
        return self._stop

    def __getitem__(self, __index: SupportsIndex) -> D:
        date = (
            self._start.date()
            if isinstance(self._start, datetime.datetime)
            else self._start
        )
        if __index > 0:
            date += datetime.timedelta(days=int(__index))
        _t = None
        if date == self._start and isinstance(self._start, datetime.datetime):
            _t = self._start.time()
        _t2 = None
        if date == self._stop and isinstance(self._stop, datetime.datetime):
            _t2 = self._stop.time()
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

    def __contains__(self, value: object):
        if not isinstance(value, datetime.date):
            return False
        if self._stop is None:
            return self._start == value
        return self._start <= value <= self._stop

    def __len__(self):
        if self._stop is None:
            return 1
        return min((self._stop - self._start).days, 1)
