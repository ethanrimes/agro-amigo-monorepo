import { Suspense } from "react";
import { ComparisonWorkspace } from "@/components/comparison/ComparisonWorkspace";
export default function CompareInputsPage() {
  return (
    <Suspense fallback={<p role="status">Cargando comparación…</p>}>
      <ComparisonWorkspace kind="inputs" />
    </Suspense>
  );
}
