import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { DemoCommandCenter } from "../../components/DemoCommandCenter";
import { isDemoTourEnabled } from "../../lib/demo-tour-access";

export const metadata: Metadata = {
  title: "FounderOS — живой штаб компании",
  description:
    "Изолированный живой штаб FounderOS с контекстным ассистентом на вымышленных данных.",
  robots: {
    follow: false,
    index: false
  }
};

export default function DemoPage() {
  if (
    !isDemoTourEnabled(
      process.env.NODE_ENV,
      process.env.FOUNDEROS_DEMO_ENABLED
    )
  ) {
    notFound();
  }

  return <DemoCommandCenter />;
}
