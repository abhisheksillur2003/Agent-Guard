import "server-only";

export const ACCESS_COOKIE = "agentguard_access_token";

export function apiBaseUrl(): string {
  return (process.env.AGENTGUARD_API_URL ?? "http://127.0.0.1:8000").replace(
    /\/$/,
    "",
  );
}

export const accessCookieOptions = {
  httpOnly: true,
  sameSite: "lax" as const,
  secure: process.env.NODE_ENV === "production",
  path: "/",
  maxAge: 30 * 60,
};
