import { photoFor } from "@/lib/images";
export function CropPicture({
  category,
  name,
}: {
  imageKey?: string;
  category: string;
  name: string;
}) {
  const photo = photoFor(name, category);
  return <img src={photo.src} alt={photo.alt} loading="lazy" />;
}
