"""
AI Engine — Schedule Generator  (v2)
======================================
Distributes study hours across available days before each exam using an
enhanced priority-score algorithm:

    priority_score = difficulty_weight × urgency_factor × log(days_remaining + 1)

Difficulty weights : Easy=1  Medium=2  Hard=3
Urgency factor     : max(1, 30 / remaining_days)  — grows sharply as exam nears

v2 improvements
---------------
* Grace-day buffer  — never schedules study on the day of the exam itself,
  giving the student a rest/revision day.
* Even distribution — remaining hours are spread as evenly as possible across
  available days instead of front-loading.
* Capacity re-balance — if daily_hours can't cover required_hours in the
  remaining days, the per-day limit is auto-raised to just fit.
* Priority metadata — _priority_score() now returns a rich dict so the UI
  can display each subject's urgency level, weight, and computed score.
* Max daily cap      — total planned hours per calendar day never exceeds 8 h.
"""

import math
from datetime import datetime, date, timedelta


DIFFICULTY_WEIGHTS = {"Easy": 1, "Medium": 2, "Hard": 3}

# Labels for urgency bands shown in the UI
def _urgency_label(factor: float) -> str:
    if factor >= 6:  return "Critical"
    if factor >= 3:  return "High"
    if factor >= 1.5: return "Medium"
    return "Low"


def _priority_score(difficulty: str, exam_date_str: str):
    """
    Compute and return a rich priority metadata dict for one subject.

    Returns a dict with keys:
        score, remaining_days, weight, urgency_factor, urgency_label
    Returns None when the exam date has already passed.
    """
    weight    = DIFFICULTY_WEIGHTS.get(difficulty, 1)
    exam_date = datetime.strptime(exam_date_str, "%Y-%m-%d").date()
    remaining = (exam_date - date.today()).days

    if remaining <= 0:
        return None

    # Urgency rises sharply as exam approaches; capped at 30 to avoid infinity
    urgency = max(1.0, 30.0 / remaining)
    score   = round(weight * urgency * math.log(remaining + 1), 3)

    return {
        "score":         score,
        "remaining_days": remaining,
        "weight":        weight,
        "urgency_factor": round(urgency, 2),
        "urgency_label": _urgency_label(urgency),
    }


def get_priority_breakdown(subjects_data: list) -> list:
    """
    Return per-subject priority metadata for display in the UI.

    Each returned dict:
        subject_name, difficulty, exam_date, score, remaining_days,
        weight, urgency_factor, urgency_label, score_pct (0-100 relative)
    """
    rows = []
    for sub in subjects_data:
        meta = _priority_score(sub["difficulty"], sub["exam_date"])
        if meta is None:
            meta = {
                "score": 0, "remaining_days": 0, "weight": DIFFICULTY_WEIGHTS.get(sub["difficulty"], 1),
                "urgency_factor": 0, "urgency_label": "Past",
            }
        rows.append({
            "subject_name":   sub["subject_name"],
            "difficulty":     sub["difficulty"],
            "exam_date":      sub["exam_date"],
            **meta,
        })

    # Normalise scores to 0-100 scale for progress bars
    max_score = max((r["score"] for r in rows), default=1) or 1
    for r in rows:
        r["score_pct"] = round(r["score"] / max_score * 100, 1)

    rows.sort(key=lambda x: x["score"], reverse=True)
    return rows


