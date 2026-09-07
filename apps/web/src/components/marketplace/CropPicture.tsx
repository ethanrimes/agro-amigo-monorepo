import {
  IoLeafOutline,
  IoNutritionOutline,
  IoFishOutline,
  IoRestaurantOutline,
  IoEggOutline,
  IoGridOutline,
  IoBasketOutline,
} from "react-icons/io5";
import { productImage } from "@/lib/market-types";
export function CropPicture({
  imageKey,
  category,
  name,
}: {
  imageKey: string;
  category: string;
  name: string;
}) {
  if (imageKey !== "produce")
    return (
      <img
        src={productImage(imageKey)}
        alt={`Imagen ilustrativa: ${name}`}
        loading="lazy"
      />
    );
  const Icon =
    category === "Frutas"
      ? IoNutritionOutline
      : category === "Pescados"
        ? IoFishOutline
        : category === "Carnes"
          ? IoRestaurantOutline
          : category === "Lácteos y huevos"
            ? IoEggOutline
            : category === "Granos y cereales"
              ? IoGridOutline
              : category === "Verduras"
                ? IoLeafOutline
                : IoBasketOutline;
  return (
    <div
      className="crop-placeholder"
      role="img"
      aria-label={`Categoría: ${category}. Sin fotografía de este producto.`}
    >
      <Icon />
    </div>
  );
}
