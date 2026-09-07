# Application and data architecture

The active product has a Next.js web app, an Android client and a Flutter iOS client using the same Azure origin. No Supabase dependency remains. Both mobile clients add native navigation, document downloads/sharing, JSON export and connection recovery without duplicating product logic. The iOS client retains the existing TestFlight app identity and uses WKWebView.

## Recorridos de usuario

Las cinco secciones son **Inicio, Productos, Mercados, Insumos y Mi finca**. Web, iOS y Android comparten la interfaz en español. Ya no existe un selector de comprador/agricultor.

```mermaid
flowchart TB
    app["AgroAmigo · Web / iOS / Android"]
    app --> inicio["1 · Inicio<br/>Buscar y acceder a las consultas"]
    app --> productos["2 · Productos<br/>Productos agrícolas y café"]
    app --> mercados["3 · Mercados<br/>Plazas y puntos de entrega"]
    app --> insumos["4 · Insumos<br/>Producto, fabricante y presentación"]
    app --> fincas["5 · Mi finca<br/>Todas tus fincas"]
    productos --> producto["Detalle del producto<br/>Precios / Abastecimiento"]
    productos --> cafe["Detalle del café<br/>Referencia FNC, calidad y entrega"]
    mercados --> mercado["Detalle del mercado<br/>Precios / Abastecimiento"]
    insumos --> insumo["Detalle del insumo<br/>Precios / Abastecimiento"]
    productos & mercados & insumos --> mapa["Ver mapa<br/>Mapa interactivo de Colombia"]
    producto & cafe & mercado & insumo --> documento["Comprobar dato<br/>Visor emergente y descarga"]
    fincas --> finca["Una finca<br/>Ubicación y cultivos"]
    finca --> cuentas["Mis cuentas<br/>Costos, ingresos y utilidad estimada"]
    finca --> cultivos["Mis cultivos<br/>Áreas, rendimientos y presupuestos"]
    finca --> clima["Clima y labores<br/>Pronóstico y sugerencias de trabajo"]
```

| Sección | Ruta | Contenido |
| --- | --- | --- |
| Inicio | `/` | Búsqueda con sugerencias, accesos con imágenes, productos destacados y acceso a Mi finca. |
| Productos | `/products` | Filtros de departamento/categoría, favoritos y mapa. Detalle: `/product/[id]`. El café está en `/product/cafe-pergamino-seco`. |
| Mercados | `/markets` | Directorio con búsqueda y mapa. `/market/[id]` muestra precios de cada producto y volúmenes reportados. |
| Insumos | `/insumos` | Identidades y presentaciones comparables. `/insumo/[id]` muestra historia y comparación departamental. |
| Mi finca | `/farm` | Lista y registro de fincas. `/farm/[id]` contiene mapa con pin, cultivos, cuentas y clima. `/plan` y `/offers` mantienen seleccionada esta sección. |

**Mis guardados** está en el corazón del encabezado, en `/saved`. **Fuentes y ayuda** y **Créditos de imágenes** están en el encabezado o pie. No son pestañas adicionales. Un detalle conserva seleccionada su sección principal.

### Consultar precios y abastecimiento

```mermaid
flowchart LR
    buscar["Escribir un nombre<br/>Sugerencias filtradas"] --> detalle["Abrir producto, mercado o insumo"]
    detalle --> vista{"Elegir información"}
    vista --> precio["Precios<br/>Valor, unidad, fecha e historia"]
    vista --> abastecimiento["Abastecimiento<br/>Mes, toneladas y días reportados"]
    precio & abastecimiento --> fuente["Comprobar dato"]
    fuente --> visor["Visor sobre la misma página"]
    visor --> volver["Cerrar o volver<br/>Conservar selección y posición"]
```

El abastecimiento suma filas originales de DANE SIPSA-A por alimento, mercado de destino y mes. Muestra primera/última fecha y días con reportes. Un mes parcial se conserva parcial. Son **llegadas reportadas, no inventario disponible para comprar**. Los alimentos sin correspondencia exacta con el catálogo mantienen su nombre original; no se mezclan variedades por semejanza.

En insumos, **Abastecimiento** explica que SIPSA-I no publica inventarios de proveedores y permite consultar la cobertura de precios. El café pergamino y otros productos sin volúmenes comparables muestran esa ausencia. No se interpreta una serie ausente como cero producción.

### Abrir el mapa desde cada catálogo

```mermaid
flowchart LR
    catalogo["Productos / Mercados / Insumos"] --> abrir["Ver mapa"]
    abrir --> filtros["Elegir producto o presentación<br/>Precio o abastecimiento"]
    filtros --> mapa["Colombia en MapLibre<br/>Departamentos y mercados agrupados"]
    mapa --> punto["Tocar departamento o mercado<br/>Ver referencias fechadas"]
    punto --> detalle["Abrir detalle o comprobar fuente"]
```

