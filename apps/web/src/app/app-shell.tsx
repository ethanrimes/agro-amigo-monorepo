"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  IoLeafOutline,
  IoHomeOutline,
  IoBasketOutline,
  IoStorefrontOutline,
  IoFlaskOutline,
  IoHeartOutline,
  IoHelpCircleOutline,
  IoLocationOutline,
} from "react-icons/io5";
const links = [
  { href: "/", label: "Inicio", icon: IoHomeOutline },
  { href: "/products", label: "Productos", icon: IoBasketOutline },
  { href: "/markets", label: "Mercados", icon: IoStorefrontOutline },
  { href: "/insumos", label: "Insumos", icon: IoFlaskOutline },
  { href: "/farm", label: "Mi finca", icon: IoLeafOutline },
];
export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const selected = (href: string) =>
    href === "/"
      ? path === "/"
      : path === href ||
        path.startsWith(href + "/") ||
        (href === "/products" &&
          (path.startsWith("/product/") ||
            ["/coffee", "/daily", "/saved"].includes(path))) ||
        (href === "/markets" && path.startsWith("/market/")) ||
        (href === "/insumos" && path.startsWith("/insumo/")) ||
        (href === "/farm" && ["/plan", "/offers"].includes(path));
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Ir al contenido
      </a>
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="AgroAmigo, inicio">
          <span className="brand-mark">
            <IoLeafOutline />
          </span>
          agro<span>amigo</span>
        </Link>
        <div className="sidebar-caption">EL CAMPO, A TU ALCANCE</div>
        <nav aria-label="Navegación principal">
          {links.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={"nav-link " + (selected(href) ? "active" : "")}
              aria-current={
                selected(href)
                  ? path === href
                    ? "page"
                    : "location"
                  : undefined
              }
            >
              <Icon />
              {label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <Link className="help-link" href="/saved">
            <IoHeartOutline />
            Mis guardados
          </Link>
          <Link className="help-link" href="/sources">
            <IoHelpCircleOutline />
            Fuentes y ayuda
          </Link>
          <div className="made-in">
            <span className="colombia-flag" />
            Hecho para Colombia
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <Link href="/" className="mobile-brand">
            <IoLeafOutline /> agroamigo
          </Link>
          <span className="topbar-message">
            <IoLocationOutline /> Colombia · Información para el campo
          </span>
          <div className="topbar-actions">
            <Link
              href="/saved"
              className="topbar-icon"
              aria-label="Mis guardados"
            >
              <IoHeartOutline />
            </Link>
            <Link
              href="/sources"
              className="topbar-icon"
              aria-label="Fuentes y ayuda"
            >
              <IoHelpCircleOutline />
            </Link>
          </div>
        </header>
        <main
          id="main-content"
          className="app-content"
          data-section={path.split("/")[1] || "home"}
        >
          {children}
        </main>
        <footer className="site-footer">
          <span>AgroAmigo · Del campo, para el campo.</span>
          <Link href="/sources">Fuentes y ayuda</Link>
          <Link href="/credits">Créditos de imágenes</Link>
        </footer>
      </div>
      <nav className="mobile-nav" aria-label="Navegación móvil">
        {links.map(({ href, label, icon: Icon }) => (
          <Link
            href={href}
            key={href}
            className={selected(href) ? "active" : ""}
            aria-current={
              selected(href) ? (path === href ? "page" : "location") : undefined
            }
          >
            <Icon />
            <span>{label}</span>
          </Link>
        ))}
      </nav>
    </div>
  );
}
