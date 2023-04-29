"""Typings"""

from collections import OrderedDict
from datetime import datetime, date, time, MINYEAR, MAXYEAR, timedelta

from operator import index as _index
from types import MappingProxyType
from typing import ClassVar, Iterable, Iterator, Mapping, Reversible, Union, overload
from reolink_aio.typings import VOD_search_status, VOD_file

dict_values = type({}.values())


def _cmp(x, y):
    return 0 if x == y else 1 if x > y else -1


_MAXORDINAL = MAXYEAR * 12 + 12

_date_class = date


class yearmonth:
    """Year and month partial"""

    __slots__ = ("_year", "_month", "_hashcode")

    min: ClassVar["yearmonth"]
    max: ClassVar["yearmonth"]

    def __init__(self, year: int, month: int):
        year = _index(year)
        if not MINYEAR <= year <= MAXYEAR:
            raise ValueError("year must be in %d..%d" % (MINYEAR, MAXYEAR), year)
        if not 1 <= month <= 12:
            raise ValueError("month must be in 1..12", month)
        self._year = _index(year)
        self._month = _index(month)
        self._hashcode = -1

    @classmethod
    def fromdate(cls, __date: _date_class):
        """Construct from date"""
        return cls(__date.year, __date.month)

    @classmethod
    def fromstatus(cls, __status: VOD_search_status):
        """Construct from search status"""
        return cls(__status.year, __status.month)

    @classmethod
    def _fromordinal(cls, n: int):
        (year, n) = divmod(n, 12)
        return cls(year, n + 1)

    def __repr__(self):
        """Convert to formal string, for repr()."""
        return "%s.%s(%d, %d)" % (
            self.__class__.__module__,
            self.__class__.__qualname__,
            self._year,
            self._month,
        )

    def __str__(self):
        return "%04d-%02d" % (self._year, self._month)

    # Read-only field accessors
    @property
    def year(self):
        """year (1-9999)"""
        return self._year

    @property
    def month(self):
        """month (1-12)"""
        return self._month

    def date(self, day: int = 1) -> date:
        """construct date from monthyear and given day, use -1 for from end of month [-1 is last day of month]"""
        if day >= 0:
            return date(self._year, self._month, day)
        return (self + 1).date() - timedelta(days=day)

    def replace(self, year: int = None, month: int = None):
        """Return a new yearmonth with new values for the specified fields."""
        if year is None:
            year = self._year
        if month is None:
            month = self._month
        return type(self)(year, month)

    def _toordinal(self):
        return self._year * 12 + (self._month - 1)

    def __add__(self, other: int) -> "yearmonth":
        if isinstance(other, int):
            o = self._toordinal() + other
            if 0 <= o <= _MAXORDINAL:
                return type(self)._fromordinal(o)
            raise OverflowError("result out of range")
        return NotImplemented

    __radd__ = __add__

    @overload
    def __sub__(self, other: int) -> "yearmonth":
        ...

    @overload
    def __sub__(self, other: "yearmonth") -> int:
        ...

    @overload
    def __sub__(self, other: _date_class) -> int:
        ...

    @overload
    def __sub__(self, other: VOD_search_status) -> int:
        ...

    def __sub__(self, other):
        if isinstance(other, int):
            return self + -other
        if isinstance(other, date):
            other = type(self).fromdate(other)
        elif isinstance(other, VOD_search_status):
            other = type(self).fromstatus(other)
        if isinstance(other, yearmonth):
            return self._toordinal() - other._toordinal()
        return NotImplemented

    # Comparisons of yearmonth objects with other.

    def __eq__(self, other) -> bool:
        if isinstance(other, (yearmonth, date, VOD_search_status)):
            return self._cmp(other) == 0
        return NotImplemented

    def __le__(self, other) -> bool:
        if isinstance(other, (yearmonth, date, VOD_search_status)):
            return self._cmp(other) <= 0
        return NotImplemented

    def __lt__(self, other) -> bool:
        if isinstance(other, (yearmonth, date, VOD_search_status)):
            return self._cmp(other) < 0
        return NotImplemented

    def __ge__(self, other) -> bool:
        if isinstance(other, (yearmonth, date, VOD_search_status)):
            return self._cmp(other) >= 0
        return NotImplemented

    def __gt__(self, other) -> bool:
        if isinstance(other, (yearmonth, date, VOD_search_status)):
            return self._cmp(other) > 0
        return NotImplemented

    def _cmp(self, other):
        assert isinstance(other, (yearmonth, date, VOD_search_status))
        y, m = self._year, self._month
        y2, m2 = other.year, other.month
        return _cmp((y, m), (y2, m2))

    def __hash__(self):
        "Hash."
        if self._hashcode == -1:
            self._hashcode = hash((self._year, self._month))
        return self._hashcode


