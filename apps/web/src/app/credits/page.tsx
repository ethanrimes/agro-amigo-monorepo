"use client";

import Link from "next/link";
import { useState } from "react";
import { imageLibrary } from "@/lib/images";
import { SearchableSelect } from "@/components/ui/SearchableSelect";

const creditOptions = Object.entries(imageLibrary).map(([key, photo]) => ({
  id: key,
  label: photo.title,
  detail: `${photo.description} · ${photo.author} · ${photo.license}`,
}));

export default function Credits() {
  const [selectedImage, setSelectedImage] = useState("");
  const p = imageLibrary[selectedImage];
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
      <SearchableSelect
        label="Consultar los créditos de una imagen"
        placeholder="Busca imagen, producto, autor o licencia…"
        emptyLabel="Elige una imagen para consultar su autor, licencia y origen"
        value={selectedImage}
        onChange={setSelectedImage}
        options={creditOptions}
      />
      <p>{creditOptions.length} imágenes con sus créditos conservados.</p>
      <div className="credits-grid">
        {p ? (
          <article className="panel" key={selectedImage}>
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
        ) : <p>Busca y elige una imagen para ver sus créditos.</p>}
      </div>
    </>
  );
}
