import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { DemoProductTour } from "../../components/DemoProductTour";
import { isDemoTourEnabled } from "../../lib/demo-tour-access";

export const metadata: Metadata = {
  title: "FounderOS — интерактивный демо-тур",
  description:
    "Изолированный интерактивный показ полного цикла FounderOS на вымышленных данных.",
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

  return <DemoProductTour />;
}
