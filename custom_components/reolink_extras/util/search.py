"""Search Utils"""

import datetime
from typing_extensions import SupportsIndex

from reolink_aio.typings import SearchStatus, SearchTime

from .dt import DateRange

# pylint: disable=invalid-name


def cmp(x: SearchTime | datetime.date, y: SearchTime | datetime.date):
    """compare SearchTime and date/time"""
    if isinstance(x, datetime.datetime):
        x = (x.year, x.month, x.day, x.hour, x.minute, x.second)
    elif isinstance(x, datetime.date):
        x = (x.year, x.month, x.day)
    else:
        x = (x["year"], x["mon"], x["day"], x["hour"], x["min"], x["sec"])

    if isinstance(y, datetime.datetime):
        y = (y.year, y.month, y.day, y.hour, y.minute, y.second)
    elif isinstance(y, datetime.date):
        y = (y.year, y.month, y.day)
    else:
        y = (y["year"], y["mon"], y["day"], y["hour"], y["min"], y["sec"])

    if len(x) > len(y):
        x = x[: len(y)]
    elif len(y) > len(x):
        y = y[: len(x)]

    return 1 if x > y else 0 if x == y else -1


def _nextmonth(year: int, month: int):
    if month > 11:
        year += 1
    return (year, (month + 1 % 12) + 1)


class _SearchDateRange(DateRange):
    def __init__(self, status: SearchStatus):
        start = datetime.date(status["year"], status["mon"], 1)
        end = datetime.date(*(_nextmonth(start.year, start.month) + (1,)))
        super().__init__(start, end)
        self._days = tuple(
            i for i, flag in enumerate(status["table"], start=1) if flag == "1"
        )

    def __contains__(self, value: object):
        if not isinstance(value, datetime.date):
            if isinstance(value, int):
                return value in self._days
            return False
        if value.year != self._start.year or value.month != self._start.month:
            return False
        return value.day in self._days

    def __getitem__(self, __index: SupportsIndex):
        return self._start + datetime.timedelta(days=self._days[__index] - 1)

    def __len__(self):
        return len(self._days)


def iter_search_status(status: SearchStatus) -> DateRange:
    """get DateRange of search status"""
    return _SearchDateRange(status)
