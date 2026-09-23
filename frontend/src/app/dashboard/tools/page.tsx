import type { Metadata } from "next";

import { ToolsView } from "@/components/resource-views";

export const metadata: Metadata = { title: "Tools" };
export default function Page() {
  return <ToolsView />;
}
