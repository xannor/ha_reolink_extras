""" Reolink Calendar for VOD searches """

from dataclasses import dataclass
import datetime
from typing import TYPE_CHECKING, Callable, cast
from typing_extensions import SupportsIndex
from homeassistant.config_entries import (
    ConfigEntry,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.entity import EntityDescription
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from homeassistant.components.reolink import ReolinkData
from homeassistant.components.reolink.entity import ReolinkChannelCoordinatorEntity

from homeassistant.util import dt

from reolink_aio.api import DUAL_LENS_MODELS
from reolink_aio.api import Host
from reolink_aio.typings import VOD_file, VOD_search_status

from .helpers import async_forward_reolink_entries, async_get_reolink_data

# from .helpers.search import async_get_search_cache, SearchCache


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
        reolink_data = async_get_reolink_data(hass, entry.entry_id)

        entities: list[ReolinkVODCalendar] = []
        for channel in reolink_data.host.api.stream_channels:
            # search = async_get_search_cache(hass, entry.entry_id, channel)
            entities.extend(
                [
                    ReolinkVODCalendar(
                        reolink_data, channel, entity_description  # , search
                    )
                    for entity_description in CALENDARS
                    if entity_description.supported(reolink_data.host.api, channel)
                ]
            )

        async_add_entities(entities)

    await async_forward_reolink_entries(hass, setup_entry)


class ReolinkVODCalendar(ReolinkChannelCoordinatorEntity, CalendarEntity):
    """Reolink VOD Calendar"""

    entity_description: ReolinkCalendarEntityDescription

    def __init__(
        self,
        reolink_data: ReolinkData,
        channel: int,
        entity_description: ReolinkCalendarEntityDescription,
        # cache: SearchCache,
    ) -> None:
        ReolinkChannelCoordinatorEntity.__init__(self, reolink_data, channel)
        CalendarEntity.__init__(self)
        self.entity_description = entity_description
        self._last_event: CalendarEvent | None = None

        if self._host.api.model in DUAL_LENS_MODELS:
            self._attr_name = f"{self.entity_description.name} lens {self._channel}"
        self._attr_unique_id = (
            f"{self._host.unique_id}_{self._channel}_{entity_description.key}"
        )

    @property
    def event(self) -> CalendarEvent | None:
        return self._last_event

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list[CalendarEvent]:
        # tzinfo = self._host.api.get_state()
        api: Host = self._host.api
        (statuses, files) = await api.request_vod_files(
            self._channel,
            start_date,
            end_date,
            stream="main",
            # .astimezone(tzinfo), end_date.astimezone(tzinfo)
        )
        # if results sets are too large we will not get full ranges
        # we should, however, get what ranges can give results
        # so we will use that to do multiple queries
        all_files = list(files)
        start = start_date.date()
        end = end_date.date()
        possible: set[datetime.date] = set(
            (
                status_date
                for status in statuses
                for status_date in status
                if start <= status_date < end
            )
        )
        found: set[datetime.date] = set((file.start_time.date() for file in files))
        missing = list(possible - found)
        while len(missing) > 0:
            missing.sort()
            start_date = datetime.datetime.combine(missing[0], datetime.time.min)
            end_date = datetime.datetime.combine(missing[-1], datetime.time.max)
            (_, files) = await api.request_vod_files(
                self._channel, start_date, end_date, stream="main"
            )
            all_files.extend(files)
            found.update(set((file.start_time.date() for file in files)))
            missing = list(possible - found)

        return [_file_to_event(file) for file in all_files]

    async def async_added_to_hass(self) -> None:
        """Entity created."""
        await self._async_handle_event(None)
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

    async def _async_handle_event(self, event):  # pylint: disable=unused-argument
        """Handle incoming event for motion detection"""
        now = datetime.datetime.now()
        # now = await self._host.api.async_get_time()
        # tzinfo = now.tzinfo
        tzinfo = None
        (statuses, _) = await self._host.api.request_vod_files(
            self._channel, now, now, True, "main"
        )
        while len(statuses[-1].days) < 1:
            if now.month > 1:
                now = now.replace(month=now.month - 1)
            else:
                now = now.replace(year=now.year - 1, month=1)
            (statuses, _) = await self._host.api.request_vod_files(
                self._channel, now, now, True, "main"
            )

        now = datetime.datetime.combine(statuses[-1][-1], datetime.time.min)
        (_, files) = await self._host.api.request_vod_files(
            self._channel, now, datetime.datetime.combine(now.date(), datetime.time.max)
        )
        file = files[-1]
        self._last_event = _file_to_event(file, tzinfo)

        if event is not None:
            self.async_write_ha_state()


def _file_to_event(file: VOD_file, tzinfo: datetime.tzinfo = None):
    return CalendarEvent(
        dt.as_utc(file.start_time.replace(tzinfo=tzinfo)),
        dt.as_utc(file.end_time.replace(tzinfo=tzinfo)),
        repr(file.triggers),
    )
