/**
 * The one place dates are formatted on screen.
 *
 * "Oct 26" and "Thu, Oct 30" in the current year, "Jul 14, 2026" in other years.
 * Dates from the API are plain YYYY-MM-DD strings, read as local calendar dates so
 * they never shift a day because of time zones.
 */

const TIME_ZONE = "America/Los_Angeles";

function parse(iso: string): Date {
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
}

function currentYear(): number {
  return Number(new Intl.DateTimeFormat("en-US", { year: "numeric", timeZone: TIME_ZONE }).format(new Date()));
}

export function formatDate(iso: string | null | undefined, options: { weekday?: boolean } = {}): string {
  if (!iso) return "";
  const date = parse(iso);
  const sameYear = date.getUTCFullYear() === currentYear();
  return new Intl.DateTimeFormat("en-US", {
    weekday: options.weekday ? "short" : undefined,
    month: "short",
    day: "numeric",
    year: sameYear ? undefined : "numeric",
    timeZone: "UTC",
  }).format(date);
}

/** Today in Pacific time, as YYYY-MM-DD, for date inputs. */
export function todayIso(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: TIME_ZONE,
  }).format(new Date());
  return parts;
}

export function addDays(iso: string, days: number): string {
  const date = parse(iso);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((parse(toIso).getTime() - parse(fromIso).getTime()) / 86_400_000);
}

export function seasonName(iso: string): string {
  const date = parse(iso);
  const month = date.getUTCMonth() + 1;
  const season =
    month === 12 || month <= 2 ? "Winter" : month <= 5 ? "Spring" : month <= 8 ? "Summer" : "Fall";
  const year = month === 12 ? date.getUTCFullYear() + 1 : date.getUTCFullYear();
  return `${season} ${year}`;
}
