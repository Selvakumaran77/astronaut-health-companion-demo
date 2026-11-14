"""
healthmon.notifications
=======================

Turns the day-by-day rule-based alert levels into **notifications about changes
of state**, so the crew is told when something starts, when it gets worse, and
-- importantly -- when it goes back to normal.

Rules
-----
* ``normal -> watch/alert``  -> **warning** (a problem started)
* ``watch -> alert``         -> **warning** (it got worse / escalated)
* ``alert -> watch``         -> no new alert (improving, but still not normal)
* ``watch/alert -> normal``  -> **recovered** ("back to normal", with peak + duration)

So while a crew member is *not* normal, the warnings stand; the moment the reading
climbs back down to the normal rate, a "back to normal" notification is raised.

Pure standard library.
"""

from __future__ import annotations

from typing import Any

from .alerts import LEVEL_RANK, evaluate_row

EVENT_RANK = {"warning": 1, "recovered": 0}


def build_notifications(
    rows: list[dict[str, Any]],
    profiles: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return state-change notifications across all crew, oldest first."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(str(r.get("crew_id", "?")), []).append(r)

    events: list[dict[str, Any]] = []

    for crew, seq in groups.items():
        seq.sort(key=lambda r: float(r.get("mission_day", 0)))
        prev_level = "normal"
        peak = "normal"
        start_day: int | None = None
        start_date: str | None = None

        for r in seq:
            finding = evaluate_row(r, profiles)
            level = finding.level
            day = int(float(r.get("mission_day", 0)))
            date = r.get("date_utc")

            if level != "normal":
                if prev_level == "normal":
                    # a problem started
                    start_day, start_date, peak = day, date, level
                    events.append({
                        "crew_id": crew, "mission_day": day, "date_utc": date,
                        "type": "warning", "event": "onset", "level": level,
                        "peak_level": level, "from_level": prev_level, "to_level": level,
                        "reasons": finding.messages,
                        "message": f"{crew} entered {level.upper()} on {date}",
                    })
                else:
                    if LEVEL_RANK[level] > LEVEL_RANK[peak]:
                        peak = level
                    if LEVEL_RANK[level] > LEVEL_RANK[prev_level]:
                        # got worse
                        events.append({
                            "crew_id": crew, "mission_day": day, "date_utc": date,
                            "type": "warning", "event": "escalation", "level": level,
                            "peak_level": peak, "from_level": prev_level, "to_level": level,
                            "reasons": finding.messages,
                            "message": f"{crew} escalated to {level.upper()} on {date}",
                        })
            else:
                if prev_level != "normal":
                    # back to normal
                    duration = day - (start_day if start_day is not None else day)
                    events.append({
                        "crew_id": crew, "mission_day": day, "date_utc": date,
                        "type": "recovered", "event": "recovered", "level": "normal",
                        "peak_level": peak, "from_level": prev_level, "to_level": "normal",
                        "since_day": start_day, "since_date": start_date,
                        "duration_days": duration, "reasons": [],
                        "message": (f"{crew} returned to NORMAL on {date} "
                                    f"after {duration} day(s) at peak {peak.upper()}"),
                    })
                    peak, start_day, start_date = "normal", None, None

            prev_level = level

    events.sort(key=lambda e: (e["mission_day"], e["crew_id"], EVENT_RANK.get(e["type"], 1)))
    return events


def summarize_notifications(
    rows: list[dict[str, Any]],
    profiles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Counts of notifications plus the current (latest) state per crew."""
    events = build_notifications(rows, profiles)
    counts = {"warning": 0, "recovered": 0}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1

    # current state = the level on each crew's most recent reading
    latest: dict[str, dict] = {}
    for r in rows:
        crew = str(r.get("crew_id", "?"))
        if crew not in latest or float(r.get("mission_day", 0)) > float(latest[crew].get("mission_day", 0)):
            latest[crew] = r
    current = {
        crew: evaluate_row(r, profiles).level for crew, r in latest.items()
    }
    return {
        "counts": counts,
        "total": len(events),
        "current_state": current,
        "active_warnings": sum(1 for lv in current.values() if lv != "normal"),
    }
