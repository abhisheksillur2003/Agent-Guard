import type { Metadata } from "next";

import { SettingsView } from "@/components/resource-views";

export const metadata: Metadata = { title: "Settings" };
export default function Page() {
  return <SettingsView />;
}
