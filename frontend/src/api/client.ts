/** Small wrapper around fetch for talking to our own backend. */

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...options.headers },
  });

  if (!response.ok) {
    // A session that ended sends the person back to sign in. /api/me is the
    // exception, since a 401 there just means nobody is signed in yet.
    if (response.status === 401 && path !== "/api/me") {
      window.location.assign("/");
    }
    throw new ApiError(response.status, `Request failed: ${path}`);
  }
  return response.json() as Promise<T>;
}
