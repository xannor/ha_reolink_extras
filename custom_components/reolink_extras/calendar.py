""" Reolink Calendar for VOD searches """

from dataclasses import dataclass
import datetime
from typing import Callable
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

from reolink_aio.api import Host

from .helpers import async_forward_reolink_entries, async_get_reolink_data
from .helpers.search import async_get_search_cache, SearchCache


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
        for channel in reolink_data.host.api.channels:
            search = async_get_search_cache(hass, entry.entry_id, channel)
            entities.extend(
                [
                    ReolinkVODCalendar(
                        reolink_data, channel, entity_description, search
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
        cache: SearchCache,
    ) -> None:
        super().__init__(reolink_data, channel)
        self.entity_description = entity_description
        self._cache = cache

        self._attr_unique_id = (
            f"{self._host.unique_id}_{self._channel}_{entity_description.key}"
        )

    @property
    def event(self) -> CalendarEvent | None:
        if file := self._cache.get(self._cache.last):
            return CalendarEvent(
                dt.as_local(file.start),
                dt.as_local(file.end),
                f"{file.best_stream.trigger} Event",
            )

        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list[CalendarEvent]:
        results = self._cache.async_search(start_date, end_date)
        return [
            CalendarEvent(
                dt.as_local(file.start),
                dt.as_local(file.end),
                f"{file.best_stream.trigger} Event",
            )
            async for file in results
        ]

    async def async_added_to_hass(self) -> None:
        """Entity created."""
        await self._cache.async_update()
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
        await self._cache.async_update()
        self.async_write_ha_state()