Se incluyen los límites departamentales restaurados, una base OpenStreetMap, sombreado por departamento y agrupación de puntos. Se compara el mismo producto, fecha y unidad; el café conserva COP/125 kg. En insumos se conserva la presentación. El panorama de mercados cuenta referencias de productos, sin promediar precios de alimentos distintos. Los puntos de mercados son referencias municipales, no direcciones verificadas. Los controles del mapa están en español; sus dos módulos de trabajo se copian al preparar el build para que también se dibujen polígonos y puntos en Next.js/WebKit.

### Comprobar el origen de un dato

```mermaid
flowchart TD
    dato["Precio, volumen, costo o rendimiento"] --> enlace["Enlace junto al dato"]
    enlace --> visor["Visor emergente"]
    visor --> pdf["PDF<br/>Páginas, miniaturas, zoom y texto"]
    visor --> filas["Excel o JSON<br/>Registros coincidentes y fila original"]
    pdf & filas --> descarga["Descargar original archivado en Azure"]
    visor --> trazabilidad["Publicador, período, consulta y SHA-256"]
    visor --> original["Extracto generado → archivo original"]
```

Azure PostgreSQL guarda copias inmutables de los documentos. Un PDF oficial se conserva intacto; un PDF generado por AgroAmigo se identifica como extracto y enlaza al libro original. Los XLSX se presentan con sus registros y descarga, sin fingir que son PDF. El visor conserva el foco, responde a Escape/Atrás y devuelve al elemento que lo abrió. `/evidence/[id]` permite enlaces directos.

### Registrar varias fincas y llevar sus cuentas

```mermaid
flowchart TD
    lista["Mis fincas"] --> registro["Agregar finca<br/>Nombre, municipio y área total"]
    registro --> ubicacion["Poner pin en mapa o usar GPS<br/>Confirmar municipio"]
    ubicacion --> detalle["Detalle de la finca<br/>Mapa con su pin guardado"]
    detalle --> cultivos["Agregar cultivos o lotes<br/>Hectáreas, variedad, estado y rendimiento"]
    cultivos --> presupuesto["Presupuesto por cultivo<br/>Año o ciclo, costos y precio esperado"]
    presupuesto --> evidencia["Revisar referencias<br/>UPRA, EVA, SIPSA y FEPCafé"]
    presupuesto --> aplicar["Aplicar presupuesto al cultivo"]
    aplicar --> resumen["Mis cuentas<br/>Ingresos, costos, utilidad y caja previa"]
    resumen --> escenarios["Escenarios bajo, central y alto<br/>Equilibrio por kg y aportes por cultivo"]
    detalle --> labores["Clima y labores del cultivo elegido"]
    detalle --> exportar["Descargar datos de esta finca"]
```

Cada finca tiene identificador, perfil, pin y cultivos propios. Cada cultivo conserva área, variedad/lote, estado del producto, rendimiento esperado, año, etapa, riego y fechas opcionales. La suma de áreas no puede superar la finca. Cambiar área, rendimiento, cultivo, estado del producto o año obliga a recalcular el presupuesto; cambiar de municipio invalida los presupuestos vinculados a las referencias anteriores.

El resumen agrupa presupuestos del **mismo año y tipo de período**: establecimiento, año en producción o un ciclo por cultivo. No suma períodos incompatibles ni convierte automáticamente ciclos en años. Los costos incluyen producción, gastos de venta y comisión; la utilidad es ingreso menos esos costos. La caja antes de cosechar suma las labores marcadas para ese momento. El equilibrio se muestra por cultivo: no se promedian kilogramos de productos diferentes.

Los escenarios utilizan los supuestos guardados y, cuando se elige historia, cinco años completos de precios nominales comparables. Son proyecciones condicionales, no ganancias garantizadas. Los cultivos sin presupuesto permanecen visibles como pendientes.

