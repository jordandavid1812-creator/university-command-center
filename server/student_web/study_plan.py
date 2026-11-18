"""Study planner arithmetic: spread topics evenly over the days before an exam, keeping the last
`review_days` for revision. Pure functions: no database, no I/O."""
from datetime import timedelta

MAX_TOPICS = 60


def study_days(today, exam_date, review_days):
    """The days for new topics: today up to the day before the exam, minus the review days at the
    end. When the exam is too close for review days, every day before it is used."""
    last = exam_date - timedelta(days=1)
    if last < today:
        return []
    every = [today + timedelta(days=n) for n in range((last - today).days + 1)]
    kept = every[:len(every) - review_days] if review_days else every
    return kept or every


def spread(count, today, exam_date, review_days):
    """A date for each of `count` topics, in order, shared out evenly over the study days."""
    days = study_days(today, exam_date, review_days)
    if not days:
        raise ValueError("The exam date must be after today.")
    return [days[index * len(days) // count] for index in range(count)] if count else []


def review_dates(today, exam_date, review_days):
    """The revision days just before the exam (none when the exam is too close for them)."""
    days = study_days(today, exam_date, review_days)
    last = exam_date - timedelta(days=1)
    if not days:
        return []
    return [days[-1] + timedelta(days=n) for n in range(1, (last - days[-1]).days + 1)]


def topic_lines(text):
    """One topic per line: trimmed, blank lines skipped, duplicates kept (they may be real)."""
    return [' '.join(line.split()) for line in text.splitlines() if line.strip()]
