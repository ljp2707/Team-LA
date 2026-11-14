import { useState } from "react";
import { getCalendarFeed, newCalendarFeedLink, turnOffCalendarFeed } from "../api/calendar";
import type { CalendarFeed } from "../api/calendar";
import { useApi } from "../hooks/useApi";
import { Button } from "./ui/Button";
import { Card } from "./ui/Card";
import { useToast } from "./ui/Toast";

function errorText(caught: unknown) {
  return caught instanceof Error ? caught.message : "That did not work. Please try again.";
}

/**
 * On My Tasks: an opt-in private calendar feed of every task assigned to the
 * person. Off until they turn it on. Hidden for people who cannot turn it on.
 */
export function CalendarFeedCard() {
  const toast = useToast();
  const feed = useApi(getCalendarFeed, []);
  const [busy, setBusy] = useState(false);

  if (!feed.data || !feed.data.can_turn_on) return null;
  const data = feed.data;

  async function run(action: () => Promise<CalendarFeed>, done: string) {
    setBusy(true);
    try {
      feed.setData(await action());
      toast.show(done);
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  function toggle(on: boolean) {
    if (on) {
      void run(newCalendarFeedLink, "Calendar sync is on. Add it to Google Calendar below.");
    } else if (
      window.confirm("Turn off calendar sync? Your link stops working, and your tasks leave your calendar when it next checks.")
    ) {
      void run(turnOffCalendarFeed, "Calendar sync is off.");
    }
  }

  function reset() {
    const ok = window.confirm(
      "Make a new link? The old one stops working right away, so you will need to add the new link to Google Calendar again. Use this if the link was shared by mistake.",
    );
    if (ok) void run(newCalendarFeedLink, "New link made. Add it to Google Calendar again.");
  }

  async function copy() {
    if (!data.feed_url) return;
    try {
      await navigator.clipboard.writeText(data.feed_url);
      toast.show("Link copied.");
    } catch {
      toast.error("Could not copy. Select the link and copy it instead.");
    }
  }

  return (
    <Card>
      <h2>Calendar</h2>
      <label className="check-option">
        <input type="checkbox" checked={data.enabled} disabled={busy} onChange={(e) => toggle(e.target.checked)} />
        Sync all my tasks to Google Calendar
      </label>
      {data.enabled && data.feed_url && data.google_url ? (
        <div className="calendar-feed">
          <a className="button button--primary button--sm" href={data.google_url} target="_blank" rel="noreferrer">
            Add to Google Calendar
          </a>
          <div className="inline-form">
            <label className="visually-hidden" htmlFor="calendar-feed-url">
              Your private calendar link
            </label>
            <input
              id="calendar-feed-url"
              className="input"
              value={data.feed_url}
              readOnly
              onFocus={(e) => e.target.select()}
            />
            <Button variant="outline" size="sm" onClick={() => void copy()}>
              Copy
            </Button>
          </div>
          <p className="muted small">
            New tasks and changes can take several hours to appear. Keep this link private: anyone with it can see your tasks.
          </p>
          <div className="inline-actions">
            <button type="button" className="text-button" disabled={busy} onClick={reset}>
              Reset link
            </button>
            <button type="button" className="text-button" disabled={busy} onClick={() => toggle(false)}>
              Turn off
            </button>
          </div>
        </div>
      ) : (
        <p className="muted small">Your open tasks with due dates appear on your calendar and stay up to date. Off until you turn it on.</p>
      )}
    </Card>
  );
}
