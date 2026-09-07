import Link from "next/link";
import { IoArrowForward } from "react-icons/io5";
import { SourceLibrary } from "@/components/planning/SourceLibrary";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
const sources = [
  {
    name: "UPRA · EVA y calendarios",
    subtitle: "Producción local, rendimiento y temporadas",
    status: "Integrado",
    description:
      "EVA municipal 2025 y calendarios departamentales 2024. Se conserva variedad, estado del producto, área, producción y registro de origen. Los calendarios son históricos; no fijan la fecha óptima de siembra.",
    url: "https://www.datos.gov.co/resource/uejq-wxrr.json",
  },
  {
    name: "UPRA · SIPRA",
    subtitle: "Aptitud regional para 15 sistemas de cultivo",
    status: "Integrado",
    description:
      "Áreas por municipio y categoría de aptitud. Se distinguen variedades y semestres cuando corresponde. La zonificación regional no establece la aptitud de tu parcela.",
    url: "https://sipra.upra.gov.co/",
  },
  {
    name: "UPRA · Costos e insumos",
    subtitle: "Estructuras regionales y primera venta",
    status: "Integrado",
    description:
      "22 estructuras verificadas de costos de 2023 y 2024 para siete cultivos. Se mantienen los valores de ese año para editar. La biblioteca incluye precios en primer mercado de diciembre de 2025 y el índice de insumos de junio de 2026; no son cotizaciones actuales.",
    url: "https://upra.gov.co/es-co/eva/eva-2023",
  },
  {
    name: "AGROSAVIA",
    subtitle: "Contexto de suelos y referencias técnicas",
    status: "Integrado",
    description:
      "Resúmenes de muestras públicas de laboratorio por municipio, con cantidad y fechas. Son muestras por demanda: no describen el suelo de cada finca ni generan dosis de fertilizantes. Incluye la referencia técnica de papa Alhaja.",
    url: "https://www.datos.gov.co/resource/ch4u-f3i5.json",
  },
  {
    name: "Open-Meteo",
    subtitle: "Siete días para organizar las labores",
    status: "Integrado",
    description:
      "Lluvia, temperatura, probabilidad de lluvia, viento y evapotranspiración de referencia. Cada respuesta del modelo se archiva. Las tareas se derivan de reglas visibles de AgroAmigo, no de alertas oficiales. API gratuita para esta demo no comercial; la app permite configurar la API comercial.",
    url: "https://open-meteo.com/en/docs",
  },
  {
    name: "Cenicafé e ICA",
    subtitle: "Cosecha del café y vigilancia fitosanitaria",
    status: "Integrado",
    description:
      "Estudio de desarrollo del fruto según altitud, y publicación de vigilancia del café en Santander de septiembre de 2026. Se diferencia el monitoreo reportado de un brote confirmado en tu finca.",
    url: "https://publicaciones.cenicafe.org/index.php/avances_tecnicos/article/view/1964",
  },
  {
    name: "DANE · SIPSA",
    subtitle: "Precios mayoristas",
    status: "Integrado",
    description:
      "Promedios mensuales por producto y mercado, más un boletín diario separado para decisiones próximas. Se muestran en pesos colombianos por kilogramo. La fecha corresponde al cierre del mes observado, no a una cotización de hoy.",
    url: "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/mayoristas-boletin-mensual-1",
  },
  {
    name: "Federación Nacional de Cafeteros",
    subtitle: "Referencia diaria y tabla regional del café",
    status: "Integrado",
    description:
      "Precio interno de referencia por carga de 125 kg de pergamino seco; historial diario, factores de rendimiento y precios para entrega en sucursales Almacafé. Se conserva la fecha de la publicación.",
    url: "https://federaciondecafeteros.org/precio-del-cafe/",
  },
  {
    name: "Superintendencia Financiera",
    subtitle: "Tasa de cambio representativa del mercado",
    status: "Integrado",
    description:
      "TRM oficial en pesos por dólar. Ayuda a entender uno de los factores del precio del café; no se usa para convertir café tostado, cereza o futuros en pergamino seco.",
    url: "https://www.datos.gov.co/Econom-a-y-Finanzas/Tasa-de-Cambio-Representativa-del-Mercado-TRM/32sa-8pi3",
  },
  {
    name: "DANE · Abastecimiento",
    subtitle: "Cuánto producto llega a los mercados",
    status: "Boletín archivado",
    description:
      "Volúmenes de entrada y procedencias. Es útil para compradores que quieren entender la oferta de los mercados. Un ingreso reportado no equivale a inventario disponible para comprar.",
    url: "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-abastecimiento-1",
  },
  {
    name: "DANE · Insumos agropecuarios",
    subtitle: "Precios de insumos y factores de producción",
    status: "Integrado",
    description:
      "Referencias para planear costos de fertilizantes y otros insumos. Compara la formulación, la presentación y la unidad, además del precio.",
    url: "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-insumos-1",
  },
  {
    name: "IDEAM · Agroclima",
    subtitle: "Boletín agroclimático nacional",
    status: "Consultar en la fuente",
    description:
      "Información climática y recomendaciones por región para organizar labores y cosechas. Consulta el boletín oficial más reciente para tu zona.",
    url: "https://ideam.gov.co/sala-de-prensa/boletines/Bolet%C3%ADn-agroclim%C3%A1tico-nacional",
  },
  {
    name: "INVÍAS · Información vial",
    subtitle: "Planea el transporte de tu cosecha",
    status: "Consultar en la fuente",
    description:
      "Consulta información de la red vial antes de organizar una entrega. Verifica tu recorrido y los costos con el transportador.",
    url: "https://hermes2.invias.gov.co/",
  },
  {
    name: "FNC · Aprende a vender tu café",
    subtitle: "Calidad, cooperativas y condiciones de compra",
    status: "Consultar en la fuente",
    description:
      "Información para entender las bonificaciones y la garantía de compra. Los precios de compradores particulares requieren cotizaciones directas con fecha, calidad, volumen y condiciones de entrega.",
    url: "https://risaralda.federaciondecafeteros.org/servicios-al-caficultor/aprenda-a-vender-su-cafe/",
  },
];
export default function Sources() {
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">INFORMACIÓN QUE DA CONFIANZA</span>
          <h1>Conoce de dónde viene.</h1>
          <p>Fuentes públicas para tomar mejores decisiones en el campo.</p>
        </div>
      </div>
      <div className="source-grid">
        {sources.map((s) => (
          <article className="source-card" key={s.name}>
            <span
              className={
                "source-status " + (s.status === "Integrado" ? "" : "external")
              }
            >
              {s.status}
            </span>
            <h2>{s.name}</h2>
            <h3>{s.subtitle}</h3>
            <p>{s.description}</p>
            <a href={s.url} target="_blank" rel="noreferrer">
              Consultar fuente oficial <IoArrowForward />
            </a>
          </article>
        ))}
      </div>
      <section className="panel">
        <h2>Cómo pasamos del dato a una decisión</h2>
        <p>
          Rendimientos, escenarios de precio, costos, ventanas de cosecha y
          tareas del clima tienen fórmulas y supuestos visibles. Puedes
          cambiarlos y comprobar el documento de origen.
        </p>
        <EvidenceLink id="planning-method">Ver el método completo</EvidenceLink>
      </section>
      <SourceLibrary />
      <section className="faq">
        <h2>Preguntas del campo</h2>
        <details>
          <summary>¿Este es el precio que me van a pagar?</summary>
          <p>
            Es una referencia. SIPSA reporta precios de venta mayorista, que
            pueden incluir costos y márgenes posteriores a la finca. Para café,
            la FNC publica la base de su garantía de compra. El valor final
            depende de la calidad, el punto de entrega, los descuentos y las
            bonificaciones que acuerdes.
          </p>
        </details>
        <details>
          <summary>¿Por qué algunos precios no son de hoy?</summary>
          <p>
            Las fuentes tienen distintas frecuencias y demoras de publicación.
            DANE se presenta aquí como promedio mensual; FNC, como referencia
            diaria. Mostramos siempre el período real del dato. Esta demo
            conserva las observaciones recientes dentro de los últimos 12 meses.
            La historia estacional se guarda por separado: cinco años completos,
            con al menos tres años comparables para calcular escenarios. Las
            referencias técnicas conservan su año de publicación. No inventa
            registros para completar períodos faltantes.
          </p>
        </details>
        <details>
          <summary>¿Cómo se calcula el promedio de un producto?</summary>
          <p>
            Es el promedio simple de los mercados del departamento seleccionado
            que reportaron el último mes disponible de ese producto. Toda
            Colombia incluye todos los departamentos. La variación mensual solo
            aparece cuando se puede comparar el mismo conjunto de mercados con
            el mes inmediatamente anterior. El gráfico histórico promedia los
            mercados disponibles en cada mes; su cobertura puede variar.
          </p>
        </details>
        <details>
          <summary>¿Qué cambia si soy comprador?</summary>
          <p>
            Los mercados se ordenan por el menor precio y la calculadora suma el
            transporte para estimar tu presupuesto. Los precios publicados no
            indican existencias, un proveedor disponible ni una oferta de venta.
            Confirma cantidad, calidad y entrega directamente con tu proveedor.
          </p>
        </details>
        <details>
          <summary>¿Dónde se guardan mis productos?</summary>
          <p>
            Los favoritos y tus preferencias se guardan en este navegador. No
            necesitas una cuenta. El perfil de finca, las ofertas y los
            escenarios guardados permanecen en este navegador. La ubicación
            redondeada se envía al proveedor de clima y se conserva junto al
            pronóstico en Azure; los datos personales de las ofertas no se
            envían ni se publican.
          </p>
        </details>
      </section>
      <p className="privacy-note">
        <Link href="/android">Instalar AgroAmigo en Android →</Link>
        <br />
        Fotografías ilustrativas de Unsplash. AgroAmigo no está afiliado a las
        entidades que publican los datos.
      </p>
    </>
  );
}
