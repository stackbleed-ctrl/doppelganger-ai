"""
Browser History Importer
Imports browsing history from Chrome, Firefox, and Safari
into Doppelganger memory. Fully local — reads SQLite directly.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from ..memory_manager import MemoryManager

logger = logging.getLogger(__name__)

# Paths per OS
CHROME_PATHS = {
    "darwin":  Path.home() / "Library/Application Support/Google/Chrome/Default/History",
    "linux":   Path.home() / ".config/google-chrome/Default/History",
    "win32":   Path.home() / "AppData/Local/Google/Chrome/User Data/Default/History",
}
FIREFOX_PROFILE_PATHS = {
    "darwin":  Path.home() / "Library/Application Support/Firefox/Profiles",
    "linux":   Path.home() / ".mozilla/firefox",
    "win32":   Path.home() / "AppData/Roaming/Mozilla/Firefox/Profiles",
}
SAFARI_PATH = Path.home() / "Library/Safari/History.db"


@dataclass
class HistoryEntry:
    url: str
    title: str
    visit_time: float
    visit_count: int = 1
    browser: str = "unknown"


def _safe_copy(src: Path) -> str | None:
    """Copy a locked SQLite file to a temp location for reading."""
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        shutil.copy2(src, tmp.name)
        return tmp.name
    except Exception as e:
        logger.warning("Could not copy %s: %s", src, e)
        return None


def _is_meaningful_url(url: str, title: str) -> bool:
    """Filter out internal browser pages, blank tabs, etc."""
    skip_schemes = ("chrome://", "chrome-extension://", "about:", "moz-extension://", "file://")
    skip_domains = {"google.com/search", "bing.com/search", "localhost", "127.0.0.1"}
    if any(url.startswith(s) for s in skip_schemes):
        return False
    if not title or title.strip() in ("New Tab", "newtab", "about:blank"):
        return False
    parsed = urlparse(url)
    for d in skip_domains:
        if d in parsed.netloc + parsed.path:
            return False
    return len(title) > 3


def read_chrome_history(limit: int = 500, days_back: int = 30) -> list[HistoryEntry]:
    import sys
    db_path = CHROME_PATHS.get(sys.platform)
    if not db_path or not db_path.exists():
        return []

    tmp = _safe_copy(db_path)
    if not tmp:
        return []

    entries = []
    cutoff = (time.time() - days_back * 86400) * 1_000_000 + 11644473600_000_000  # Chrome epoch

    try:
        conn = sqlite3.connect(tmp)
        rows = conn.execute("""
            SELECT url, title, last_visit_time, visit_count
            FROM urls
            WHERE last_visit_time > ? AND title != ''
            ORDER BY last_visit_time DESC
            LIMIT ?
        """, (cutoff, limit)).fetchall()
        conn.close()

        for url, title, ts, count in rows:
            if _is_meaningful_url(url, title):
                # Convert Chrome timestamp to Unix
                unix_ts = (ts - 11644473600_000_000) / 1_000_000
                entries.append(HistoryEntry(
                    url=url, title=title or "",
                    visit_time=unix_ts, visit_count=count,
                    browser="chrome",
                ))
    except Exception as e:
        logger.error("Chrome history read error: %s", e)
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass

    return entries


def read_firefox_history(limit: int = 500, days_back: int = 30) -> list[HistoryEntry]:
    import sys
    profile_dir = FIREFOX_PROFILE_PATHS.get(sys.platform)
    if not profile_dir or not profile_dir.exists():
        return []

    # Find the default profile
    db_path = None
    for profile in profile_dir.iterdir():
        candidate = profile / "places.sqlite"
        if candidate.exists():
            db_path = candidate
            break

    if not db_path:
        return []

    tmp = _safe_copy(db_path)
    if not tmp:
        return []

    entries = []
    cutoff_us = int((time.time() - days_back * 86400) * 1_000_000)

    try:
        conn = sqlite3.connect(tmp)
        rows = conn.execute("""
            SELECT p.url, p.title, h.visit_date, p.visit_count
            FROM moz_places p
            JOIN moz_historyvisits h ON h.place_id = p.id
            WHERE h.visit_date > ? AND p.title IS NOT NULL
            ORDER BY h.visit_date DESC
            LIMIT ?
        """, (cutoff_us, limit)).fetchall()
        conn.close()

        for url, title, ts_us, count in rows:
            if _is_meaningful_url(url, title or ""):
                entries.append(HistoryEntry(
                    url=url, title=title or "",
                    visit_time=ts_us / 1_000_000,
                    visit_count=count or 1,
                    browser="firefox",
                ))
    except Exception as e:
        logger.error("Firefox history read error: %s", e)
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass

    return entries


def read_safari_history(limit: int = 500, days_back: int = 30) -> list[HistoryEntry]:
    if not SAFARI_PATH.exists():
        return []

    tmp = _safe_copy(SAFARI_PATH)
    if not tmp:
        return []

    entries = []
    # Safari epoch: Jan 1 2001
    cutoff = time.time() - days_back * 86400 - 978307200

    try:
        conn = sqlite3.connect(tmp)
        rows = conn.execute("""
            SELECT hi.url, hv.title, hv.visit_time
            FROM history_items hi
            JOIN history_visits hv ON hv.history_item = hi.id
            WHERE hv.visit_time > ?
            ORDER BY hv.visit_time DESC
            LIMIT ?
        """, (cutoff, limit)).fetchall()
        conn.close()

        for url, title, ts in rows:
            if _is_meaningful_url(url, title or ""):
                unix_ts = ts + 978307200  # convert from Safari epoch
                entries.append(HistoryEntry(
                    url=url, title=title or "",
                    visit_time=unix_ts,
                    browser="safari",
                ))
    except Exception as e:
        logger.error("Safari history read error: %s", e)
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass

    return entries


async def import_browser_history(
    memory: MemoryManager,
    browsers: list[str] | None = None,
    days_back: int = 30,
    limit_per_browser: int = 200,
    cluster_by_domain: bool = True,
) -> dict:
    """
    Import browser history into memory.
    Clusters by domain to avoid noise (10+ visits to same site → one memory).
    """
    all_browsers = browsers or ["chrome", "firefox", "safari"]
    all_entries: list[HistoryEntry] = []

    loop = asyncio.get_event_loop()

    if "chrome" in all_browsers:
        entries = await loop.run_in_executor(None, read_chrome_history, limit_per_browser, days_back)
        all_entries.extend(entries)

    if "firefox" in all_browsers:
        entries = await loop.run_in_executor(None, read_firefox_history, limit_per_browser, days_back)
        all_entries.extend(entries)

    if "safari" in all_browsers:
        entries = await loop.run_in_executor(None, read_safari_history, limit_per_browser, days_back)
        all_entries.extend(entries)

    if not all_entries:
        return {"imported": 0, "message": "No browser history found"}

    imported = 0

    if cluster_by_domain:
        # Group by domain and store domain-level summaries
        domain_map: dict[str, list[HistoryEntry]] = {}
        for entry in all_entries:
            try:
                domain = urlparse(entry.url).netloc.replace("www.", "")
            except Exception:
                domain = "unknown"
            domain_map.setdefault(domain, []).append(entry)

        for domain, entries in domain_map.items():
            if not domain:
                continue
            titles = list({e.title for e in entries if e.title})[:5]
            total_visits = sum(e.visit_count for e in entries)
            content = (
                f"Browsed {domain} ({total_visits} visits, {len(entries)} pages). "
                f"Pages: {', '.join(titles[:3])}"
            )
            await memory.store(
                content,
                tags=["browser_history", "imported", domain.split(".")[0]],
                source="browser",
                entity_type="browsing_pattern",
                metadata={"domain": domain, "visit_count": total_visits},
            )
            imported += 1
    else:
        # Store individual entries
        for entry in sorted(all_entries, key=lambda e: e.visit_time, reverse=True)[:limit_per_browser]:
            content = f"Visited: {entry.title} ({entry.url})"
            await memory.store(
                content,
                tags=["browser_history", "imported", entry.browser],
                source="browser",
                entity_type="webpage",
                metadata={"url": entry.url, "visit_time": entry.visit_time},
            )
            imported += 1

    return {
        "total_entries": len(all_entries),
        "imported": imported,
        "browsers_found": list({e.browser for e in all_entries}),
        "days_back": days_back,
    }
