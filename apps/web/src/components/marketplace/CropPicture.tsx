import { photoFor } from "@/lib/images";
import { IoFlowerOutline, IoLeafOutline } from "react-icons/io5";
export function CropPicture({
  category,
  name,
}: {
  imageKey?: string;
  category: string;
  name: string;
}) {
  const photo = photoFor(name, category);
  if (photo.key === "produce") {
    return (
      <div className="crop-placeholder" role="img" aria-label={`Ilustración de ${category || "producto agrícola"}`}>
        {category === "Flores" ? <IoFlowerOutline /> : <IoLeafOutline />}
      </div>
    );
  }
  return <img src={photo.src} alt={photo.alt} loading="lazy" />;
}
