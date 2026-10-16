"use client";
import { useState } from "react";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import type { MapPoint } from "@/lib/explore-types";

/** Every original contributing to a monthly total remains independently readable. */
export function SupplyMapEvidence({ point, product, productName }: {
  point: MapPoint; product?: string; productName?: string;
}) {
  const sources = [...(point.sources || [])].sort((a, b) =>
    (a.title || "").localeCompare(b.title || "", "es") || a.document_id.localeCompare(b.document_id));
  const [chosen, setChosen] = useState("");
  const source = sources.find((item) => item.document_id === chosen) || sources[0];
  return <>
    {sources.length > 1 && <SearchableSelect
      label="Archivo de abastecimiento"
      value={source.document_id}
      options={sources.map((item, index) => ({ id: item.document_id,
        label: item.title || `Fuente conservada ${index + 1}` }))}
      allowClear={false}
      onChange={setChosen}
    />}
    <EvidenceLink id={source?.document_id} product={product} productName={productName}
      market={point.id} marketName={point.name} department={point.region}
      units="kg" month={point.period_start}>
      Consultar fuente
    </EvidenceLink>
  </>;
}
