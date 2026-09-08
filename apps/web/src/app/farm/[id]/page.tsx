import { LocationWorkspace } from "@/components/location/LocationWorkspace";
export default async function FarmPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <LocationWorkspace farmId={(await params).id} />;
}
