""" Reolink Calendar for VOD searches """

from dataclasses import dataclass
import datetime
from typing import TYPE_CHECKING, Callable, Iterable, Iterator, cast
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


StatusCache = dict[tuple[int,int], search.Status]


def _status_cache_lookup(cache: StatusCache, value: datetime.date | dt.Date):
    return cache.get((value.year, value.month))

def _create_status_cache_filter(cache: StatusCache):
    def _filter(step:dt.DateRangeType):
        if isinstance(step, tuple):
            date = step[0]
        else:
            date = step
        if not (status := _status_cache_lookup(cache, date)):
            return False
        return date.day in status.days

    return _filter

FileEventType = tuple[search.File,CalendarEvent]

FileEventCache = dict[datetime.date, list[FileEventType]]

def _file_event_cache_lookup(file_events: FileEventCache, value:search.File|CalendarEvent):
    if isinstance(value,search.File):
        filtered = filter(lambda fe: fe[0].start_time == value.start_time and fe[0].end_time == value.end_time, file_events.get(value.start_time.date(), []))
    else:
        filtered = filter(lambda fe: fe[1].start == value.start and fe[1].end == value.end, file_events.get( value.start.date(),[]))
    return next(filtered,None)

def _file_event_cache_map(file_events: FileEventCache):
    def _map(step:dt.DateRangeType):
        if isinstance(step, tuple):
            date = step[0]
        else:
            date = step

        return (step, file_events.get(date, []))

    return _map

def _iter_file_event_cache(__iter:Iterable[tuple[dt.DateRangeType,list[FileEventType]]]|Iterator[tuple[dt.DateRangeType,list[FileEventType]]]):
    for step, __list in iter(__iter):
        time = None
        if isinstance(step, tuple):
            time = step[1:2]
            date = step[0]
        else:
            date = step
        for file_event in __list:
            start_ok = (fdate := file_event[0].start_time.to_date()) < date or (fdate == date and (time is None or file_event[0].start_time.to_time() <= time[0]))
            if not start_ok:
                continue
            end_ok  = (fdate := file_event[0].end_time.to_date()) < date or (fdate == date and (time is None or file_event[0].start_time.to_time() <= time[1]))
            if not end_ok:
                continue
            yield file_event



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
        self._event_cache:FileEventCache = {}
        self._hard_stop:datetime.date = None
        self._

        self._attr_unique_id = (
            f"{self._host.unique_id}_{self._channel}_{entity_description.key}"
        )

    @property
    def event(self) -> CalendarEvent | None:
        return self._vod_cache[-1]

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list[CalendarEvent]:
        start_status = _status_cache_lookup(self._status_cache, start_date)
        end_status = _status_cache_lookup(self._status_cache, end_date)

        if start_status is not None and start_status.days

        status, __search = await self._host.api.request_vod_files(
            self._channel, start_date, end_date
        )
        tzinfo = dt.DeviceTime.from_json(self._host.api._time_settings).to_timezone()
        events: list[CalendarEvent] = []
        for __file in __search:
            file = search.File.from_json(__file)
            if file is None:
                continue
            event = CalendarEvent(
                file.start_time.to_datetime(tzinfo),
                file.end_time.to_datetime(tzinfo),
                summary="Motion Recording",
            )
            events.append(event)
        return events

    async def async_added_to_hass(self) -> None:
        """Entity created."""
        end = dt.DeviceTime.from_json(self._host.api._time_settings).to_datetime(
            False
        ) + datetime.timedelta(hours=1)
        start = datetime.datetime.combine(end.date(), datetime.time(), end.tzinfo)
        await self.async_get_events(self.hass, start, end)
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
