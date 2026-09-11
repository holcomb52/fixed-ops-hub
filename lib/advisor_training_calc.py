"""Service Advisor daily training log — topics, skills, and progress helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

TOPIC_GROUPS: List[Tuple[str, List[Tuple[str, str]]]] = [
    (
        "Systems & Tools",
        [
            ("dms_login", "DMS / service system login & navigation along with Dealer Connect"),
            ("appointment_scheduling", "Appointment scheduling software"),
            ("mpi", "Multi-point inspection"),
            ("parts_lookup", "Parts lookup & ordering system"),
            ("phone_numa", "Phone system (NUMA)"),
        ],
    ),
    (
        "Customer Interaction",
        [
            ("greeting_walkaround", "Service drive greeting & vehicle walkaround"),
            ("active_listening", "Active listening & needs assessment"),
            ("writeup_ro", "Write-up process including diagnosis (creating the repair order)"),
            ("setting_expectations", "Setting expectations (time, cost, loaner/shuttle)"),
            ("phone_etiquette", "Phone etiquette"),
            ("deescalation", "De-escalating an upset customer"),
        ],
    ),
    (
        "Service Process",
        [
            ("explain_mpi", "Explaining recommended services / MPI results"),
            ("menu_upsell", "Menu pricing, alignments & upselling"),
            ("warranty_vs_cp", "Warranty vs. customer-pay determination"),
            ("estimate_approval", "Estimate approval & documentation"),
            ("parts_status", "Communicating parts status / delays"),
        ],
    ),
    (
        "Closing & Follow-Up",
        [
            ("review_ro", "Reviewing the completed repair order with the customer"),
            ("invoice_payment", "Explaining the invoice & taking payment"),
            ("vehicle_delivery", "Vehicle delivery"),
            ("csi_survey", "CSI survey explanation"),
        ],
    ),
    (
        "Shop / Dealership Specific",
        [
            ("loaner_shuttle", "Loaner car / shuttle process"),
            ("shop_policies", "Shop policies & teamwork with technicians"),
            ("other", "Other (see notes)"),
        ],
    ),
]

ALL_TOPIC_IDS: List[str] = [tid for _, items in TOPIC_GROUPS for tid, _ in items]
TOPIC_LABELS: Dict[str, str] = {tid: label for _, items in TOPIC_GROUPS for tid, label in items}

SKILLS: List[Tuple[str, str]] = [
    ("greeting_rapport", "Greeting customers & building rapport"),
    ("writeup_accuracy", "Write-up accuracy (RO creation)"),
    ("explain_pricing", "Explaining pricing, estimates & MPI results"),
    ("menu_presentation", "Menu presentation / upselling"),
    ("difficult_customers", "Handling difficult or upset customers"),
    ("time_management", "Time management & multitasking on the drive"),
]

SKILL_IDS: List[str] = [sid for sid, _ in SKILLS]
SKILL_LABELS: Dict[str, str] = {sid: label for sid, label in SKILLS}

SKILL_LEVELS: List[Tuple[str, str]] = [
    ("needs_practice", "Needs Practice"),
    ("developing", "Developing"),
    ("proficient", "Proficient"),
]

SKILL_LEVEL_LABELS: Dict[str, str] = dict(SKILL_LEVELS)
SKILL_RANK = {"needs_practice": 1, "developing": 2, "proficient": 3}

RECOMMENDATIONS: List[Tuple[str, str]] = [
    ("continue_training", "Continue training"),
    ("release_solo", "Release on their own"),
    ("termination", "Recommend termination"),
]

RECOMMENDATION_LABELS: Dict[str, str] = dict(RECOMMENDATIONS)
RECOMMENDATION_IDS: List[str] = [rid for rid, _ in RECOMMENDATIONS]


@dataclass
class AdvisorTrainingProgress:
    trainee_name: str
    log_count: int
    max_day_number: int
    topics_ever_covered: int
    topics_total: int
    skill_counts: Dict[str, int]
    latest_next_focus: str


def empty_topics() -> Dict[str, bool]:
    return {tid: False for tid in ALL_TOPIC_IDS}


def empty_skills() -> Dict[str, str]:
    return {sid: "" for sid in SKILL_IDS}


def normalize_topics(raw: Optional[dict]) -> Dict[str, bool]:
    out = empty_topics()
    if not isinstance(raw, dict):
        return out
    for tid in ALL_TOPIC_IDS:
        out[tid] = bool(raw.get(tid))
    return out


def normalize_skills(raw: Optional[dict]) -> Dict[str, str]:
    out = empty_skills()
    if not isinstance(raw, dict):
        return out
    for sid in SKILL_IDS:
        level = str(raw.get(sid) or "").strip()
        out[sid] = level if level in SKILL_LEVEL_LABELS else ""
    return out


def topics_checked_count(topics: Dict[str, bool]) -> int:
    return sum(1 for v in topics.values() if v)


def skills_rated_count(skills: Dict[str, str]) -> int:
    return sum(1 for v in skills.values() if v)


def normalize_recommendation(raw: Optional[str]) -> str:
    value = str(raw or "").strip()
    return value if value in RECOMMENDATION_LABELS else ""


def build_snapshot(
    *,
    trainee_name: str,
    trainer_name: str,
    log_date: str,
    day_number: int,
    topics: Dict[str, bool],
    skills: Dict[str, str],
    other_topic_note: str = "",
    trainee_questions: str = "",
    trainer_notes: str = "",
    next_focus: str = "",
    recommendation: str = "",
    recommendation_notes: str = "",
) -> dict:
    topics_n = normalize_topics(topics)
    skills_n = normalize_skills(skills)
    rec = normalize_recommendation(recommendation)
    return {
        "trainee_name": (trainee_name or "").strip(),
        "trainer_name": (trainer_name or "").strip(),
        "log_date": (log_date or "").strip(),
        "day_number": int(day_number or 0),
        "topics": topics_n,
        "topics_checked": topics_checked_count(topics_n),
        "skills": skills_n,
        "skills_rated": skills_rated_count(skills_n),
        "other_topic_note": (other_topic_note or "").strip(),
        "trainee_questions": (trainee_questions or "").strip(),
        "trainer_notes": (trainer_notes or "").strip(),
        "next_focus": (next_focus or "").strip(),
        "recommendation": rec,
        "recommendation_label": RECOMMENDATION_LABELS.get(rec, ""),
        "recommendation_notes": (recommendation_notes or "").strip(),
    }


def progress_from_logs(
    trainee_name: str,
    logs: Sequence[dict],
    *,
    exclude_run_id: Optional[str] = None,
) -> AdvisorTrainingProgress:
    key = (trainee_name or "").strip().casefold()
    topic_union = set()
    best_skills: Dict[str, str] = {}
    max_day = 0
    count = 0
    latest_focus = ""
    latest_completed = ""

    for rec in logs:
        snap = rec.get("snapshot") or {}
        name = (snap.get("trainee_name") or rec.get("employee_name") or "").strip()
        if name.casefold() != key:
            continue
        if exclude_run_id and rec.get("id") == exclude_run_id:
            continue
        count += 1
        topics = normalize_topics(snap.get("topics"))
        for tid, on in topics.items():
            if on:
                topic_union.add(tid)
        skills = normalize_skills(snap.get("skills"))
        for sid, level in skills.items():
            if not level:
                continue
            prev = best_skills.get(sid, "")
            if SKILL_RANK.get(level, 0) >= SKILL_RANK.get(prev, 0):
                best_skills[sid] = level
        try:
            max_day = max(max_day, int(snap.get("day_number") or 0))
        except (TypeError, ValueError):
            pass
        completed = str(rec.get("completed_at") or snap.get("log_date") or "")
        if completed >= latest_completed:
            latest_completed = completed
            latest_focus = str(snap.get("next_focus") or "")

    skill_counts = {level: 0 for level, _ in SKILL_LEVELS}
    for level in best_skills.values():
        if level in skill_counts:
            skill_counts[level] += 1

    return AdvisorTrainingProgress(
        trainee_name=(trainee_name or "").strip(),
        log_count=count,
        max_day_number=max_day,
        topics_ever_covered=len(topic_union),
        topics_total=len(ALL_TOPIC_IDS),
        skill_counts=skill_counts,
        latest_next_focus=latest_focus,
    )


def suggested_day_number(progress: AdvisorTrainingProgress) -> int:
    return max(progress.max_day_number + 1, 1)


def trainee_names_from_logs(logs: Iterable[dict]) -> List[str]:
    names = []
    seen = set()
    for rec in logs:
        snap = rec.get("snapshot") or {}
        name = (snap.get("trainee_name") or rec.get("employee_name") or "").strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return sorted(names, key=str.casefold)
