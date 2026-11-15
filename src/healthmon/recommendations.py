"""Parameter-specific, non-diagnostic follow-up guidance for configured alerts."""

from __future__ import annotations

from typing import Any


def _direction(
    factors: str,
    watch_actions: tuple[str, ...],
    critical_actions: tuple[str, ...],
    watch_follow_up: str,
    critical_follow_up: str,
    watch_contact: str,
    critical_contact: str,
    precaution: str = (
        "Do not change medication, supplements, prescribed exercise, or mission "
        "operations based only on this demonstration result."
    ),
) -> dict[str, Any]:
    return {
        "factors": factors,
        "actions": {"watch": watch_actions, "critical": critical_actions},
        "follow_up": {"watch": watch_follow_up, "critical": critical_follow_up},
        "contact": {"watch": watch_contact, "critical": critical_contact},
        "precautions": (precaution,),
    }


_REST_CONTACT = (
    "Contact onboard medical support if the reading persists, worsens, or occurs "
    "with concerning symptoms."
)
_URGENT_CONTACT = (
    "Contact onboard medical support now and follow the established mission "
    "medical emergency protocol."
)

PARAMETER_GUIDANCE: dict[str, dict[str, Any]] = {
    "heart_rate_bpm": {
        "label": "Heart rate",
        "unit": "bpm",
        ">": _direction(
            "Exertion, stress, fatigue, or measurement variation can affect heart "
            "rate; this reading does not identify a cause.",
            (
                "Pause strenuous activity if safe and rest in a comfortable position.",
                "Check hydration only in accordance with the mission plan.",
                "Recheck according to mission medical protocol.",
            ),
            (
                "Stop strenuous activity and notify onboard medical support now.",
                "Follow the mission medical emergency protocol.",
                "Do not resume strenuous activity until medically cleared.",
            ),
            "Recheck only as directed by mission protocol; do not delay support if symptoms occur.",
            "Immediate medical assessment; do not wait for another reading before contacting support.",
            _REST_CONTACT,
            _URGENT_CONTACT,
        ),
        "<": _direction(
            "Rest, sleep, medication, or measurement variation can affect heart "
            "rate; symptoms and mission context need medical assessment.",
            (
                "Rest in a safe position and note any dizziness, weakness, faintness, or breathing difficulty.",
                "Recheck according to mission medical protocol.",
            ),
            (
                "Stop activity and notify onboard medical support now.",
                "Follow the mission medical emergency protocol.",
            ),
            "Recheck only as directed; seek support sooner if symptoms are present.",
            "Immediate medical assessment; do not wait for a repeat reading.",
            _REST_CONTACT,
            _URGENT_CONTACT,
        ),
    },
    "systolic_bp_mmHg": {
        "label": "Systolic blood pressure",
        "unit": "mmHg",
        ">": _direction(
            "Posture, recent activity, stress, and measurement technique can affect a reading.",
            (
                "Rest safely and repeat the measurement using the approved procedure.",
                "Record symptoms and share persistent readings with medical support.",
            ),
            (
                "Stop activity and notify onboard medical support now.",
                "Follow the mission medical emergency protocol.",
            ),
            "Repeat only as directed by mission protocol.",
            "Immediate medical assessment; do not delay contact for a repeat measurement.",
            _REST_CONTACT,
            _URGENT_CONTACT,
        ),
        "<": _direction(
            "Posture, recent activity, hydration status, and measurement technique can affect a reading.",
            (
                "Sit or lie down safely, especially if light-headed.",
                "Repeat only using the approved procedure and report persistent readings.",
            ),
            (
                "Sit or lie down safely and notify onboard medical support now.",
                "Follow the mission medical emergency protocol.",
            ),
            "Recheck only as directed; seek support sooner if faintness or weakness occurs.",
            "Immediate medical assessment; do not delay contact for a repeat measurement.",
            _REST_CONTACT,
            _URGENT_CONTACT,
        ),
    },
    "diastolic_bp_mmHg": {
        "label": "Diastolic blood pressure",
        "unit": "mmHg",
        ">": _direction(
            "Posture, recent activity, stress, and measurement technique can affect a reading.",
            (
                "Rest safely and repeat the measurement using the approved procedure.",
                "Report persistent readings to medical support.",
            ),
            (
                "Stop activity and notify onboard medical support now.",
                "Follow the mission medical emergency protocol.",
            ),
            "Repeat only as directed by mission protocol.",
            "Immediate medical assessment; do not delay contact for a repeat measurement.",
            _REST_CONTACT,
            _URGENT_CONTACT,
        ),
        "<": _direction(
            "Posture, recent activity, and measurement technique can affect a reading.",
            (
                "Sit or lie down safely, especially if light-headed.",
                "Repeat only using the approved procedure and report persistent readings.",
            ),
            (
                "Sit or lie down safely and notify onboard medical support now.",
                "Follow the mission medical emergency protocol.",
            ),
            "Recheck only as directed; seek support sooner if faintness or weakness occurs.",
            "Immediate medical assessment; do not delay contact for a repeat measurement.",
            _REST_CONTACT,
            _URGENT_CONTACT,
        ),
    },
    "spo2_pct": {
        "label": "Blood oxygen (SpO₂)",
        "unit": "%",
        "<": _direction(
            "Sensor fit, signal quality, motion, and breathing changes can affect a reading.",
            (
                "Check sensor placement and signal quality according to mission procedure.",
                "Rest if safe and note any breathing difficulty or other symptoms.",
                "Recheck according to mission protocol.",
            ),
            (
                "Notify onboard medical support now and follow the mission emergency protocol.",
                "Do not delay contacting support to repeat a reading if breathing is difficult or symptoms are severe.",
            ),
            "Recheck as directed; contact medical support if it remains low or symptoms occur.",
            "Immediate medical assessment; do not wait for another reading before contacting support.",
            _REST_CONTACT,
            _URGENT_CONTACT,
        ),
    },
    "resp_rate_bpm": {
        "label": "Respiratory rate",
        "unit": "/min",
        ">": _direction(
            "Recent activity, stress, breathing symptoms, or measurement variation can affect this reading.",
            (
                "Stop exertion if safe, rest, and assess for breathing difficulty.",
                "Repeat the count or sensor measurement as directed by mission protocol.",
            ),
            (
                "Notify onboard medical support now and follow the mission emergency protocol.",
                "Seek immediate assistance for abnormal breathing or worsening symptoms.",
            ),
            "Recheck as directed; contact medical support if the change persists or symptoms occur.",
            "Immediate medical assessment; do not wait for a repeat reading.",
            _REST_CONTACT,
            _URGENT_CONTACT,
        ),
        "<": _direction(
            "Sleep state, sensor quality, or changes in breathing can affect this reading.",
            (
                "Check breathing and alertness and verify the measurement as directed.",
                "Rest safely and report persistent changes.",
            ),
            (
                "Check responsiveness and breathing; notify onboard medical support now.",
                "Follow the mission medical emergency protocol.",
            ),
            "Recheck as directed; seek support promptly if breathing or alertness is abnormal.",
            "Immediate medical assessment; do not wait for a repeat reading.",
            _REST_CONTACT,
            _URGENT_CONTACT,
        ),
    },
    "body_temp_c": {
        "label": "Body temperature",
        "unit": "°C",
        ">": _direction(
            "Measurement technique, environment, recent activity, or illness may affect temperature; this is not a diagnosis.",
            (
                "Reduce unnecessary exertion and verify the reading with an approved device.",
                "Note other symptoms and follow the onboard fever-management protocol.",
            ),
            (
                "Notify onboard medical support now and follow the mission medical protocol.",
                "Do not self-treat based on this demonstration result.",
            ),
            "Recheck only as directed; report persistent elevation or symptoms.",
            "Immediate medical assessment; do not delay contact for another reading.",
            _REST_CONTACT,
            _URGENT_CONTACT,
        ),
        "<": _direction(
            "Measurement technique or environment may affect temperature; the cause needs medical assessment.",
            (
                "Follow the onboard warming protocol and verify the reading with an approved device.",
                "Report persistent changes or symptoms.",
            ),
            (
                "Notify onboard medical support now and follow the mission emergency protocol.",
                "Use only mission-approved warming procedures.",
            ),
            "Recheck only as directed; contact support if it remains low or symptoms occur.",
            "Immediate medical assessment; do not delay contact for another reading.",
            _REST_CONTACT,
            _URGENT_CONTACT,
        ),
    },
    "sleep_hours": {
        "label": "Sleep",
        "unit": "hours",
        "<": _direction(
            "Workload, schedule, environment, or stress can affect sleep; the reading is not a diagnosis.",
            (
                "Follow the mission sleep plan and allow the scheduled rest opportunity.",
                "Review avoidable workload and sleep-environment concerns with the crew wellbeing team.",
            ),
            (
                "Notify the crew medical or wellbeing lead for prompt assessment.",
                "Follow mission guidance on workload and rest before safety-critical duties.",
            ),
            "Review the next scheduled sleep opportunity with the crew wellbeing team.",
            "Prompt medical/wellbeing review; follow mission guidance before safety-critical duties.",
            "Contact crew medical or wellbeing support if reduced sleep persists or affects functioning.",
            "Contact crew medical or wellbeing support promptly.",
        ),
    },
    "mood_score_1_10": {
        "label": "Mood self-report",
        "unit": "/10",
        "<": _direction(
            "A self-report reflects the person's experience and does not determine a diagnosis or cause.",
            (
                "Consider a private check-in with the crew wellbeing agent or a trusted crewmate.",
                "Use relaxation or other mission-approved support activities if helpful.",
            ),
            (
                "Contact the established confidential behavioral-health or medical support channel now.",
                "If anyone may be in immediate danger, use the mission emergency protocol.",
            ),
            "Choose a private follow-up time with crew wellbeing support.",
            "Immediate confidential support; use emergency procedures if safety is at risk.",
            "Contact confidential support if low mood persists, worsens, or affects safety.",
            "Contact confidential support promptly; use emergency procedures if safety is at risk.",
            "This score is sensitive self-report information; discuss it through the mission's confidential support channel.",
        ),
    },
    "cognitive_score_0_100": {
        "label": "Cognitive score",
        "unit": "/100",
        "<": _direction(
            "Sleep, workload, stress, task conditions, or measurement variation can affect performance scores.",
            (
                "Take a mission-approved rest opportunity and reduce nonessential cognitive workload.",
                "Reassess only as directed by the mission medical or operations team.",
            ),
            (
                "Notify onboard medical support now for assessment.",
                "Follow mission guidance before resuming safety-critical duties.",
            ),
            "Reassess as directed; report a continuing decline.",
            "Immediate medical assessment; follow mission guidance before safety-critical duties.",
            "Contact medical support if the decline persists, worsens, or affects safe task performance.",
            "Contact medical support promptly.",
        ),
    },
    "bone_density_pct_change": {
        "label": "Bone-density change",
        "unit": "%",
        "<": _direction(
            "Bone-density results are periodic measurements and require comparison with prior assessments by medical staff.",
            (
                "Review the result and trend with the medical team.",
                "Discuss prescribed resistance exercise and nutrition plans with them.",
            ),
            (
                "Notify the medical officer for evaluation of the result and trend.",
                "Do not independently change exercise, diet, or supplements.",
            ),
            "Follow the medical team's plan for the next assessment.",
            "Prompt medical review; follow the clinician's assessment plan.",
            "Contact the medical team for interpretation and individualized guidance.",
            "Contact the medical officer promptly for evaluation.",
        ),
        ">": _direction(
            "Bone-density changes are periodic measurements; the direction and significance require clinical interpretation.",
            (
                "Review the result and trend with the medical team.",
                "Continue only the prescribed countermeasure plan.",
            ),
            (
                "Notify the medical officer for evaluation of the result and trend.",
                "Do not independently change exercise, diet, or supplements.",
            ),
            "Follow the medical team's plan for the next assessment.",
            "Prompt medical review; follow the clinician's assessment plan.",
            "Contact the medical team for interpretation and individualized guidance.",
            "Contact the medical officer promptly for evaluation.",
        ),
    },
    "muscle_mass_pct_change": {
        "label": "Muscle-mass change",
        "unit": "%",
        "<": _direction(
            "Muscle-mass results are periodic measurements and should be interpreted with the mission medical team.",
            (
                "Review the trend, prescribed resistance exercise, nutrition, and recovery plan with the medical team.",
                "Continue only the approved exercise and nutrition plan.",
            ),
            (
                "Notify the medical officer for evaluation.",
                "Do not independently change exercise or nutrition prescriptions.",
            ),
            "Follow the medical team's plan for reassessment.",
            "Prompt medical review; follow the clinician's assessment plan.",
            "Contact the medical team if the change persists or affects function.",
            "Contact the medical officer promptly for evaluation.",
        ),
        ">": _direction(
            "Muscle-mass results are periodic measurements and should be interpreted with the mission medical team.",
            (
                "Review the result and trend with the medical team.",
                "Continue only the approved exercise and nutrition plan.",
            ),
            (
                "Notify the medical officer for evaluation.",
                "Do not independently change exercise or nutrition prescriptions.",
            ),
            "Follow the medical team's plan for reassessment.",
            "Prompt medical review; follow the clinician's assessment plan.",
            "Contact the medical team for interpretation.",
            "Contact the medical officer promptly for evaluation.",
        ),
    },
    "wbc_1e9_per_L": {
        "label": "White blood cells",
        "unit": "10⁹/L",
        "<": _direction(
            "This periodic laboratory result requires clinical interpretation; it cannot diagnose infection or immune change by itself.",
            (
                "Share the result and any symptoms with the flight surgeon for review.",
                "Follow the medical team's instructions for repeat testing or assessment.",
            ),
            (
                "Contact the flight surgeon or medical officer now for assessment.",
                "Follow mission medical guidance; do not self-diagnose or self-treat.",
            ),
            "Arrange medical review according to mission protocol.",
            "Prompt medical assessment according to mission protocol.",
            "Contact medical support for interpretation, especially if symptoms are present.",
            "Contact the flight surgeon or medical officer promptly.",
        ),
        ">": _direction(
            "This periodic laboratory result requires clinical interpretation; it cannot diagnose infection or immune change by itself.",
            (
                "Share the result and any symptoms with the flight surgeon for review.",
                "Follow the medical team's instructions for repeat testing or assessment.",
            ),
            (
                "Contact the flight surgeon or medical officer now for assessment.",
                "Follow mission medical guidance; do not self-diagnose or self-treat.",
            ),
            "Arrange medical review according to mission protocol.",
            "Prompt medical assessment according to mission protocol.",
            "Contact medical support for interpretation, especially if symptoms are present.",
            "Contact the flight surgeon or medical officer promptly.",
        ),
    },
    "crp_mg_per_L": {
        "label": "CRP",
        "unit": "mg/L",
        ">": _direction(
            "CRP is a nonspecific periodic laboratory result and needs interpretation alongside other findings and symptoms.",
            (
                "Share the result and any symptoms with the flight surgeon.",
                "Follow the medical team's instructions for further assessment.",
            ),
            (
                "Contact the flight surgeon or medical officer now for clinical assessment.",
                "Do not self-diagnose or self-treat from CRP alone.",
            ),
            "Arrange medical review according to mission protocol.",
            "Prompt medical assessment according to mission protocol.",
            "Contact medical support for interpretation, especially if symptoms are present.",
            "Contact the flight surgeon or medical officer promptly.",
        ),
    },
    "radiation_dose_mSv_day": {
        "label": "Daily radiation dose",
        "unit": "mSv/day",
        ">": _direction(
            "A dose reading can be affected by instrument status and mission conditions; use the approved radiation-monitoring plan.",
            (
                "Check the reading and exposure trend with the radiation-monitoring system.",
                "Review mission radiation guidance and exposure-reduction procedures.",
            ),
            (
                "Notify mission control and the crew according to the radiation emergency protocol.",
                "Follow established mission radiation-protection procedures.",
            ),
            "Continue review under the mission radiation-management plan.",
            "Immediate mission-control review under the radiation emergency protocol.",
            "Notify the responsible mission team if the reading persists or rises.",
            "Notify mission control now and follow the established protocol.",
            "Do not change mission operations except as directed by authorized mission control.",
        ),
    },
    "radiation_dose_cumulative_mSv": {
        "label": "Cumulative radiation dose",
        "unit": "mSv",
        ">": _direction(
            "Cumulative exposure must be compared with the mission-specific dose plan; this demo has no validated mission allowance.",
            (
                "Review the cumulative trend with mission control and the radiation-management plan.",
                "Use only mission-approved exposure-reduction procedures.",
            ),
            (
                "Notify mission control now for exposure assessment and mission-specific action.",
                "Follow the established radiation emergency protocol.",
            ),
            "Review the trend and any applicable mission limit with mission control.",
            "Immediate mission-control exposure assessment; follow mission-specific instructions.",
            "Contact mission control when approaching or exceeding a mission-defined review level.",
            "Notify mission control now for exposure assessment.",
            "This display is not an exposure allowance; mission control defines applicable limits and actions.",
        ),
    },
    "cabin_co2_ppm": {
        "label": "Cabin CO₂",
        "unit": "ppm",
        ">": _direction(
            "Sensor status, ventilation, or CO₂-removal system conditions may affect the cabin reading.",
            (
                "Verify the reading and sensor status according to spacecraft procedures.",
                "Check ventilation and CO₂-removal-system status using the approved checklist.",
            ),
            (
                "Alert the crew and notify mission control now.",
                "Follow the spacecraft CO₂ emergency procedures.",
            ),
            "Recheck according to environmental-monitoring procedure and report a persistent reading.",
            "Immediate action under spacecraft CO₂ emergency procedures; notify mission control.",
            "Notify the responsible crew member or mission control if the reading persists.",
            "Notify mission control now and follow spacecraft emergency procedures.",
            "Do not alter spacecraft systems except as directed by approved procedures.",
        ),
    },
}


