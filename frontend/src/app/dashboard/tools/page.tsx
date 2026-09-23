import type { Metadata } from "next";

import { ToolsView } from "@/components/registry-management";

export const metadata: Metadata = { title: "Tools" };
export default function Page() {
  return <ToolsView />;
}
