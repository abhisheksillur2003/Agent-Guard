import type { Metadata } from "next";

import { PoliciesView } from "@/components/resource-views";

export const metadata: Metadata = { title: "Policies" };
export default function Page() {
  return <PoliciesView />;
}
