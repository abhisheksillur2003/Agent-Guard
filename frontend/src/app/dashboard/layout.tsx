import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { ACCESS_COOKIE } from "@/lib/server-auth";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const token = (await cookies()).get(ACCESS_COOKIE)?.value;
  const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
  if (!token && !demoMode) redirect("/login");
  return <AppShell>{children}</AppShell>;
}
