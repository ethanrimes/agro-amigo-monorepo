"use client";
import Link from "next/link";
import {
  IoPartlySunnyOutline,
  IoLeafOutline,
  IoSwapHorizontalOutline,
} from "react-icons/io5";
import { useFarm } from "./FarmContext";
import { usePreferences } from "@/components/marketplace/Preferences";
export function HomeActions() {
  const { farm } = useFarm(),
    { role } = usePreferences();
  return (
    <section className="home-decisions">
      <div className="section-heading">
        <div>
          <span className="eyebrow">INFORMACIÓN PARA ACTUAR</span>
          <h2>¿Qué necesitas decidir hoy?</h2>
        </div>
        {farm.municipalityId && (
          <Link className="text-link" href="/farm">
            Ir a {farm.name} →
          </Link>
        )}
      </div>
      <div className="decision-grid">
        <Link className="decision-card decision-photo decision-weather" href="/farm">
          <div className="decision-art"><img src="/images/farm.jpg" alt="" /><span>01 · MI SEMANA</span></div>
          <IoPartlySunnyOutline />
          <h3>Organizar mi semana</h3>
          <p>Clima y avisos útiles para tu cultivo y ubicación.</p>
          <span>Ver mi plan de trabajo →</span>
        </Link>
        <Link className="decision-card decision-photo decision-crops" href="/plan">
          <div className="decision-art"><img src="/images/avocado.jpg" alt="" /><span>02 · MI PRÓXIMA COSECHA</span></div>
          <IoLeafOutline />
          <h3>
            {role === "buyer"
              ? "Conocer zonas productoras"
              : "Elegir qué sembrar"}
          </h3>
          <p>Cultivos, costos y escenarios de cosecha para cada zona.</p>
          <span>Explorar y hacer cuentas →</span>
        </Link>
        <Link className="decision-card decision-photo decision-sales" href="/offers">
          <div className="decision-art"><img src="/images/produce.jpg" alt="" /><span>03 · MIS CUENTAS</span></div>
          <IoSwapHorizontalOutline />
          <h3>
            {role === "buyer" ? "Comparar proveedores" : "Comparar mis ofertas"}
          </h3>
          <p>Incluye transporte, descuentos y plazo de pago.</p>
          <span>Comparar el valor final →</span>
        </Link>
      </div>
    </section>
  );
}
