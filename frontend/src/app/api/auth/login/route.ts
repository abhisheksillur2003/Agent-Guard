import { NextResponse } from "next/server";

import {
  ACCESS_COOKIE,
  accessCookieOptions,
  apiBaseUrl,
} from "@/lib/server-auth";

type LoginBody = { email?: string; password?: string };
type TokenResponse = { access_token: string; token_type: string };

export async function POST(request: Request): Promise<NextResponse> {
  let body: LoginBody;
  try {
    body = (await request.json()) as LoginBody;
  } catch {
    return NextResponse.json(
      { message: "Invalid login request" },
      { status: 400 },
    );
  }
  if (!body.email || !body.password) {
    return NextResponse.json(
      { message: "Email and password are required" },
      { status: 400 },
    );
  }

  try {
    const upstream = await fetch(`${apiBaseUrl()}/api/v1/auth/token`, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        username: body.email,
        password: body.password,
      }),
      cache: "no-store",
    });
    if (!upstream.ok) {
      return NextResponse.json(
        {
          message:
            upstream.status === 401
              ? "Invalid email or password"
              : "Login failed",
        },
        { status: upstream.status },
      );
    }
    const token = (await upstream.json()) as TokenResponse;
    const response = NextResponse.json({ authenticated: true });
    response.cookies.set(
      ACCESS_COOKIE,
      token.access_token,
      accessCookieOptions,
    );
    return response;
  } catch {
    return NextResponse.json(
      {
        message:
          "AgentGuard API is unavailable. Start the backend and try again.",
      },
      { status: 503 },
    );
  }
}
