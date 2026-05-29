"""
Utils — Productivity Tracker
==============================
Helper functions for scoring and motivating students.
"""

from datetime import date, timedelta


def calculate_productivity_score(user_id: int, conn) -> float:
    """
    Return a blended productivity score based on study activity and tasks.

    The score favors study consistency, but still rewards task completion.
    This keeps the dashboard meaningful even when the user has no tasks yet.
    """
    today = date.today().strftime("%Y-%m-%d")

    study_hours_today = conn.execute(
        """
        SELECT COALESCE(SUM(hours),0) AS t
        FROM study_sessions
        WHERE user_id=? AND date=?
        """,
        (user_id, today),
    ).fetchone()["t"]

    completed_schedule_hours = conn.execute(
        """
        SELECT COALESCE(SUM(study_hours),0) AS t
        FROM schedules
        WHERE user_id=? AND date=? AND completed=1
        """,
        (user_id, today),
    ).fetchone()["t"]

    planned_today = conn.execute(
        """
        SELECT COALESCE(SUM(study_hours),0) AS t
        FROM schedules
        WHERE user_id=? AND date=?
        """,
        (user_id, today),
    ).fetchone()["t"]

    # Use the larger source for the day so timer-logged sessions and schedule
    # completions do not get double-counted when they refer to the same work.
    daily_study_total = max(float(study_hours_today), float(completed_schedule_hours))
    study_progress = 0.0
    if planned_today > 0:
        study_progress = min((daily_study_total / float(planned_today)) * 100, 100.0)
    elif daily_study_total > 0:
        study_progress = min(daily_study_total * 100, 100.0)

    total_tasks = conn.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE user_id=?", (user_id,)
    ).fetchone()["c"]
    task_progress = 0.0
    if total_tasks > 0:
        completed_tasks = conn.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE user_id=? AND status='Completed'",
            (user_id,),
        ).fetchone()["c"]
        task_progress = (completed_tasks / total_tasks) * 100

    if planned_today > 0 and total_tasks > 0:
        score = (study_progress * 0.7) + (task_progress * 0.3)
    elif planned_today > 0:
        score = study_progress
    elif total_tasks > 0:
        score = task_progress
    else:
        score = daily_study_total * 25

    return round(min(score, 100.0), 1)


def get_weekly_stats(user_id: int, conn) -> dict:
    """
    Return dicts with 'dates' and 'hours' arrays for the last 7 days.
    Used to draw the dashboard line chart.
    """
    dates, hours = [], []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).strftime("%Y-%m-%d")
        h = conn.execute(
            """
            SELECT COALESCE(SUM(hours),0) AS t
            FROM study_sessions
            WHERE user_id=? AND date=?
            """,
            (user_id, d),
        ).fetchone()["t"]
        scheduled = conn.execute(
            """
            SELECT COALESCE(SUM(study_hours),0) AS t
            FROM schedules
            WHERE user_id=? AND date=? AND completed=1
            """,
            (user_id, d),
        ).fetchone()["t"]
        h = max(float(h), float(scheduled))
        dates.append(d)
        hours.append(round(h, 2))

    return {"dates": dates, "hours": hours}


def get_study_streak(user_id: int, conn) -> int:
    """
    Count consecutive days (ending today) that have at least one study activity.

    A study activity can be either:
    - a logged study session from the timer, or
    - a completed schedule entry for that day.
    """
    streak  = 0
    current = date.today()

    activity_days = {
        row["activity_date"]
        for row in conn.execute(
            """
            SELECT DISTINCT date AS activity_date
            FROM study_sessions
            WHERE user_id=?
            UNION
            SELECT DISTINCT date AS activity_date
            FROM schedules
            WHERE user_id=? AND completed=1
            """,
            (user_id, user_id),
        ).fetchall()
    }

    while True:
        d = current.strftime("%Y-%m-%d")
        if d in activity_days:
            streak  += 1
            current -= timedelta(days=1)
        else:
            break

    return streak


def get_motivational_message(productivity_score: float) -> str:
    """Return an encouraging message based on the student's score."""
    if productivity_score >= 80:
        return "🌟 Excellent work! You're crushing your goals!"
    if productivity_score >= 60:
        return "💪 Great progress! Keep up the momentum!"
    if productivity_score >= 40:
        return "📚 You're on the right track! Stay consistent!"
    if productivity_score > 0:
        return "🚀 Every step counts! Let's pick up the pace!"
    return "👋 Welcome! Start your learning journey today!"
