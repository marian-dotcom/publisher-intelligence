"use client";

import { use } from "react";

import { IncidentDetailView } from "@/components/incident-views";

export default function IncidentDetailRoute({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <IncidentDetailView incidentId={id} />;
}
