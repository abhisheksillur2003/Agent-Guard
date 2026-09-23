"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Activity,
  BellRing,
  Bot,
  ChevronDown,
  FileClock,
  Gauge,
  KeyRound,
  Menu,
  ScrollText,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Wrench,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Brand } from "@/components/brand";
import { getCurrentUser } from "@/lib/api-client";
import { useUiStore } from "@/lib/ui-store";

const navigation = [
  { href: "/dashboard", label: "Overview", icon: Gauge },
  { href: "/dashboard/agents", label: "Agents", icon: Bot },
  { href: "/dashboard/tools", label: "Tools", icon: Wrench },
  { href: "/dashboard/policies", label: "Policies", icon: ShieldCheck },
  { href: "/dashboard/approvals", label: "Approvals", icon: KeyRound },
  { href: "/dashboard/runs", label: "Runs", icon: Activity },
  { href: "/dashboard/security", label: "Security", icon: ShieldAlert },
  { href: "/dashboard/audit", label: "Audit log", icon: FileClock },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { mobileNavigationOpen, setMobileNavigationOpen } = useUiStore();
  const session = useQuery({ queryKey: ["session"], queryFn: getCurrentUser });
  const initials = session.data?.email.slice(0, 2).toUpperCase() ?? "AG";

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="app-frame">
      <aside
        className={clsx("sidebar", mobileNavigationOpen && "sidebar-open")}
      >
        <div className="sidebar-brand">
          <Brand />
          <button
            className="icon-button sidebar-close"
            onClick={() => setMobileNavigationOpen(false)}
            aria-label="Close navigation"
          >
            <X size={20} />
          </button>
        </div>
        <nav className="primary-nav" aria-label="Primary navigation">
          <p>Control plane</p>
          {navigation.map((item) => {
            const active =
              item.href === "/dashboard"
                ? pathname === item.href
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(active && "active")}
                onClick={() => setMobileNavigationOpen(false)}
              >
                <item.icon size={18} />
                <span>{item.label}</span>
                {item.label === "Approvals" && (
                  <span className="nav-badge">2</span>
                )}
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-posture">
          <span>
            <ShieldCheck size={16} /> Security posture
          </span>
          <strong>Protected</strong>
          <p>Deterministic controls active</p>
          <div>
            <i style={{ width: "88%" }} />
          </div>
        </div>
        <footer className="sidebar-footer">
          <ScrollText size={16} />
          <span>AgentGuard v0.7</span>
        </footer>
      </aside>
      {mobileNavigationOpen && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileNavigationOpen(false)}
        />
      )}
      <div className="workspace">
        <header className="topbar">
          <button
            className="icon-button menu-button"
            onClick={() => setMobileNavigationOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={21} />
          </button>
          <div className="topbar-context">
            <span className="live-dot" />
            <span>Local control plane</span>
          </div>
          <div className="topbar-actions">
            <button className="icon-button" aria-label="Notifications">
              <BellRing size={19} />
              <i />
            </button>
            <button className="user-menu" onClick={logout} title="Sign out">
              <span>{initials}</span>
              <span>
                <strong>{session.data?.email ?? "Loading…"}</strong>
                <small>{session.data?.role ?? ""}</small>
              </span>
              <ChevronDown size={16} />
            </button>
          </div>
        </header>
        <main className="main-content">{children}</main>
      </div>
    </div>
  );
}