def generate_schedule(subjects_data: list) -> list:
    """
    Generate a day-by-day study schedule for a list of subjects.

    Each entry in subjects_data must be a dict with keys:
        subject_name, difficulty, exam_date, required_hours, daily_hours

    Returns a sorted list of dicts:
        [{'date': 'YYYY-MM-DD', 'subject': str, 'hours': float}, ...]
    """
    if not subjects_data:
        return []

    today = date.today()

    # ── Build plan per subject ────────────────────────────────────────────────
    plans = []
    for sub in subjects_data:
        meta = _priority_score(sub["difficulty"], sub["exam_date"])
        if meta is None:
            continue  # skip past exams

        exam_date      = datetime.strptime(sub["exam_date"], "%Y-%m-%d").date()
        required_hours = float(sub["required_hours"])
        daily_hours    = float(sub["daily_hours"])

        # Grace buffer: exclude the exam day itself (use days before exam)
        available_days = max(1, (exam_date - today).days - 1)

        # Auto-raise daily limit if required hours can't fit otherwise
        min_daily = required_hours / available_days
        if min_daily > daily_hours:
            daily_hours = round(min(min_daily, 8.0), 1)

        plans.append({
            "subject_name":   sub["subject_name"],
            "exam_date":      exam_date,
            "required_hours": required_hours,
            "daily_hours":    daily_hours,
            "priority_score": meta["score"],
            "available_days": available_days,
        })

    if not plans:
        return []

    # ── Build empty day buckets up to the latest exam ─────────────────────────
    max_exam   = max(p["exam_date"] for p in plans)
    total_days = (max_exam - today).days
    daily_slots: dict = {today + timedelta(days=i): [] for i in range(total_days)}

    # Track mutable remaining hours per subject.
    for p in plans:
        p["remaining_hours"] = float(p["required_hours"])

    # ── Allocate hours day-by-day with fair distribution ─────────────────────
    MAX_DAILY_HOURS = 8.0  # hard cap per calendar day across all subjects
    MIN_CHUNK = 0.1

    for day in sorted(daily_slots.keys()):
        day_capacity = MAX_DAILY_HOURS
        day_alloc = {p["subject_name"]: 0.0 for p in plans}

        # Active subjects for this day
        active = [
            p for p in plans
            if p["remaining_hours"] > 0.05 and day < p["exam_date"]
        ]

        if not active:
            continue

        # Pass 1 (fairness): ensure each active subject gets at least a base chunk.
        # This prevents only top-priority subjects from dominating the schedule.
        base_chunk = min(0.5, round(day_capacity / max(len(active), 1), 1))

        for p in active:
            if day_capacity < MIN_CHUNK:
                break

            subject_left_today = p["daily_hours"] - day_alloc[p["subject_name"]]
            if subject_left_today <= 0.05:
                continue

            allot = min(base_chunk, p["remaining_hours"], subject_left_today, day_capacity)
            allot = round(allot, 1)

            if allot >= MIN_CHUNK:
                day_alloc[p["subject_name"]] += allot
                p["remaining_hours"] = round(p["remaining_hours"] - allot, 2)
                day_capacity = round(day_capacity - allot, 2)

        # Pass 2 (priority): distribute remaining capacity by priority score.
        # Higher-priority subjects still get more time, but only after baseline fairness.
        safety_counter = 0
        while day_capacity >= MIN_CHUNK and safety_counter < 100:
            safety_counter += 1

            eligible = [
                p for p in active
                if p["remaining_hours"] > 0.05 and (p["daily_hours"] - day_alloc[p["subject_name"]]) > 0.05
            ]
            if not eligible:
                break

            total_score = sum(max(p["priority_score"], 0.1) for p in eligible)
            progressed = False

            for p in eligible:
                if day_capacity < MIN_CHUNK:
                    break

                weight = max(p["priority_score"], 0.1) / total_score
                suggested = max(day_capacity * weight, MIN_CHUNK)
                subject_left_today = p["daily_hours"] - day_alloc[p["subject_name"]]

                allot = min(suggested, p["remaining_hours"], subject_left_today, day_capacity)
                allot = round(allot, 1)

                if allot >= MIN_CHUNK:
                    day_alloc[p["subject_name"]] += allot
                    p["remaining_hours"] = round(p["remaining_hours"] - allot, 2)
                    day_capacity = round(day_capacity - allot, 2)
                    progressed = True

            if not progressed:
                break

        # Write this day's allocations
        for subject_name, hours in day_alloc.items():
            if hours >= MIN_CHUNK:
                daily_slots[day].append((subject_name, round(hours, 1)))

    # ── Flatten into output list ──────────────────────────────────────────────
    schedule = []
    for day, sessions in sorted(daily_slots.items()):
        for subject_name, hours in sessions:
            schedule.append({
                "date":    day.strftime("%Y-%m-%d"),
                "subject": subject_name,
                "hours":   hours,
            })

    return schedule
