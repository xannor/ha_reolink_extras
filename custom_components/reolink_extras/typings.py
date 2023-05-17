"""Typings"""

import bisect
from datetime import datetime, date, time, MINYEAR, MAXYEAR, timedelta

from operator import index as _index
from typing import (
    Any, ClassVar, Iterable, Iterator, Mapping, MappingView, KeysView, SupportsIndex, ValuesView, ItemsView, Reversible, Sequence, TypeVar, overload,
)
from reolink_aio.typings import VOD_search_status, VOD_file


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

KT = TypeVar("KT")
VT = TypeVar("VT")

class SortedMapping(Mapping[KT, VT], Reversible[KT]):
    """Sorted Mapping"""

    __slots__ = ("_keys", "_items")

    def __init__(self, keys:Sequence[KT], items:Mapping[KT, VT]) -> None:
        super().__init__()
        self._keys = keys
        self._items = items

    def __len__(self) -> int:
        return len(self._keys)

    def __getitem__(self, __key: KT) -> VT:
        return self._items[__key]

    def __iter__(self) -> Iterator[KT]:
        return iter(self._keys)

    def __reversed__(self) -> Iterator[KT]:
        return iter(reversed(self._keys))

    def __contains__(self, __key: object) -> bool:
        return __key in self._items

    def __bool__(self) -> bool:
        return len(self._keys) > 0

    def items(self):
        return SortedItemsView(self)

    def keys(self):
        return SortedKeysView(self)

    def values(self):
        return SortedValuesView(self)

class SortedKeysView(Sequence[KT], KeysView[KT, VT]):

    _mapping: SortedMapping[KT, VT]

    def __getitem__(self, index:SupportsIndex):
        return self._mapping._keys[index]

class SortedValuesView(Sequence[VT], ValuesView[KT, VT]):

    _mapping: SortedMapping[KT, VT]

    def __getitem__(self, index:SupportsIndex):
        __key = self._mapping._keys[index]
        return self._mapping[__key]


class SortedItemsView(Sequence[tuple[KT, VT]], ItemsView[KT, VT]):

    _mapping: SortedMapping[KT, VT]

    def __getitem__(self, index:SupportsIndex):
        __key = self._mapping._keys[index]
        return (__key, self._mapping[__key])


class SearchCache(SortedMapping[datetime, VOD_file]):
    "Search Cache"

    _keys: list[date]
    _items: dict[date, tuple[list[time], dict[time, VOD_file]]]

    __slots__ = ("_status_keys", "_statuses", "at_start", "at_end")

    def __init__(self):
        super().__init__([], {})

        self._status_keys:list[yearmonth] = []
        self._statuses:dict[yearmonth,VOD_search_status] = {}
        self.at_start: bool = False
        self.at_end: bool = False

    def __getitem__(self, __key: datetime) -> VOD_file:
        return self._items.get(__key.date())[1].get(__key.time())

    def __iter__(self) -> Iterator[datetime]:
        for __date in self._keys:
            for __time in self._items[__date][0]:
                yield datetime.combine(__date, __time)

    def __len__(self) -> int:
        return sum(map(lambda d: len(d[0]), self._items.values()))

    def __reversed__(self) -> Iterator[datetime]:
        for __date in reversed(self._keys):
            for __time in reversed(self._items[__date][0]):
                yield datetime.combine(__date, __time)

    def __contains__(self, __x: datetime):
        if __files := self._items.get(__x.date()):
            return __x.time() in __files[1]
        return False

    def _statuses_pop(self, __key: yearmonth):
        if (status:= self._statuses.pop(__key, None)) is not None:
            self._status_keys.remove(__key)
        return status

    def _del_item(self, __key:date):
        if not isinstance(__key, datetime):
            if self._items.pop(__key, None) is None:
                self._keys.remove(__key)
            return
        if not (items := self._items.get(__key.date())):
            return
        __time = __key.time()
        keys, files = items
        if files.pop(__time, None):
            keys.remove(__time)

    def trim(self, __key: yearmonth | date):
        """trim from cache"""
        if isinstance(__key, yearmonth):
            if not (__status := self._statuses_pop(__key)):
                return
            for __date in __status:
                self._del_item(__date)
            return

        self._del_item(__key)

    @property
    def statuses(self):
        """search statuses"""
        return SortedMapping(self._status_keys, self._statuses)

    def slice(self, start: datetime, end: datetime):
        """get a slice of cache"""
        if len(self._status_keys) < 1:
            return
        __ym = max(self._status_keys[0], yearmonth.fromdate(start))
        end_ym = min(self._status_keys[-1], yearmonth.fromdate(end))
        start_time = start.time()
        end_time = end.time()
        first = True

        while __ym <= end_ym:
            status = self._statuses.get(__ym)
            if status:
                for __date in status:
                    if first:
                        if __date.day < start.day:
                            continue
                        if __date.day > start.day:
                            first = False
                    if __ym == end_ym and __date.day > end.day:
                        break
                    files = self._items.get(__date)
                    if not files:
                        continue
                    keys, items = files
                    for __time in keys:
                        if first:
                            if __time < start_time:
                                continue
                            if __time >= start_time:
                                first = False
                        if __ym == end_ym and __date.day == end.day and __time > end_time:
                            break
                        yield items[__time]

            first = False
            __ym += 1

    def append(self, __object: VOD_search_status | VOD_file):
        """append/update status or file"""
        if isinstance(__object, VOD_search_status):
            __key = yearmonth.fromstatus(__object)
            if __status := self._statuses.get(__key):
                if __status.days == __object.days:
                    return
                # purge any days that fall off from last status
                for day in set(__status.days).difference(set(__object.days)):
                    self._del_item(__key.date(day))
            else:
                bisect.insort(self._status_keys, __key)
            self._statuses[__key] = __object
            return

        keys, files = self._items.setdefault(__object.start_time.date(), ([], {}))
        __time = __object.start_time.time().replace(tzinfo=None)
        if __time not in files:
            bisect.insort(keys, __time)

        files[__time] = __object

    def extend(
        self,
        __files: Iterable[VOD_file],
        __statuses: Iterable[VOD_search_status] = None,
    ):
        """add search results to cache"""
        if __statuses:
            for status in __statuses:
                self.append(status)

        for file in __files:
            self.append(file)