def _parameter_card(
    rule: dict[str, Any],
    latest: dict[str, Any],
    previous: dict[str, Any] | None,
    baselines: dict[str, Any],
    baseline_source: str,
) -> dict[str, Any]:
    field = rule["col"]
    info = PARAMETER_GUIDANCE.get(field, {})
    direction = rule.get("op")
    severity = "critical" if rule.get("level") == "alert" else "watch"
    guidance = info.get(direction) or _direction(
        "This reading is outside a configured review limit; the result alone does not establish a cause.",
        ("Review the reading with the crew medical team and follow mission procedures.",),
        ("Contact onboard medical support now and follow the mission emergency protocol.",),
        "Recheck as directed by mission protocol.",
        "Immediate medical assessment; do not wait for another reading.",
        _REST_CONTACT,
        _URGENT_CONTACT,
    )
    try:
        value = float(rule["reading"])
    except (KeyError, TypeError, ValueError):
        value = float(latest[field])
    try:
        threshold = float(rule["val"])
    except (KeyError, TypeError, ValueError):
        threshold = None

    trend = "first_reading"
    previous_value = None
    if previous is not None:
        try:
            previous_value = float(previous[field])
        except (KeyError, TypeError, ValueError):
            pass
        if previous_value is not None:
            trend = (
                "higher" if value > previous_value
                else "lower" if value < previous_value
                else "unchanged"
            )

    baseline = None
    baseline_comparison = None
    try:
        baseline = float(baselines[field])
    except (KeyError, TypeError, ValueError):
        pass
    if baseline is not None:
        baseline_comparison = (
            "above" if value > baseline
            else "below" if value < baseline
            else "at"
        )

    return {
        "field": field,
        "label": info.get("label", field.replace("_", " ").title()),
        "status": "CRITICAL" if severity == "critical" else "WATCH",
        "severity": severity,
        "value": value,
        "unit": info.get("unit", ""),
        "comparison": "above" if direction == ">" else "below",
        "threshold": threshold,
        "trend": trend,
        "previous_value": previous_value,
        "baseline": baseline,
        "baseline_comparison": baseline_comparison,
        "baseline_source": baseline_source if baseline is not None else None,
        "factors": guidance["factors"],
        "actions": list(guidance["actions"][severity]),
        "precautions": list(guidance["precautions"]),
        "follow_up": guidance["follow_up"][severity],
        "contact": guidance["contact"][severity],
        "threshold_source": (
            "profile" if rule.get("personalized") else "demonstration"
        ),
    }


