""" Reolink Calendar for VOD searches """

from dataclasses import dataclass
import datetime
from typing import TYPE_CHECKING, Callable, Iterable, Iterator, Sequence, cast
from typing_extensions import TypeVar
from homeassistant.config_entries import (
    ConfigEntry,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.entity import EntityDescription
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from reolink_aio.api import Host
from reolink_aio.typings import SearchFile, SearchStatus

from homeassistant.components.reolink import ReolinkData
from homeassistant.components.reolink.entity import ReolinkCoordinatorEntity

from . import async_forward_reolink_entries, async_get_reolink_data

from .util import dt, search


@dataclass
class ReolinkCalendarEntityDescriptionMixin:
    """Mixin values for Reolink calendar entities."""


@dataclass
class ReolinkCalendarEntityDescription(
    EntityDescription, ReolinkCalendarEntityDescriptionMixin
):
    """A class that describes calendar entities."""

    supported: Callable[[Host, int | None], bool] = lambda host, ch: True


CALENDARS = (ReolinkCalendarEntityDescription("vod_calendar", name="Videos"),)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the calendar platform."""

    extras_entry = entry

    async def setup_entry(entry: ConfigEntry):
        reolink_data = async_get_reolink_data(hass, entry)

        entities: list[ReolinkVODCalendar] = []
        for channel in reolink_data.host.api.channels:
            entities.extend(
                [
                    ReolinkVODCalendar(reolink_data, channel, entity_description)
                    for entity_description in CALENDARS
                    if entity_description.supported(reolink_data.host.api, channel)
                ]
            )

        async_add_entities(entities)

    await async_forward_reolink_entries(hass, setup_entry)


StatusCache = dict[tuple[int, int], dt.DateRange]


def _status_cache_lookup(cache: StatusCache, value: datetime.date):
    return cache.get((value.year, value.month))


def _create_status_cache_filter(cache: StatusCache):
    def _filter(step: dt.DateRangeType):
        if isinstance(step, tuple):
            date = step[0]
        else:
            date = step
        if not (status := _status_cache_lookup(cache, date)):
            return False
        return date.day in status

    return _filter


FileEventType = tuple[SearchFile, CalendarEvent]

FileEventCache = dict[datetime.date, list[FileEventType]]


def _file_event_cache_lookup(
    file_events: FileEventCache, value: SearchFile | CalendarEvent
):
    if isinstance(value, CalendarEvent):
        filtered = filter(
            lambda fe: fe[1].start == value.start and fe[1].end == value.end,
            file_events.get(value.start.date(), []),
        )
    else:
        filtered = filter(
            lambda fe: search.cmp(fe[0]["StartTime"], value["StartTime"]) == 0
            and search.cmp(fe[0]["EndTime"], value["EndTime"]) == 0,
            file_events.get(dt.json_to_datetime(value["StartTime"]).date(), []),
        )

    return next(filtered, None)


def _file_event_cache_map(file_events: FileEventCache):
    def _map(step: dt.DateRangeType):
        if isinstance(step, tuple):
            date = step[0]
        else:
            date = step

        return (step, file_events.get(date, []))

    return _map


def _cmp_time(
    x: datetime.date | datetime.time | None, y: datetime.date | datetime.time | None
):
    if isinstance(x, datetime.datetime):
        x = x.time()
    elif not isinstance(x, datetime.time):
        x = None
    if isinstance(y, datetime.datetime):
        y = y.time()
    elif not isinstance(y, datetime.time):
        y = None
    if x is None and y is None:
        return 0
    if x is None:
        return -1
    if y is None:
        return 1
    return -1 if x < y else 1 if x > y else 0


def _date(value: datetime.date):
    if isinstance(value, datetime.datetime):
        return value.date()
    return value


def _iter_file_event_cache(
    __iter: Iterable[tuple[dt.DateRangeType, list[FileEventType]]]
    | Iterator[tuple[dt.DateRangeType, list[FileEventType]]]
):
    for step, __list in iter(__iter):
        time = None
        if isinstance(step, tuple):
            time = step[1:2]
            date = step[0]
        else:
            date = step
        for file_event in __list:
            start_ok = (fdate := _date(file_event[1].start)) < date or (
                fdate == date
                and _cmp_time(
                    file_event[1].start, time[0] if time is not None else None
                )
                >= 0
            )
            if not start_ok:
                continue
            end_ok = (fdate := _date(file_event[1].end)) > date or (
                fdate == date
                and _cmp_time(file_event[1].end, time[1] if time is not None else None)
                <= 0
            )
            if not end_ok:
                continue
            yield file_event


T = TypeVar("T", infer_variance=True)


def _last(value: Sequence[T]):
    if len(value) == 0:
        return None
    return value[-1]


class ReolinkVODCalendar(ReolinkCoordinatorEntity, CalendarEntity):
    """Reolink VOD Calendar"""

    entity_description: ReolinkCalendarEntityDescription

    def __init__(
        self,
        reolink_data: ReolinkData,
        channel: int,
        entity_description: ReolinkCalendarEntityDescription,
    ) -> None:
        super().__init__(reolink_data, channel)
        self.entity_description = entity_description
        self._status_cache: StatusCache = {}
        self._event_cache: FileEventCache = {}
        self._hard_stop: datetime.date = None

        self._attr_unique_id = (
            f"{self._host.unique_id}_{self._channel}_{entity_description.key}"
        )

    @property
    def event(self) -> CalendarEvent | None:
        if (
            (status_key := _last(self._status_cache.keys())) is not None
            and (status := self._status_cache[status_key])
            and (last := _last(status)) is not None
            and (_list := self._status_cache[last])
            and (entry := _last(_list))
        ):
            return entry[0]
        return None

    async def _async_fetch_events(
        self, start: datetime.date, end: datetime.date | None = None, status_only=False
    ):
        tzinfo = dt.Timezone.get(**self._host.api._time_settings)
        if isinstance(start, datetime.datetime):
            start = start.astimezone(tzinfo)
        else:
            start = datetime.datetime.combine(start, datetime.time.min, tzinfo)
        if isinstance(end, datetime.datetime):
            end = end.astimezone(tzinfo)
        else:
            end = datetime.datetime.combine(
                end if end is not None else datetime.date.today(),
                datetime.time.max,
                tzinfo,
            )

        statuses, results = await self._host.api.request_vod_files(
            self._channel, start, end, status_only=status_only
        )
        if statuses is None:
            return False

        for status in statuses:
            self._status_cache[
                (status["year"], status["mon"])
            ] = search.iter_search_status(status)

        if results is not None:
            for file in results:
                event = CalendarEvent(
                    dt.json_to_datetime(file["StartTime"], tzinfo),
                    dt.json_to_datetime(file["EndTime"], tzinfo),
                    "Motion Event",
                )
                key = _date(event.start)
                cache = self._event_cache.setdefault(key, [])
                # TODO : handle reload of same day
                cache.append((file, event))
        return True

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list[CalendarEvent]:
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        """Entity created."""
        await self._async_fetch_events(datetime.date.today())
        # TODO : walk statuses to find start of recordings
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{self._host.webhook_id}_{self._channel}",
                self._async_handle_event,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{self._host.webhook_id}_all",
                self._async_handle_event,
            )
        )

    async def _async_handle_event(self, event):
        """Handle incoming event for motion detection"""
        self.async_write_ha_state()