EVA aporta referencias municipales de rendimiento, UPRA estructuras de costos por región/año y FEPCafé una referencia nacional para pergamino seco. El porcentaje de rendimiento requiere período y estado comparables. El [Censo Nacional Agropecuario de DANE](https://microdatos.dane.gov.co/catalog/513) tiene microdatos, pero no recoge costos de producción, precios de venta ni ingresos: no permite inventar una clasificación de utilidad entre fincas vecinas. La aptitud y el contexto de suelos se presentan con su escala territorial; no sustituyen mediciones de la finca.

### Funcionalidad y límites

| Función | Dónde | Alcance |
| --- | --- | --- |
| Buscar y filtrar | Catálogos, mapas, fuentes y exploración de cultivos | Sugerencias sin distinción de tildes, teclado y botón para limpiar. |
| Precios actuales | Productos y mercados | Vista de últimos 12 meses, historia y fuentes. El precio mayorista no es una oferta en finca. |
| Café | Productos → Café pergamino seco | Referencia diaria FNC, factores de rendimiento, entregas, TRM y calculadora de oferta. Sin clasificación de compradores privados. |
| Abastecimiento | Producto / mercado | Volúmenes mensuales reportados, cobertura y filas originales; no existencias para venta. |
| Insumos | Detalle de insumo | Precios fechados de la misma presentación, sin dosis recomendadas ni ofertas de tiendas. |
| Transporte y ofertas | Producto, café y `/offers` | Comparar neto de venta y costo de compra con cantidades, descuentos, gastos, pago y vencimiento. Ofertas privadas ingresadas por el usuario. |
| Boletín diario | Producto → `/daily` | Definiciones diarias separadas de variedades mensuales, con PDF archivado. |
| Fincas y cultivos | Mi finca | Registros múltiples, mapa con pin, GPS opcional y presupuestos por cultivo. Sin subir análisis de suelo. |
| Clima y alertas | Finca → Clima y labores | Pronóstico de siete días, reglas explicadas y publicaciones oficiales fechadas. No notificaciones push ni confirmación automática de plagas. |
| Qué sembrar | Finca → Mis cultivos → Explorar | Producción/rendimiento EVA, aptitud SIPRA y contexto regional de suelos. Sin diagnóstico de parcela. |
| Cosecha y estacionalidad | Presupuesto | Calendarios históricos, ventana según floración de café y simulación por ciclo. No determina madurez de cosecha. |
| Guardar y exportar | Finca y presupuesto | Copia JSON de finca; hasta seis escenarios por finca con supuestos e identificadores de fuente. |
| Fotografías e ilustraciones | Catálogos y créditos | Fotografías por familia, plazas conocidas y material ilustrativo. Se distinguen ilustraciones y empaques genéricos. |

Pendiente de desarrollo: red de ofertas en vivo, pagos verificados, notificaciones push, fechas de siembra óptimas automáticas, aptitud de parcela, satélites, rutas de transporte, análisis CHIRPS e integración de modelos AGRORAC. Las notas de investigación no implican que esas funciones estén activas.

### Mapa de implementación

| Responsabilidad | Ubicación |
| --- | --- |
| Navegación y catálogos | `app/app-shell.tsx`, `app/page.tsx`, `components/marketplace/CatalogView.tsx`, `app/markets`, `app/insumos` |
| Detalles | `app/product/[id]`, `app/market/[id]`, `app/insumo/[id]`, `components/explore/CoffeeDetail.tsx` |
| Abastecimiento y mapas | `components/explore/SupplyPanel.tsx`, `ColombiaMap.tsx`, `lib/server/explore.ts`, `/api/explore/[resource]` |
| Búsqueda y visor | `components/ui`, `components/planning/EvidenceProvider.tsx`, `EvidenceContent.tsx`, `PdfViewer.tsx` |
| Fincas y cuentas | `app/farm/[id]`, `components/farms`, `lib/farm-types.ts`, `components/planning/FarmContext.tsx` |
| Planificación | `app/plan`, `components/planning/WeeklyPlan.tsx`, `CropOptions.tsx`, `CropBudget.tsx`, `lib/planning-math.ts` |
| Imágenes | `lib/images.ts`, `lib/image-library.json`, `app/credits`, `pipelines/assets` |
| Importación inicial de abastecimiento | `pipelines/market` |
| Ingesta permanente | `pipelines/ingestion`, `infra/deploy_ingestion.py` |

Las rutas de código web son relativas a `apps/web/src`. `/coffee` redirige al producto café y `/map` al catálogo de mercados. `/auth` y `/settings` conservan redirecciones de compatibilidad.

## Server boundary

`apps/web/src/lib/server` is server-only. PostgreSQL connections use certificate validation, a small pooled connection limit and statement timeout. Parameterized API queries validate/limit inputs and return plain Spanish errors without SQL or connection details. The application role can SELECT reference tables and INSERT public weather snapshots; it cannot modify official data or documents.

`source_document` holds original PDF/XLSX/JSON/text bytes. `document_alias` points to a current version, while observation records and saved scenarios link to immutable hashes. DANE's original price source is XLSX: generated PDFs explicitly identify themselves as AgroAmigo extracts and retain workbook/sheet/row locators plus links to the original workbook. Original official PDFs are archived intact. PDF.js renders locally inside the app with bundled worker/fonts; non-PDF source data can show relevant records and preserve a downloadable original.

Observation guards reject future Colombia dates. Historical observations are retained permanently; the app queries recent 12-month views, and planning selects five complete prior years from the retained `seasonal_year` history. The `historical_price` table preserves original source rows and units; `retained_record` preserves revisions of published observations. Triggers block deletion/truncation of historical stores, and the ingestion role has no deletion or DDL privileges. Crop reference data is not represented as a current observation. Prices are nominal. No interpolation fills missing source rows.

## Local data

Farm records, crops, saved products, quotes, task status and up to six scenarios per farm are stored on the user's device. They are not uploaded or published. Climate requests send rounded coordinates (0.01°) to the server/provider and store the public forecast response for provenance. Municipal default points are explicitly distinguished from a farm location. User-entered dates and yields are assumptions or records, not remotely verified facts.

Farm storage uses `agroamigo-farms-v2`. The existing `agroamigo-farm-v1` is migrated once with stable identifiers, and old scenario snapshots remain accessible on that migrated farm. Budgets are applied explicitly to one crop. Weather task status is scoped to farm/crop. Location permission is requested only by the GPS button; permission denial keeps map/manual entry available. The saved pin appears on every farm detail. JSON exports carry the farm, crop plans and source identifiers; there is no account-based device synchronization.

## Refresh and deployment

Azure Function `agroamigo-data-9a04` refreshes official price sources daily at 23:00 UTC (18:00 Colombia) and resumes historical extraction hourly at minute 15. It uses the existing subscription, App Service plan and PostgreSQL database. Original source bytes also reside in the private `agroamigodata9a04/source-archive` container without expiration. PostgreSQL storage autogrow is enabled. SIPSA monthly coverage begins in July 2012, and the first daily source is dated 12 June 2012. See [the ingestion service](../pipelines/ingestion/README.md) for checkpoints, retention controls and operational validation. Other planning references remain dated publications; climate is fetched on use.

Web deployment bundles the standalone server, static assets, PDF worker assets and APK. It excludes dotenv credentials and verifies both an artifact-specific release ID and the database health endpoint.

GitHub Actions builds web, Android and iOS, checks Python syntax, runs Android lint and checks iOS navigation rules. The retained `agroamigo-iphone-build.yml` workflow runs on every push/PR; successful builds on `main` automatically sign and upload to TestFlight using the existing native-app secrets. Other branches and pull requests only build. Web deployment remains a separate Azure operation. End-to-end browser tests need the configured Azure database or `PLAYWRIGHT_BASE_URL`; iOS integration tests use the live Azure demo in a simulator.

GitHub build artifacts use one-day retention. Only successful main-branch Android installers and successfully uploaded TestFlight IPAs are archived; unsigned Runner.app folders are not uploaded. `artifact-cleanup.yml` runs after either build workflow, daily, and on manual request. It keeps at most the newest successful main artifact per platform, removes superseded/expired/older-than-one-day copies and retired build formats, and leaves running workflows and unrelated artifacts alone. The daily pass also covers artifacts created under the old 90-day policy. Dependency caches remain available to speed up builds. The cleanup does not delete workflow history or store releases. Preview it with `python3 .github/scripts/prune_artifacts.py`; add `--apply` to delete the listed artifacts.

## Cleanup record

The active Flutter iOS client was moved from `agroamigo-iphone` to `apps/ios`, its old Supabase screens were replaced with the shared Azure interface, and its existing successful TestFlight workflow was retained with updated paths. The old Expo/React Native and second Next web prototypes, Expo release workflow and unused shared Supabase package were removed. Twenty unreachable components, providers, translation/map modules and Supabase initializers were removed from the active web app. Legacy Supabase migrations, one-off repair scripts and its ingestion stack were replaced by the independent Azure importers. Source municipal files were preserved; old implementations remain available in Git history.

## Shared visual design

`apps/web/src/app/globals.css` provides component layout and responsive behavior; `field-theme.css` defines the shared colors, photographic headers, crop cards, alert treatments and mobile refinements. All three clients load this same product interface. The iOS deployment target is iOS 18, matching the supported PDF viewer browser baseline. PDF text uses explicit stream readers for older WebKit versions without asynchronous stream iteration.

Typography uses standard platform fonts without downloaded display fonts. Solid fills, visible borders, larger labels and simple corners keep the interface familiar. The five mobile destinations share equal grid columns and the same parent-route selection rules as desktop navigation. Short pages fill the dynamic viewport; landscape phones retain mobile navigation.

The iOS WebView fills a Stack below the top safe area and extends to the bottom screen edge. Loading is an overlay and there is no separate native back-button row to change the page height after navigation. The web viewport uses `viewport-fit=cover`; the tab bar adds `env(safe-area-inset-bottom)` so its background reaches the edge while controls clear the home indicator. This follows [WebKit's safe-area guidance](https://webkit.org/blog/7929/designing-websites-for-iphone-x/). Page back buttons and native swipe gestures remain available.
