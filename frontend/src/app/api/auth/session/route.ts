import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  ACCESS_COOKIE,
  accessCookieOptions,
  apiBaseUrl,
} from "@/lib/server-auth";

export async function GET(): Promise<NextResponse> {
  const token = (await cookies()).get(ACCESS_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ authenticated: false }, { status: 401 });
  }
  try {
    const upstream = await fetch(`${apiBaseUrl()}/api/v1/auth/me`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!upstream.ok) {
      const response = NextResponse.json(
        { authenticated: false },
        { status: 401 },
      );
      response.cookies.set(ACCESS_COOKIE, "", {
        ...accessCookieOptions,
        maxAge: 0,
      });
      return response;
    }
    return NextResponse.json({
      authenticated: true,
      user: await upstream.json(),
    });
  } catch {
    return NextResponse.json(
      { message: "AgentGuard API is unavailable" },
      { status: 503 },
    );
  }
}
