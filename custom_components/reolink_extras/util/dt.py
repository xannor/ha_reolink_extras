"""DateTime Utilities"""

import dataclasses
import datetime
from typing import (
    ClassVar,
    Final,
    Generic,
    NamedTuple,
    Sequence,
    TypedDict,
    overload,
)
from typing_extensions import (
    SupportsIndex,
    TypeVar,
    Unpack,
)


class YearMonthJson(TypedDict):
    """YeaRMonth JSON"""

    year: int
    mon: int
    """month"""


@dataclasses.dataclass(slots=True, frozen=True, order=True)
class YearMonth:
    """Year and Month"""

    min: ClassVar["YearMonth"]
    max: ClassVar["YearMonth"]

    year: int
    mon: dataclasses.InitVar[int]
    month: int = dataclasses.field(init=False)

    def __post_init__(self, mon: int):
        object.__setattr__(self, "month", mon)

    def date(self, day=1):
        """Return as date"""
        return datetime.date(self.year, self.month, day)

    def timetuple(self):
        """return as time_struct"""
        return self.date().timetuple()

    def replace(self, year: int = None, month: int = None):
        """Return a new YearMonth with new values for the specified fields."""
        if year is None:
            year = self.year
        if month is None:
            month = self.month
        return type(self)(year, month)


YearMonth.max = YearMonth(datetime.date.max.year, datetime.date.max.month)
YearMonth.min = YearMonth(datetime.date.min.year, datetime.date.min.month)


class DateJson(YearMonthJson):
    """Date JSON"""

    day: int


class HourMinuteJson(TypedDict):
    """Hour Minute JSON"""

    hour: int
    min: int


@dataclasses.dataclass(frozen=True, slots=True, order=True)
class HourMinute:
    """Hour / Minute"""

    min: ClassVar["HourMinute"]
    max: ClassVar["HourMinute"]

    hour: int
    min: dataclasses.InitVar[int]
    minute: int = dataclasses.field(init=False)

    # pylint: disable=redefined-builtin
    def __post_init__(self, min: int):
        object.__setattr__(self, "minute", min)

    def time(self, second: int = 0):
        """time"""
        return datetime.time(self.hour, self.minute, second)


HourMinute.min = HourMinute(datetime.time.min.hour, datetime.time.min.minute)
HourMinute.max = HourMinute(datetime.time.max.hour, datetime.time.max.minute)


class TimeJson(HourMinuteJson):
    """Time JSON"""

    sec: int


class DateTimeJson(DateJson, TimeJson):
    """Date Time JSON"""


@overload
def from_json(
    tzinfo: datetime.timezone = None, **kwargs: Unpack[DateTimeJson]
) -> datetime.datetime:
    ...


@overload
def from_json(**kwargs: Unpack[DateJson]) -> datetime.date:
    ...


@overload
def from_json(**kwargs: Unpack[YearMonthJson]) -> YearMonth:
    ...


@overload
def from_json(**kwargs: Unpack[TimeJson]) -> datetime.time:
    ...


@overload
def from_json(**kwargs: Unpack[HourMinuteJson]) -> HourMinute:
    ...


def from_json(*_, tzinfo: datetime.timezone = None, **kwargs: Unpack[DateTimeJson]):
    """get date/time from json"""
    (year, month, day, hour, minute, second) = (
        kwargs.get("year"),
        kwargs.get("mon", kwargs.get("month")),
        kwargs.get("day"),
        kwargs.get("hour"),
        kwargs.get("min", kwargs.get("minute")),
        kwargs.get("sec", kwargs.get("second")),
    )
    if year is not None:
        if day is None:
            __date = YearMonth(year, month or 1)
        else:
            __date = datetime.date(year, month, day)
    else:
        __date = None
    if hour is not None:
        if second is None and __date is None:
            __time = HourMinute(hour, minute or 0)
        else:
            __time = datetime.time(hour, minute or 0, second or 0)
    else:
        return __date
    if __date is None:
        return __time
    return datetime.datetime.combine(date(__date), time(__time), tzinfo)


@overload
def prev_month(value: YearMonth) -> YearMonth:
    ...


@overload
def prev_month(value: datetime.date) -> datetime.date:
    ...


@overload
def prev_month(value: datetime.datetime) -> datetime.datetime:
    ...


@overload
def prev_month(year: int, month: int) -> tuple[int, int]:
    ...


def prev_month(*args):
    """advance one month"""
    year: int
    month: int
    if len(args) < 1:
        return ()
    if len(args) > 1:
        (year, month) = args
    elif isinstance(args[0], (YearMonth, datetime.date)):
        year = args[0].year
        month = args[0].month

    if month < 2:
        year -= 1
        month = 12
    else:
        month -= 1

    if isinstance(args[0], (YearMonth, datetime.date)):
        return args[0].replace(year, month)
    return (year, month) + args[2:]


@overload
def next_month(value: YearMonth) -> YearMonth:
    ...


@overload
def next_month(value: datetime.date) -> datetime.date:
    ...


@overload
def next_month(value: datetime.datetime) -> datetime.datetime:
    ...


@overload
def next_month(year: int, month: int) -> tuple[int, int]:
    ...


