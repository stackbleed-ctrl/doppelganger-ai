"""
Calendar Integration
Reads Google Calendar and iCal feeds for context injection.
Provides upcoming events to the reasoning and proactive layers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    id: str
    title: str
    start: float           # unix timestamp
    end: float
    description: str = ""
    location: str = ""
    attendees: list[str] = field(default_factory=list)
    calendar: str = "default"
    is_all_day: bool = False
    recurring: bool = False


class CalendarManager:
    """
    Aggregates events from multiple calendar sources.
    Publishes upcoming events to the event bus for proactive context.
    """

    def __init__(self, bus: Any = None) -> None:
        self._bus = bus
        self._events: list[CalendarEvent] = []
        self._last_sync: float = 0.0
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._running = True
        await self.sync()
        self._task = asyncio.create_task(self._sync_loop(), name="calendar-sync")
        logger.info("CalendarManager started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def sync(self) -> int:
        """Sync all configured calendar sources. Returns event count."""
        events: list[CalendarEvent] = []

        # Google Calendar
        if os.environ.get("GOOGLE_CALENDAR_ID"):
            try:
                gcal_events = await self._fetch_google_calendar()
                events.extend(gcal_events)
            except Exception as e:
                logger.warning("Google Calendar sync failed: %s", e)

        # iCal URL
        if os.environ.get("ICAL_URL"):
            try:
                ical_events = await self._fetch_ical(os.environ["ICAL_URL"])
                events.extend(ical_events)
            except Exception as e:
                logger.warning("iCal sync failed: %s", e)

        self._events = sorted(events, key=lambda e: e.start)
        self._last_sync = time.time()

        if self._bus and events:
            await self._bus.publish_simple(
                "calendar.synced",
                payload={"count": len(events), "ts": self._last_sync},
                source="calendar",
            )

        logger.info("Calendar sync complete: %d events", len(events))
        return len(events)

    # ─── Queries ─────────────────────────────────────────────────────────────

    def get_upcoming(self, hours: int = 24) -> list[CalendarEvent]:
        """Get events starting within the next N hours."""
        now = time.time()
        cutoff = now + hours * 3600
        return [e for e in self._events if now <= e.start <= cutoff]

    def get_current(self) -> list[CalendarEvent]:
        """Get events happening right now."""
        now = time.time()
        return [e for e in self._events if e.start <= now <= e.end]

    def get_today(self) -> list[CalendarEvent]:
        return self.get_upcoming(hours=24)

    def get_week(self) -> list[CalendarEvent]:
        return self.get_upcoming(hours=168)

    def next_event(self) -> CalendarEvent | None:
        now = time.time()
        future = [e for e in self._events if e.start > now]
        return future[0] if future else None

    def context_string(self) -> str:
        """Format upcoming events as a context string for prompt injection."""
        upcoming = self.get_upcoming(hours=12)
        if not upcoming:
            return "No upcoming events in the next 12 hours."
        now = time.time()
        lines = []
        for e in upcoming[:5]:
            mins_until = int((e.start - now) / 60)
            if mins_until < 60:
                when = f"in {mins_until}min"
            elif mins_until < 1440:
                when = f"in {mins_until//60}h"
            else:
                when = datetime.fromtimestamp(e.start).strftime("%a %I:%M%p")
            desc = f" — {e.description[:60]}" if e.description else ""
            lines.append(f"• {when}: {e.title}{desc}")
        return "Upcoming:\n" + "\n".join(lines)

    # ─── Google Calendar ──────────────────────────────────────────────────────

    async def _fetch_google_calendar(self) -> list[CalendarEvent]:
        """Fetch via Google Calendar API v3."""
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set")

        now_iso = datetime.now(timezone.utc).isoformat()
        week_iso = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
                params={
                    "key": api_key,
                    "timeMin": now_iso,
                    "timeMax": week_iso,
                    "singleEvents": "true",
                    "orderBy": "startTime",
                    "maxResults": 50,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        events = []
        for item in data.get("items", []):
            start_raw = item.get("start", {})
            end_raw   = item.get("end", {})
            is_all_day = "date" in start_raw and "dateTime" not in start_raw

            def parse_ts(d: dict) -> float:
                if "dateTime" in d:
                    return datetime.fromisoformat(d["dateTime"]).timestamp()
                if "date" in d:
                    return datetime.strptime(d["date"], "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    ).timestamp()
                return time.time()

            events.append(CalendarEvent(
                id=item.get("id", ""),
                title=item.get("summary", "Untitled"),
                start=parse_ts(start_raw),
                end=parse_ts(end_raw),
                description=item.get("description", ""),
                location=item.get("location", ""),
                attendees=[a.get("email", "") for a in item.get("attendees", [])],
                calendar="google",
                is_all_day=is_all_day,
                recurring=bool(item.get("recurringEventId")),
            ))
        return events

    # ─── iCal ─────────────────────────────────────────────────────────────────

    async def _fetch_ical(self, url: str) -> list[CalendarEvent]:
        """Parse an iCal/ICS URL."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            ical_text = resp.text

        return self._parse_ical(ical_text)

    def _parse_ical(self, text: str) -> list[CalendarEvent]:
        """Simple iCal parser (no external deps)."""
        events = []
        current: dict = {}
        in_event = False

        for line in text.splitlines():
            line = line.strip()
            if line == "BEGIN:VEVENT":
                in_event = True
                current = {}
            elif line == "END:VEVENT" and in_event:
                in_event = False
                if "DTSTART" in current and "SUMMARY" in current:
                    try:
                        def ical_ts(val: str) -> float:
                            val = val.split(";")[-1].split(":")[-1]
                            if "T" in val:
                                fmt = "%Y%m%dT%H%M%SZ" if val.endswith("Z") else "%Y%m%dT%H%M%S"
                                return datetime.strptime(val.rstrip("Z"), fmt.rstrip("Z")).replace(
                                    tzinfo=timezone.utc
                                ).timestamp()
                            return datetime.strptime(val, "%Y%m%d").replace(
                                tzinfo=timezone.utc
                            ).timestamp()

                        start = ical_ts(current["DTSTART"])
                        end   = ical_ts(current.get("DTEND", current["DTSTART"]))
                        events.append(CalendarEvent(
                            id=current.get("UID", str(time.time())),
                            title=current.get("SUMMARY", "Untitled"),
                            start=start,
                            end=end,
                            description=current.get("DESCRIPTION", ""),
                            location=current.get("LOCATION", ""),
                            calendar="ical",
                        ))
                    except Exception as e:
                        logger.debug("iCal event parse error: %s", e)
            elif in_event and ":" in line:
                key, _, val = line.partition(":")
                current[key.split(";")[0]] = val

        now = time.time()
        week = now + 7 * 86400
        return [e for e in events if now <= e.start <= week]

    # ─── Sync loop ────────────────────────────────────────────────────────────

    async def _sync_loop(self) -> None:
        while self._running:
            await asyncio.sleep(900)  # sync every 15 min
            try:
                await self.sync()
            except Exception as e:
                logger.error("Calendar sync error: %s", e)
