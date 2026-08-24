"use client";

import { use } from "react";

import { EvidencePackView } from "@/components/incident-views";

export default function EvidencePackRoute({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <EvidencePackView packId={id} />;
}
