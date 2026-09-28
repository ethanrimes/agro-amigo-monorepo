import Link from "next/link";
import { imageLibrary } from "@/lib/images";
export default function Credits() {
  return (
    <>
      <Link className="back-link" href="/sources">
        ← Fuentes y ayuda
      </Link>
      <div className="catalog-heading">
        <div>
          <h1>Créditos de imágenes</h1>
          <p>
            Fotografías e ilustraciones de referencia. Las variedades y los
            empaques comerciales pueden diferir.
          </p>
        </div>
      </div>
      <div className="credits-grid">
        {Object.entries(imageLibrary).map(([key, p]) => (
          <article className="panel" key={key}>
            <img src={p.src} alt={p.title} loading="lazy" />
            <h2>{p.title}</h2>
            <p>{p.author}</p>
            {p.source ? (
              <a href={p.source} target="_blank" rel="noreferrer">
                Ver origen de la imagen
              </a>
            ) : (
              <p>Origen de la imagen no documentado.</p>
            )}
            {p.licenseUrl || p.source ? (
              <a href={p.licenseUrl || p.source} target="_blank" rel="noreferrer">
                {p.license}
              </a>
            ) : (
              <p>{p.license}</p>
            )}
            {p.modifications && <p>{p.modifications}</p>}
          </article>
        ))}
      </div>
    </>
  );
}
