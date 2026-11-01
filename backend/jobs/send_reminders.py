"""Daily reminder job, run by the Railway cron service.

Run it with: python -m jobs.send_reminders

For now this is a dry run. It prints which tasks would get a reminder and sends
nothing. Reminders go out 7 days before a task is due and on the due date.
"""

from app.services.reminders import tasks_due_in

REMINDER_DAYS = (7, 0)


def main() -> int:
    for days in REMINDER_DAYS:
        tasks = tasks_due_in(days)
        print(f"Due in {days} days: {len(tasks)} tasks would get a reminder")
        for task in tasks:
            print(f"  {task}")
    print("Dry run, no email sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
