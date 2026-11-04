"""Daily reminder job, run by the Railway cron service.

    python -m jobs.send_reminders                  Today, in Pacific time
    python -m jobs.send_reminders --dry-run        Print what would be sent, send nothing
    python -m jobs.send_reminders --date 2026-11-09 --only weekly

It sends the 7 days before and due date emails, custom reminders that are due, and
on Mondays the weekly digest. REMINDERS_DRY_RUN=true also makes it a dry run. It
prints a summary and exits with 1 if any email failed, so Railway shows the failure.
Running it twice on the same day sends nothing new.
"""

import argparse
import sys
from datetime import date

from app.config import get_settings
from app.services import clock
from app.services.reminders import run_daily


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send today's reminder emails")
    parser.add_argument("--dry-run", action="store_true", help="Print only, send nothing")
    parser.add_argument("--date", type=date.fromisoformat, help="Run as if today were YYYY-MM-DD")
    parser.add_argument("--only", choices=["weekly", "auto", "custom"])
    args = parser.parse_args(argv)

    dry_run = args.dry_run or get_settings().REMINDERS_DRY_RUN
    day = args.date or clock.today()
    print(f"Reminders for {day} ({day:%A}){', dry run' if dry_run else ''}")
    result = run_daily(day=day, only=args.only, dry_run=dry_run)

    for label in result.planned:
        print(f"  would send  {label}")
    for label in result.sent:
        print(f"  sent        {label}")
    for label in result.already:
        print(f"  already     {label}")
    for label in result.skipped:
        print(f"  skipped     {label}")
    for label in result.failed:
        print(f"  FAILED      {label}")

    if dry_run:
        print(f"Dry run, no email sent. {len(result.planned)} would be sent, "
              f"{len(result.already)} were already sent, {len(result.skipped)} skipped.")
        return 0
    print(result.summary())
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
