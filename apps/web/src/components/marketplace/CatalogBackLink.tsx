"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

export function CatalogBackLink() {
  const [href, setHref] = useState("/products");
  useEffect(() => {
    const value = new URLSearchParams(window.location.search).get("returnTo");
    if (!value) return;
    try {
      const target = new URL(value, window.location.origin);
      if (
        target.origin === window.location.origin &&
        ["/products", "/saved"].includes(target.pathname)
      ) {
        setHref(target.pathname + target.search);
      }
    } catch {
      // Older or malformed links still return to the unified product catalog.
    }
  }, []);
  return <Link className="back-link" href={href}>← Volver a productos</Link>;
}
