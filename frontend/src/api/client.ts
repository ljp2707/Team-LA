/** Small wrapper around fetch for talking to our own backend. */

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Turn FastAPI's error body into one plain sentence. */
function detailMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string; loc?: unknown[] };
      const message = (first.msg ?? "Check the form").replace(/^Value error, /, "");
      const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1]) : "";
      return field && field !== "body" ? `${field.replace(/_/g, " ")}: ${message}` : message;
    }
  }
  if (status === 403) return "You do not have access to do that.";
  if (status === 404) return "That could not be found.";
  if (status >= 500) return "Something went wrong on the server. Please try again.";
  return "That did not work. Please try again.";
}

/** Fetch from our backend and turn any error answer into an ApiError with one plain sentence. */
async function request(path: string, options: RequestInit = {}): Promise<Response> {
  let response: Response;
  // A FormData body (a file upload) sets its own Content-Type with the boundary.
  const json = !(options.body instanceof FormData);
  try {
    response = await fetch(path, {
      ...options,
      credentials: "include",
      headers: { ...(json ? { "Content-Type": "application/json" } : {}), ...options.headers },
    });
  } catch {
    throw new ApiError(0, "Could not reach NMU Launches. Check your connection.");
  }

  if (!response.ok) {
    // A session that ended sends the person back to sign in. /api/me is the
    // exception, since a 401 there just means nobody is signed in yet.
    if (response.status === 401 && path !== "/api/me") {
      window.location.assign("/");
    }
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw new ApiError(response.status, detailMessage(body, response.status));
  }
  return response;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await request(path, options);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

/**
 * Download a file the backend makes (such as a CSV export) and save it with the
 * name the server gives in Content-Disposition. Errors arrive as ApiError, so the
 * page can show them as a toast instead of opening a raw error page.
 */
export async function download(path: string, fallbackName: string): Promise<string> {
  const response = await request(path);
  const header = response.headers.get("Content-Disposition") ?? "";
  const name = /filename="?([^";]+)"?/.exec(header)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Give the browser a moment to start the download before freeing the file.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  return name;
}

export const get = <T>(path: string) => api<T>(path);

export const send = <T>(method: "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown) =>
  api<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

/** Send a file from the person's computer as a form, with any extra text fields. */
export function upload<T>(path: string, file: File, fields: Record<string, string> = {}) {
  const form = new FormData();
  form.append("file", file);
  for (const [name, value] of Object.entries(fields)) form.append(name, value);
  return api<T>(path, { method: "POST", body: form });
}

/** Build a query string, leaving out empty values. */
export function query(params: Record<string, string | null | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v) as [string, string][];
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
}
