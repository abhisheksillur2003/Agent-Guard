import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ACCESS_COOKIE } from "@/lib/server-auth";

export default async function Home() {
  const token = (await cookies()).get(ACCESS_COOKIE)?.value;
  const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
  redirect(token || demoMode ? "/dashboard" : "/login");
}
