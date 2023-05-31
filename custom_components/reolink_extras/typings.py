"""Typings"""

import bisect
from datetime import datetime, date, time, MINYEAR, MAXYEAR, timedelta

from operator import index as _index
import typing
from typing_extensions import TypeVar

from reolink_aio.typings import VOD_search_status, VOD_file


def _cmp(x, y):
    return 0 if x == y else 1 if x > y else -1


_MAXORDINAL = MAXYEAR * 12 + 12

_date_class = date


class yearmonth:
    """Year and month partial"""

    __slots__ = ("_year", "_month", "_hashcode")

    min: typing.ClassVar["yearmonth"]
    max: typing.ClassVar["yearmonth"]

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
    def fromdate(cls, __date: "_date_class|yearmonth"):
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
        """construct date from monthyear and given day, use - for from end of month [-1 is last day of month]"""
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

    @typing.overload
    def __sub__(self, other: int) -> "yearmonth":
        ...

    @typing.overload
    def __sub__(self, other: "yearmonth") -> int:
        ...

    @typing.overload
    def __sub__(self, other: _date_class) -> int:
        ...

    @typing.overload
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

_T = TypeVar('_T', infer_variance=True)
_VT_co = TypeVar('_VT_co', covariant=True)
_KT_contra = TypeVar('_KT_contra', contravariant=True)

_slice_class = slice

class SearchCache(typing.Mapping[datetime, VOD_file], typing.Reversible[datetime]):
    "Search Cache"

    class OrderedDict(typing.Mapping[_KT_contra, _VT_co], typing.Reversible[_KT_contra]):
        """"Ordered" dictionary"""

        __slots__ = ("_keys", "_items")

        def __init__(self) -> None:
            super().__init__()
            self._keys:list[_KT_contra] = []

            self._items:dict[_KT_contra, _VT_co] = {}

        def __iter__(self):
            return self._keys.__iter__()

        def __reversed__(self):
            return self._keys.__reversed__()

        def __getitem__(self, __key: _KT_contra):
            return self._items.__getitem__(__key)

        def __len__(self):
            return self._items.__len__()

        def __contains__(self, __key: object):
            return self._items.__contains__(__key)

        def astuple(self):
            """as tuple"""
            return self._keys, self._items

        def __eq__(self, __value: object) -> bool:
            if not isinstance(__value, SearchCache.OrderedDict):
                return NotImplemented
            return self._keys == __value._keys and self._items == __value._items


    __slots__ = ("statuses", "files", "at_start", "at_end")

    def __init__(self):
        super().__init__()

        self.statuses:SearchCache.OrderedDict[yearmonth,VOD_search_status] = type(self).OrderedDict()
        self.files:SearchCache.OrderedDict[date,SearchCache.OrderedDict[time,VOD_file]] = type(self).OrderedDict()
        self.at_start: bool = False
        self.at_end: bool = False

    @typing.overload
    def __getitem__(self, __key: datetime) -> VOD_file:...

    @typing.overload
    def __getitem__(self, __key: _slice_class) -> typing.Iterable[VOD_file]:...

    def __getitem__(self, __key: datetime|_slice_class):
        if isinstance(__key, slice):
            return self.slice(slice.start, slice.stop)
        return self.files[__key.date()][__key.time()]

    def __iter__(self):
        for __date, files in self.files.items():
            for __time in files.keys():
                yield datetime.combine(__date, __time)

    def __len__(self) -> int:
        return sum(map(len, self.files.values()))

    def __reversed__(self):
        for __date in reversed(self.files):
            for __time in reversed(self.files[__date]):
                yield datetime.combine(__date, __time)

    def __contains__(self, __x: datetime):
        return (__files := self.files.get(__x.date())) and __x.time() in __files

    def __eq__(self, __other: object):
        if not isinstance(__other, SearchCache):
            return NotImplemented
        return __other.statuses == self.statuses and __other.files == self.files

    def _statuses_pop(self, __key: yearmonth):
        keys, statuses = self.statuses.astuple()
        if (status:= statuses.pop(__key, None)) is not None:
            keys.remove(__key)
        return status


    def _del_item(self, __key:date):
        if isinstance(__key, datetime):
            __time = __key.time()
            __key = __key.date()
            if not (items:=self.files.get(__key)):
                return
            keys, files = items.astuple()
            if not files.pop(__time, None):
                return
            keys.remove(__time)
            if len(files) > 0:
                return
        keys, items = self.files.astuple()
        if not items.pop(__key, None):
            return
        keys.remove(__key)

    def trim(self, __key: yearmonth | date):
        """trim from cache"""
        if isinstance(__key, yearmonth):
            if not (__status := self._statuses_pop(__key)):
                return
            for __date in __status:
                self._del_item(__date)
            return

        self._del_item(__key)

    @typing.overload
    def slice(self, start: yearmonth|None, end: yearmonth|None)->typing.Iterable[VOD_file]:...

    @typing.overload
    def slice(self, start: date|None, end: date|None)->typing.Iterable[VOD_file]:...

    @typing.overload
    def slice(self, start: datetime|None, end: datetime|None)->typing.Iterable[VOD_file]:...

    def slice(self, start: date|yearmonth|None, end: date|yearmonth|None=None):
        """get a slice of cache"""
        if len(self.statuses) < 1 or (start is None and end is None):
            return

        keys, _ = self.statuses.astuple()

        __ym = max(keys[0], yearmonth.fromdate(start))
        end_ym = min(keys[-1], yearmonth.fromdate(end))
        start_time = start.time() if isinstance(start, datetime) else time.min
        if not isinstance(start, date):
            at_start = start == __ym
            start = start.date()
        else:
            at_start = __ym.date() <= (start.date() if isinstance(start, datetime) else start)
        end_time = end.time() if isinstance(end, datetime) else time.max
        if not isinstance(end, date):
            end = end.date(-1)

        while __ym <= end_ym:
            if (status:=self.statuses.get(__ym)):
                for __date in status:
                    if at_start and __date.day < start.day:
                        continue
                    if at_start and __date.day > start.day:
                        at_start = False
                    elif __ym == end_ym and __date.day > end.day:
                        break
                    files = self.files.get(__date)
                    if not files:
                        continue
                    for __time, __file in files.items():
                        if at_start and __time < start_time:
                            continue
                        if __ym == end_ym and __date.day == end.day and __time > end_time:
                            break
                        yield __file

            at_start = False
            __ym += 1

    def append(self, __object: VOD_search_status | VOD_file):
        """append/update status or file"""
        if isinstance(__object, VOD_search_status):
            keys, statuses = self.statuses.astuple()
            __key = yearmonth.fromstatus(__object)
            if __status := statuses.get(__key):
                if __status.days == __object.days:
                    return
                # purge any days that fall off from last status
                for day in set(__status.days).difference(set(__object.days)):
                    self._del_item(__key.date(day))
            else:
                bisect.insort(keys, __key)
            statuses[__key] = __object
            return

        keys, items = self.files.astuple()
        __date = __object.start_time.date()
        if not (files := items.get(__date)):
            __files = type(self).OrderedDict()
            files = items.setdefault(__date, __files)
            if files is __files:
                bisect.insort(keys, __date)
        keys, files = files.astuple()
        __time = __object.start_time.time().replace(tzinfo=None)
        if __time not in files:
            bisect.insort(keys, __time)

        files[__time] = __object

    def extend(
        self,
        *__iterable: typing.Iterable[VOD_file] | typing.Iterable[VOD_search_status],
    ):
        """add search results to cache"""

        for __iter in __iterable:
            if not __iter:
                continue
            for __item in __iter:
                self.append(__item)
