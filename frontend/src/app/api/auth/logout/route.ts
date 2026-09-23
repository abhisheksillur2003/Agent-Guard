import { NextResponse } from "next/server";

import { ACCESS_COOKIE, accessCookieOptions } from "@/lib/server-auth";

export async function POST(): Promise<NextResponse> {
  const response = NextResponse.json({ authenticated: false });
  response.cookies.set(ACCESS_COOKIE, "", {
    ...accessCookieOptions,
    maxAge: 0,
  });
  return response;
}