_PATTERNS = (
    {
        "key": "cardiorespiratory",
        "title": "Combined cardiorespiratory pattern",
        "members": {"heart_rate_bpm", "spo2_pct", "resp_rate_bpm"},
        "what": (
            "Multiple configured cardiovascular or breathing indicators are "
            "outside their review limits at the same time. This pattern is not a diagnosis."
        ),
        "factors": (
            "Several factors or measurement issues may contribute; the combination "
            "needs mission medical assessment."
        ),
        "watch_actions": (
            "Stop exertion if safe and notify onboard medical support for assessment.",
            "Check sensor quality only as directed; do not delay support if symptoms occur.",
            "Follow the mission medical protocol and report all affected readings together.",
        ),
        "critical_actions": (
            "Notify onboard medical support now and follow the mission emergency protocol.",
            "Do not wait for repeat readings if breathing difficulty, faintness, or severe symptoms are present.",
            "Do not resume strenuous or safety-critical activity until directed by medical staff.",
        ),
    },
    {
        "key": "crew_wellbeing",
        "title": "Combined sleep, mood, or cognitive pattern",
        "members": {"sleep_hours", "mood_score_1_10", "cognitive_score_0_100"},
        "what": (
            "More than one configured sleep, mood, or cognitive indicator needs "
            "attention. Review the combined trend with crew wellbeing support."
        ),
        "factors": (
            "Workload, schedule, sleep environment, stress, or measurement context "
            "may contribute; this pattern is not a diagnosis."
        ),
        "watch_actions": (
            "Arrange a private check-in with crew wellbeing or medical support.",
            "Review rest opportunities and nonessential workload within mission guidance.",
            "Share the combined trend rather than treating each reading in isolation.",
        ),
        "critical_actions": (
            "Contact confidential crew medical or behavioral-health support now.",
            "Follow mission guidance before safety-critical duties.",
            "Use the mission emergency protocol if anyone's immediate safety is at risk.",
        ),
    },
)


