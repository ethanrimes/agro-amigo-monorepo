"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  IoLeafOutline,
  IoHomeOutline,
  IoSearchOutline,
  IoCafeOutline,
  IoHeartOutline,
  IoArrowForward,
  IoLocationOutline,
  IoChevronDown,
  IoHelpCircleOutline,
  IoStorefrontOutline,
} from "react-icons/io5";
import { usePreferences } from "@/components/marketplace/Preferences";
const links = [
  { href: "/", label: "Inicio", icon: IoHomeOutline },
  { href: "/farm", label: "Mi finca", mobile: "Mi finca", icon: IoLeafOutline },
  {
    href: "/products",
    label: "Consultar precios",
    mobile: "Precios",
    icon: IoSearchOutline,
  },
  { href: "/coffee", label: "Mi café", mobile: "Café", icon: IoCafeOutline },
  {
    href: "/saved",
    label: "Mis productos",
    mobile: "Guardados",
    icon: IoHeartOutline,
  },
];
export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { role, setRole, region, setRegion } = usePreferences();
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Ir al contenido
      </a>
      <aside className="sidebar">
        <Link href="/" className="brand" aria-label="AgroAmigo, inicio">
          <span className="brand-mark">
            <IoLeafOutline />
          </span>
          agro<span>amigo</span>
          <i />
        </Link>
        <div className="sidebar-caption">TU COMPAÑERO EN EL CAMPO</div>
        <nav aria-label="Navegación principal">
          {links.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={
                "nav-link " +
                ((
                  href === "/"
                    ? path === "/"
                    : path.startsWith(href) || (href === "/farm" && ["/plan", "/offers"].includes(path)) ||
                      (href === "/products" && path.startsWith("/product/"))
                )
                  ? "active"
                  : "")
              }
              aria-current={path === href ? "page" : undefined}
            >
              <Icon />
              {label}
              {href === "/coffee" && <span className="nav-new">NUEVO</span>}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="field-note">
            <span className="little-sun">✳</span>
            <h3>
              La información también
              <br />
              da frutos.
            </h3>
            <p>
              Conoce tus precios.
              <br />
              Negocia con confianza.
            </p>
            <Link href="/sources">
              Conoce nuestras fuentes <IoArrowForward />
            </Link>
          </div>
          <Link className="help-link" href="/sources">
            <IoHelpCircleOutline /> Fuentes y ayuda
          </Link>
          <div className="made-in">
            <span className="colombia-flag" /> Hecho para el campo colombiano
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <Link href="/" className="mobile-brand">
            <IoLeafOutline /> agroamigo<span>.</span>
          </Link>
          <span className="topbar-message">Del campo, para el campo.</span>
          <div className="topbar-actions">
            <label className="location-select">
              <IoLocationOutline />
              <span className="sr-only">Departamento</span>
              <select
                aria-label="Departamento"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
              >
                <option value="">Toda Colombia</option>
                <option>Amazonas</option>
                <option>Antioquia</option>
                <option>Arauca</option>
                <option>Atlántico</option>
                <option>Bogotá, D.C.</option>
                <option>Bolívar</option>
                <option>Boyacá</option>
                <option>Caldas</option>
                <option>Caquetá</option>
                <option>Casanare</option>
                <option>Cauca</option>
                <option>Cesar</option>
                <option>Chocó</option>
                <option>Córdoba</option>
                <option>Cundinamarca</option>
                <option>Guainía</option>
                <option>Guaviare</option>
                <option>Huila</option>
                <option>La Guajira</option>
                <option>Magdalena</option>
                <option>Meta</option>
                <option>Nariño</option>
                <option>Norte de Santander</option>
                <option>Putumayo</option>
                <option>Quindío</option>
                <option>Risaralda</option>
                <option>San Andrés y Providencia</option>
                <option>Santander</option>
                <option>Sucre</option>
                <option>Tolima</option>
                <option>Valle del Cauca</option>
                <option>Vaupés</option>
                <option>Vichada</option>
              </select>
              <IoChevronDown />
            </label>
            <span className="topbar-divider" />
            <span className="profile-icon">
              {role === "farmer" ? <IoLeafOutline /> : <IoStorefrontOutline />}
            </span>
          </div>
        </header>
        <main id="main-content" className="app-content" data-section={path.split("/")[1] || "home"}>
          {children}
        </main>
        <footer className="site-footer">
          <span>AgroAmigo · Juntos, el campo crece.</span>
          <Link href="/sources">
            Datos abiertos. Decisiones informadas. <IoArrowForward />
          </Link>
        </footer>
      </div>
      <nav className="mobile-nav" aria-label="Navegación móvil">
        {links.map(({ href, label, mobile, icon: Icon }) => (
          <Link
            href={href}
            key={href}
            className={path === href ? "active" : ""}
          >
            <Icon />
            <span>{mobile || label}</span>
          </Link>
        ))}
      </nav>
    </div>
  );
}
