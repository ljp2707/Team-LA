import { get, send } from "./client";

/** The signed-in person's calendar feed: a private .ics link of their tasks. */
export interface CalendarFeed {
  enabled: boolean;
  /** False for read-only people (Viewers), who cannot turn it on. */
  can_turn_on: boolean;
  feed_url: string | null;
  /** Opens Google Calendar's "add calendar by URL" screen with the link filled in. */
  google_url: string | null;
}

export const getCalendarFeed = () => get<CalendarFeed>("/api/me/calendar-feed");

/** Turns the feed on, or replaces the link with a new one. The old link stops working. */
export const newCalendarFeedLink = () => send<CalendarFeed>("POST", "/api/me/calendar-feed");

export const turnOffCalendarFeed = () => send<CalendarFeed>("DELETE", "/api/me/calendar-feed");