yearmonth.min = yearmonth(MINYEAR, 1)
yearmonth.max = yearmonth(MAXYEAR, 12)


class SearchCache(Mapping[datetime, VOD_file], Reversible[datetime]):
    "Search Cache"

    __slots__ = ("_statuses", "_files", "at_start")

    def __init__(self):
        super().__init__()
        self._statuses: dict[yearmonth, VOD_search_status] = OrderedDict()
        self._files: dict[date, dict[time, VOD_file]] = OrderedDict()
        self.at_start: bool = False

    def __missing__(self, key):
        raise KeyError(key)

    def __getitem__(self, __key: datetime) -> VOD_file:
        if (__files := self._files.get(__key.date())) and (
            __file := __files.get(__key.time())
        ):
            return __file
        return self.__missing__(__key)

    def __iter__(self) -> Iterator[datetime]:
        for __date in self._files:
            __files = self._files[__date]
            for __time in __files:
                yield datetime.combine(__date, __time, tzinfo=__files[__time].tzinfo)

    def __len__(self) -> int:
        return sum((len(self._files[__date]) for __date in self._files), 0)

    def __reversed__(self) -> Iterator[datetime]:
        for __date in reversed(self._files):
            __files = self._files[__date]
            for __time in reversed(__files):
                yield datetime.combine(__date, __time, tzinfo=__files[__time].tzinfo)

    def __contains__(self, __x: datetime):
        if __files := self._files.get(__x.date()):
            return __x.time() in __files
        return False

    def __bool__(self):
        return any(self._files)

    def trim(self, __key: yearmonth | date):
        """trim from cache"""
        if isinstance(__key, yearmonth):
            if not (__status := self._statuses.pop(__key)):
                return
            for __date in __status:
                if __date in self._files:
                    del self._files[__date]
            return

        if not isinstance(__key, datetime):
            self._files.pop(__key, None)
            return

        if not (__files := self._files.get(__key.date())):
            return

        __files.pop(__key, None)

    @property
    def statuses(self):
        """search statuses"""
        return MappingProxyType(self._statuses)

    def slice(self, start: datetime, end: datetime):
        """get a slice of cache"""
        _ym = max(next(iter(self._statuses), None), yearmonth.fromdate(start))
        e_ym = min(next(reversed(self._statuses), None), yearmonth.fromdate(end))
        start_time = start.time()
        end_time = end.time()
        first = True

        while _ym <= e_ym:
            status = self._statuses.get(_ym)
            if status:
                for __date in status:
                    if first:
                        if __date.day < start.day:
                            continue
                        if __date.day > start.day:
                            first = False
                    if _ym == e_ym and __date.day > end.day:
                        break
                    files = self._files.get(__date)
                    if not files:
                        continue
                    for __time in files:
                        if first:
                            if __time < start_time:
                                continue
                            if __time >= start_time:
                                first = False
                        if _ym == e_ym and __date.day == end.day and __time > end_time:
                            break
                        yield files[__time]

            first = False
            _ym += 1

    def append(self, __object: VOD_search_status | VOD_file):
        """append/update status or file"""
        if isinstance(__object, VOD_search_status):
            __key = yearmonth.fromstatus(__object)
            if __status := self._statuses.get(__key):
                if __status.days == __object.days:
                    return
                # purge any days that fall off from last status
                for day in set(__status.days).difference(set(__object.days)):
                    self._files.pop(__key.date(day), None)

            self._statuses[__key] = __object
            t: MappingProxyType = {}
            return

        __dict = self._files.setdefault(__object.start_time.date(), OrderedDict())
        __dict[__object.start_time.time()] = __object

    def extend(
        self,
        __files: Iterable[VOD_file],
        __statuses: Iterable[VOD_search_status] = None,
    ):
        """add search results to cache"""
        if __statuses:
            self._statuses.update(
                ((yearmonth.fromstatus(status), status) for status in __statuses)
            )

        for file in __files:
            files = self._files.setdefault(file.start_time.date(), OrderedDict())
            files[file.start_time.time()] = file
