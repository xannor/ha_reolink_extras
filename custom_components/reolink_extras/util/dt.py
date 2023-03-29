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


def _mangle_field_metadata(field: dataclasses.Field, json: dict):
    key: str = field.metadata.get("key", field.name) or field.name
    if (value := json.get(key, ...)) is ...:
        return ...
    if (
        trans := field.metadata.get("transform", field.metadata.get("trans"))
    ) and callable(trans):
        value = trans(value)
    return value


def _mangle_dataclass_metadata(cls, json: dict):
    return {
        field.name: value
        for field in dataclasses.fields(cls)
        if (value := _mangle_dataclass_metadata(field, json)) is not ...
    }


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True, order=True)
class _YearMonth:
    year: int
    month: int = dataclasses.field(metadata={"key": "mon"})

    def date(self, day=1):
        """date"""
        return datetime.date(self.year, self.month, day)

    @classmethod
    def from_json(cls, json: dict):
        """from json"""
        return cls(**_mangle_dataclass_metadata(cls, json))


class YearMonth(_YearMonth):
    """Year and Month"""

    min: ClassVar["YearMonth"]
    max: ClassVar["YearMonth"]

    __slots__ = ()

    def next(self):
        """next month"""
        if self.month > 11:
            return YearMonth(year=self.year + 1, month=1)
        return YearMonth(year=self.year, month=self.month + 1)

    def prev(self):
        """previous month"""
        if self.month < 2:
            return YearMonth(year=self.year - 1, month=12)
        return YearMonth(year=self.year, month=self.month - 1)


YearMonth.max = YearMonth(year=datetime.date.max.year, month=datetime.date.max.month)
YearMonth.min = YearMonth(year=datetime.date.min.year, month=datetime.date.min.month)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True, order=True)
class SimpleDate(_YearMonth):
    """Simple Date"""

    min: ClassVar["SimpleDate"]
    max: ClassVar["SimpleDate"]

    day: int = dataclasses.field(default=1)

    @overload
    def __init__(self, *, year: int, month: int, day: int) -> None:
        ...

    # pylint: disable=arguments-differ
    def date(self):
        """date"""
        return super().date(self.day)


SimpleDate.min = SimpleDate(
    year=datetime.date.min.year,
    month=datetime.date.min.month,
    day=datetime.date.min.day,
)
SimpleDate.max = SimpleDate(
    year=datetime.date.max.year,
    month=datetime.date.max.month,
    day=datetime.date.max.day,
)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True, order=True)
class HourMinute:
    """Hour / Minute"""

    min: ClassVar["HourMinute"]
    max: ClassVar["HourMinute"]

    hour: int
    minute: int = dataclasses.field(metadata={"key": "min"})

    def time(self, second: int = 0, tzinfo: datetime.timezone = None):
        """time"""
        return datetime.time(self.hour, self.minute, second, tzinfo)

    @classmethod
    def from_json(cls, json: dict):
        """from json"""
        return cls(**_mangle_dataclass_metadata(cls, json))


HourMinute.min = HourMinute(
    hour=datetime.time.min.hour, minute=datetime.time.min.minute
)
HourMinute.max = HourMinute(
    hour=datetime.time.max.hour, minute=datetime.time.max.minute
)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True, order=True)
class SimpleTime(HourMinute):
    """Simple Time"""

    min: ClassVar["SimpleTime"]
    max: ClassVar["SimpleTime"]

    second: int = dataclasses.field(metadata={"key": "sec"})

    @overload
    def __init__(self, *, hour: int, minute: int, second: int) -> None:
        ...

    # pylint: disable=arguments-differ
    def time(self, tzinfo: datetime.timezone = None):
        """time"""
        super().time(self.second, tzinfo)


SimpleTime.min = SimpleTime(
    hour=datetime.time.min.hour,
    minute=datetime.time.min.minute,
    second=datetime.time.min.second,
)
SimpleTime.max = SimpleTime(
    hour=datetime.time.max.hour,
    minute=datetime.time.max.minute,
    second=datetime.time.min.second,
)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True, order=True)
class SimpleDateTime(SimpleTime, SimpleDate):
    """Simple DateTime"""

    min: ClassVar["SimpleDateTime"]
    max: ClassVar["SimpleDateTime"]

    @overload
    def __init__(
        self, *, year: int, month: int, day: int, hour: int, minute: int, second: int
    ) -> None:
        ...

    def datetime(self, tzinfo: datetime.timezone = None):
        """datetime"""
        return datetime.datetime(self.date(), self.time(tzinfo))

    @classmethod
    def combine(
        cls, date: SimpleDate, time: SimpleTime  # pylint: disable=redefined-outer-name
    ):
        """combine date and time"""
        return cls(
            year=date.year,
            month=date.month,
            day=date.day,
            hour=time.hour,
            minute=time.minute,
            second=time.second,
        )


def date(value: datetime.date | SimpleDate):
    """Get date only"""
    if isinstance(value, (datetime.datetime, SimpleDate)):
        return value.date()
    return value


def time(value: datetime.time | SimpleTime):
    """Get time only"""
    if isinstance(value, (datetime.datetime, SimpleTime)):
        return value.time()
    return value


class MangleOptions(NamedTuple):
    """Mangle Options"""

    prefix: str | None
    suffix: str | None
    title_case: bool | None


def _mangle_key(key: str, options: MangleOptions):
    if options.prefix and key.startswith(options.prefix):
        key = key[len(options.prefix) :]
    if options.suffix and key.endswith(options.suffix):
        key = key[: -len(options.suffix)]
    if options.title_case:
        key = key.lower()
    return key


@overload
def mangle(prefix: str, __dict: dict, /) -> dict:
    ...


@overload
def mangle(prefix: str, **kwargs: any) -> dict:
    ...


@overload
def mangle(prefix: str | None, suffix: str, __dict: dict, /) -> dict:
    ...


@overload
def mangle(prefix: str | None, suffix: str, **kwargs) -> dict:
    ...


@overload
def mangle(
    prefix: str | None, suffix: str | None, title_case: bool | None, __dict: dict, /
) -> dict:
    ...


@overload
def mangle(prefix: str | None, suffix: str, title_case: bool | None, **kwargs) -> dict:
    ...


def mangle(*args, **kwargs):
    """get mangled subview of dictionary"""
    options = MangleOptions(
        *(arg for arg in args if arg is None or isinstance(arg, (str, bool)))
    )
    if len(args) > 0 and isinstance(args[-1], dict):
        kwargs.update(args[-1])
    return {
        mkey: value
        for key, value in kwargs.items()
        if (mkey := _mangle_key(key, options)) != key
    }


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class _DstRule(HourMinute):
    month: int = dataclasses.field(metadata={"key": "mon"})
    week: int
    weekday: int

    def datetime(self, year: int):
        """datetime"""
        __date = datetime.date(year, self.month, 1)
        delta = datetime.timedelta(weeks=self.week, days=self.weekday)
        delta -= datetime.timedelta(days=__date.weekday())
        __date += delta
        return datetime.datetime.combine(__date, datetime.time(self.hour, self.minute))


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
        self._start = _DstRule.from_json(mangle("start", dst))
        self._end = _DstRule.from_json(mangle("end", dst))
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
