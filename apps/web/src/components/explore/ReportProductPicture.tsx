import { photoFor } from "@/lib/images";
import styles from "./report-product-picture.module.css";

export function ReportProductPicture({ name }: { name: string }) {
  const photo = photoFor(name);
  return (
    <div className={styles.picture}>
      <img src={photo.src} alt={photo.alt} loading="lazy" />
      <span>Imagen ilustrativa</span>
    </div>
  );
}