def next_month(*args):
    """advance one month"""
    year: int
    month: int
    if len(args) < 1:
        return ()
    if len(args) > 1:
        (year, month) = args
    elif isinstance(args[0], (YearMonth, datetime.date)):
        year = args[0].year
        month = args[0].month

    if month > 11:
        year += 1
        month = 1
    else:
        month += 1

    if isinstance(args[0], (YearMonth, datetime.date)):
        return args[0].replace(year, month)
    return (year, month) + args[2:]


def date(value: datetime.date | YearMonth):
    """Get date only"""
    if isinstance(value, (datetime.datetime, YearMonth)):
        return value.date()
    return value


def time(value: datetime.time | datetime.datetime | HourMinute):
    """Get time only"""
    if isinstance(value, (datetime.datetime, HourMinute)):
        return value.time()
    return value


class MangleOptions(NamedTuple):
    """Mangle Options"""

    prefix: str | None = None
    suffix: str | None = None
    title_case: bool | None = None


def _mangle_key(key: str, options: MangleOptions):
    if options.title_case:
        key = key.lower()
    if options.prefix:
        if not key.startswith(options.prefix):
            return None
        key = key[len(options.prefix) :]
    if options.suffix:
        if not key.endswith(options.suffix):
            return None
        key = key[: -len(options.suffix)]
    return key


def mangle(options: MangleOptions, **kwargs: any):
    """get mangled subview of dictionary"""

    return {
        mkey: value
        for key, value in kwargs.items()
        if (mkey := _mangle_key(key, options))
    }


@dataclasses.dataclass(frozen=True, slots=True)
class _DstRule(HourMinute):
    sec: dataclasses.InitVar[int]
    second: int = dataclasses.field(init=False)
    month: int = dataclasses.field(init=False)
    mon: dataclasses.InitVar[int]
    week: int
    weekday: int

    # pylint: disable=redefined-builtin
    # pylint: disable=arguments-differ
    def __post_init__(self, min: int, sec: int, mon: int):
        # super broken
        HourMinute.__post_init__(self, min)
        object.__setattr__(self, "second", sec)
        object.__setattr__(self, "month", mon)

    def datetime(self, year: int):
        """datetime"""
        __date = datetime.date(year, self.month, 1)
        delta = datetime.timedelta(weeks=self.week, days=self.weekday)
        delta -= datetime.timedelta(days=__date.weekday())
        __date += delta
        return datetime.datetime.combine(
            __date, datetime.time(self.hour, self.minute, self.second)
        )


USING_KEY: Final = str()

Dst = TypedDict(
    "Dst",
    {
        "enable": bool,
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

GetTimeResponse = TypedDict("GetTimeResponse", {"Dst": Dst, "Time": Time})


# def json_to_datetime(
#     json: dict, tzinfo: datetime.timezone | None = None
# ) -> datetime.datetime:
#     """convert json time data to datetime"""

#     if json is None:
#         return None

#     if TYPE_CHECKING:
#         # use Time type for static type checking of needed keys
#         typed = cast(Time, json)
#         json: Time = typed

#     return datetime.datetime(
#         json.get("year", datetime.date.today().year),
#         json.get("mon"),
#         json.get("day"),
#         json.get("hour", 0),
#         json.get("min", 0),
#         json.get("sec", 0),
#         tzinfo=tzinfo,
#     )


_ZERO: Final = datetime.timedelta(0)


class Timezone(datetime.tzinfo):
    """Reolink Timezone"""

    _cache: ClassVar[dict[(bool, int), "Timezone"]] = {}
    __slots__ = ("_hr_chg", "_ofs", "_start", "_end", "_point_cache")

    @overload
    @staticmethod
    def get(dst: Dst, time: Time) -> "Timezone":  # pylint: disable=redefined-outer-name
        ...

    @overload
    @staticmethod
    def get(**kwargs: Unpack[GetTimeResponse]) -> "Timezone":
        ...

    @staticmethod
    def get(**kwargs: any) -> "Timezone":
        """Esnure single timezone instance"""
        dst: Dst = kwargs.get("Dst", kwargs.get("dst"))
        __time: Time = kwargs.get("Time", kwargs.get("time"))
        if dst is None or __time is None:
            return None
        key = (dst["enable"], __time["timeZone"])
        if t_z := Timezone._cache.get(key):
            return t_z
        return Timezone._cache.setdefault(key, Timezone(dst, __time))

    def __init__(self, dst: Dst, __time: Time):
        self._hr_chg = datetime.timedelta(hours=dst["offset"])
        # Reolink does positive offest python expects a negative one
        self._ofs = datetime.timedelta(seconds=-__time["timeZone"])
        self._start = _DstRule(
            **mangle(
                MangleOptions("start", title_case=True),
                **dst,
            )
        )
        self._end = _DstRule(**mangle(MangleOptions("end", title_case=True), **dst))
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


DateRangeType = datetime.date | tuple[datetime.date, datetime.time, datetime.time]

D = TypeVar("D", bound=DateRangeType, infer_variance=True, default=datetime.date)


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
        __date = (
            self._start.date()
            if isinstance(self._start, datetime.datetime)
            else self._start
        )
        if __index > 0:
            __date += datetime.timedelta(days=int(__index))
        _t = None
        if __date == self._start and isinstance(self._start, datetime.datetime):
            _t = self._start.time()
        _t2 = None
        if __date == self._stop and isinstance(self._stop, datetime.datetime):
            _t2 = self._stop.time()
        if _t is None and _t2 is None:
            return __date
        if _t is None:
            _t = datetime.time.min
        return (
            __date,
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
