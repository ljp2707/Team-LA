/**
 * The link if it is safe to put in an href, otherwise null.
 *
 * Allows https links and this site's own paths (such as /api/links/{id}/file). Anything
 * else, such as a "javascript:" link typed straight into Airtable, could run code when
 * clicked, so it is shown as plain text instead (security findings F7).
 */
export function safeHref(url: string | null | undefined): string | null {
  const value = (url ?? "").trim();
  if (/^https:\/\//i.test(value)) return value;
  if (value.startsWith("/") && !value.startsWith("//")) return value;
  return null;
}
