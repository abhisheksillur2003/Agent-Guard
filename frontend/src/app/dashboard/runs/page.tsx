import type { Metadata } from "next";

import { RunsView } from "@/components/resource-views";

export const metadata: Metadata = { title: "Runs" };
export default function Page() {
  return <RunsView />;
}