def build_follow_ups(
    flags: list[dict[str, Any]],
    latest: dict[str, Any],
    previous: dict[str, Any] | None,
    baselines: dict[str, Any] | None = None,
    baseline_source: str = "synthetic profile",
) -> list[dict[str, Any]]:
    """Build cards only for rules already matched by the configured alert engine."""
    baselines = baselines or {}
    cards_by_field: dict[str, dict[str, Any]] = {}
    for rule in flags:
        card = _parameter_card(rule, latest, previous, baselines, baseline_source)
        cards_by_field[card["field"]] = card

    grouped_fields: set[str] = set()
    cards: list[dict[str, Any]] = []
    for pattern in _PATTERNS:
        parameters = [
            cards_by_field[field]
            for field in sorted(pattern["members"])
            if field in cards_by_field
        ]
        if len(parameters) < 2:
            continue
        grouped_fields.update(item["field"] for item in parameters)
        critical = any(item["severity"] == "critical" for item in parameters)
        severity = "critical" if critical else "watch"
        cards.append({
            "kind": "pattern",
            "id": pattern["key"],
            "title": pattern["title"],
            "status": "CRITICAL" if critical else "WATCH",
            "severity": severity,
            "what": pattern["what"],
            "factors": pattern["factors"],
            "parameters": [
                {
                    key: item[key]
                    for key in (
                        "field", "label", "status", "value", "unit", "comparison",
                        "threshold", "trend", "previous_value", "baseline",
                        "baseline_comparison", "baseline_source", "threshold_source",
                    )
                }
                for item in parameters
            ],
            "actions": list(pattern[f"{severity}_actions"]),
            "precautions": (
                "Follow mission medical guidance; this demonstration does not triage symptoms "
                "or replace an onboard medical assessment.",
            ),
            "follow_up": (
                "Immediate medical assessment; do not wait for another reading."
                if critical else
                "Arrange prompt review and recheck only as directed by mission protocol."
            ),
            "contact": (
                _URGENT_CONTACT if critical else
                "Contact onboard medical support if any reading persists, worsens, or symptoms occur."
            ),
        })

    cards.extend(
        card for field, card in cards_by_field.items()
        if field not in grouped_fields
    )
    cards.sort(key=lambda card: (
        card["severity"] != "critical",
        card.get("title", card.get("label", "")),
    ))
    return cards
