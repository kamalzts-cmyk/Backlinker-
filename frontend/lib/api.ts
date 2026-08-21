// The one place this app talks to the FastAPI backend. Every call runs
// server-side (Server Components for reads, Server Actions for writes)
// so the browser never talks to the backend directly -- no CORS config
// needed on the backend, and API_URL never reaches the client bundle.
//
// See ../../docs/API.md's error convention: every error response is
// `{"error": {"code","message","detail"}}`. ApiError below carries that
// through so callers can show the backend's real message, not a generic
// "something went wrong."

const API_URL = process.env.API_URL ?? "http://localhost:8000";

// Sent on every backend call so the backend's SharedSecretMiddleware
// (app/api/auth_gate.py) lets it through. Unset in local dev, where the
// backend doesn't enforce it either -- see docs/DEPLOYMENT.md.
const APP_SHARED_SECRET = process.env.APP_SHARED_SECRET;

export class ApiError extends Error {
  status: number;
  code: string | null;

  constructor(status: number, code: string | null, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(
  path: string,
  init?: RequestInit & { params?: Record<string, string | number | boolean | undefined | null> }
): Promise<T> {
  const url = new URL(path, API_URL);
  if (init?.params) {
    for (const [key, value] of Object.entries(init.params)) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
  }

  const response = await fetch(url, {
    ...init,
    cache: "no-store", // every resource here changes on other people's actions; never serve stale
    headers: {
      "Content-Type": "application/json",
      ...(APP_SHARED_SECRET ? { "x-app-secret": APP_SHARED_SECRET } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let code: string | null = null;
    let message = `request to ${path} failed with status ${response.status}`;
    try {
      const body = await response.json();
      code = body?.error?.code ?? null;
      message = body?.error?.message ?? message;
    } catch {
      // non-JSON error body -- keep the generic message above
    }
    throw new ApiError(response.status, code, message);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function apiGet<T>(
  path: string,
  params?: Record<string, string | number | boolean | undefined | null>
): Promise<T> {
  return request<T>(path, { method: "GET", params });
}

/** Like apiGet, but returns null on a 404 instead of throwing --
 * for resources that genuinely might not exist yet (e.g. no outreach
 * strategy has been generated for a contact yet), where that's a normal
 * state to render, not an error to surface.
 */
export async function apiGetOrNull<T>(
  path: string,
  params?: Record<string, string | number | boolean | undefined | null>
): Promise<T | null> {
  try {
    return await apiGet<T>(path, params);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export function apiPost<T>(
  path: string,
  body?: unknown,
  params?: Record<string, string | number | boolean | undefined | null>
): Promise<T> {
  return request<T>(path, {
    method: "POST",
    params,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export { API_URL };
