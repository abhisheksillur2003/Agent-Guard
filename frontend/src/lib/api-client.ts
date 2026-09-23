import { demoResponse, demoUser } from "@/lib/demo-data";
import type { CurrentUser } from "@/lib/types";

export const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly requestId?: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method ?? "GET";
  if (demoMode) {
    await new Promise((resolve) => setTimeout(resolve, 180));
    return demoResponse(path, method) as T;
  }
  const response = await fetch(`/api/backend${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as {
        error?: { message?: string };
        message?: string;
      };
      message = body.error?.message ?? body.message ?? message;
    } catch {
      // Preserve the sanitized status message when the upstream body is not JSON.
    }
    throw new ApiError(
      message,
      response.status,
      response.headers.get("x-request-id") ?? undefined,
    );
  }
  return (await response.json()) as T;
}

export const apiGet = <T>(path: string) => request<T>(path);
export const apiPost = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });
export const apiPatch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const apiPut = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const apiDelete = <T>(path: string) =>
  request<T>(path, { method: "DELETE" });

export async function getCurrentUser(): Promise<CurrentUser> {
  if (demoMode) return demoUser;
  const response = await fetch("/api/auth/session", { cache: "no-store" });
  if (!response.ok) throw new Error("Your session has expired");
  const data = (await response.json()) as { user: CurrentUser };
  return data.user;
}
