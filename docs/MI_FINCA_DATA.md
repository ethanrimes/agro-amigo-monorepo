# Mi finca: datos territoriales y análisis económico

Rediseño informativo, septiembre de 2026. Sin alta obligatoria de fincas, registro de labores ni carga de análisis de suelo.

## Fuentes implementadas

| Capa | Fuente primaria | Período / escala | Interpretación |
| --- | --- | --- | --- |
| Lluvia por mes | [IDEAM, capa 62](https://visualizador.ideam.gov.co/gisserver/rest/services/Clima_Precipitacion/MapServer/62) | Normal 1991–2020 | Intervalo de total mensual habitual, mm. Filtro `periodoini` según mes de 1991. |
| Lluvia anual | [IDEAM, capa 61](https://visualizador.ideam.gov.co/gisserver/rest/services/Clima_Precipitacion/MapServer/61) | Normal 1991–2020 | Intervalo de total anual habitual, mm. |
| Temperatura mensual | [IDEAM, capa 2](https://visualizador.ideam.gov.co/gisserver/rest/services/Clima_Temperatura/MapServer/2) | Normal 1981–2010 | Intervalo de temperatura media, °C. Filtro `per_ini` según mes de 1981. |
| Temperatura anual | [IDEAM, capa 3](https://visualizador.ideam.gov.co/gisserver/rest/services/Clima_Temperatura/MapServer/3) | Normal 1981–2010 | Media anual habitual, no máxima ni pronóstico. |
| Suelos | [IGAC, correlación nacional](https://mapas.igac.gov.co/server/rest/services/agrologia/correlacionsuelosnacional/MapServer/0) | 1:100.000, estudios de fechas distintas | Color = paisaje. Punto = unidad, textura, profundidad, acidez, fertilidad, drenaje y otros atributos publicados. No laboratorio del predio. |
| Erosión | [IDEAM, capa 7](https://visualizador.ideam.gov.co/gisserver/rest/services/Estado_Degradacion_Suelos/MapServer/7) | 2020, 1:100.000 | Color = tipo; punto = tipo, clase y grado decodificados con los dominios oficiales. |
| Inundación | [IDEAM, susceptibilidad](https://visualizador.ideam.gov.co/gisserver/rest/services/Vulnerabilidad_Susceptibilidad_Ambiental/MapServer/1) | 2010, 1:500.000 | Zonificación histórica, sin probabilidad diaria. Fuera del polígono no equivale a ausencia de amenaza. |
| Pronóstico y atención meteorológica | [Open-Meteo API](https://open-meteo.com/en/docs) | 7 días, zona horaria America/Bogota | Hasta 25 consultas alrededor del mapa. Se conserva cada coordenada consultada y del modelo. La separación de muestreo no es la resolución del modelo. |

La capa meteorológica usa mm, °C y km/h solicitados explícitamente y verifica esas unidades. El total de lluvia y la máxima térmica son cálculos sobre los días elegidos. Valores incompletos permanecen sin dato. La señal de atención agrupa lluvia ≥20 mm/día, viento ≥40 km/h, máxima ≥35 °C o mínima ≤2 °C; es una heurística transparente, sin calibración por cultivo y sin equivalencia a una alerta oficial. [Boletines IDEAM](https://www.ideam.gov.co/sala-de-prensa/boletines) permanecen enlazados.

Las normales describen meses/años habituales. No se encontró un servicio público verificado de pronóstico mensual/anual equivalente con el que reemplazarlas. Las carpetas IDEAM `Normales_Climatologicas` y `Mapas` exigieron token; se usan únicamente las capas públicas comprobadas. El producto no disfraza una normal como expectativa de un año concreto. Open-Meteo gratuito corresponde al demo no comercial; `OPEN_METEO_API_KEY` permite usar su endpoint comercial.

## Trazabilidad y operación

`pipelines/spatial/layers.json` es la lista permitida de geoservicios. Ejecutar:

```sh
.venv/bin/python pipelines/spatial/import_layers.py
```

El importador valida campos y archiva los bytes originales del esquema de cada capa, sus dominios y leyendas en Azure PostgreSQL. No elimina observaciones ni historia. `spatial_layer` apunta al esquema vigente; `spatial_snapshot` conserva versiones.

- `/api/location/layers`: catálogo y enlaces de evidencia.
- `/api/location/tile`: proxy PNG de `MapServer/export`, solo capas permitidas, mes y bbox validados. Imágenes de visualización cacheadas 24 horas; proceden del geoservicio vigente y no son un archivo histórico de mosaicos.
- `/api/location/point`: intersección exacta contra los polígonos originales de la entidad (coordenadas redondeadas a seis decimales), sin aproximación por centroide municipal. Cache de 30 días para estas referencias históricas. Conserva URL, respuesta JSON, ID de polígono, atributos decodificados y padre con esquema. Las unidades superpuestas se muestran todas.
- `/api/location/grid`: pronóstico en hasta 25 puntos, separación de 0,25/0,5/1/2/4 grados según vista. Cache de dos horas. Sin fallback silencioso a pronósticos vencidos.
- `/api/evidence/spatial-…`: visor existente con registros y documentos padre.
- `/api/evidence/spatial-…/content`: descarga del esquema original o sobre JSON `{consulta, respuesta}`. SHA-256 corresponde exactamente a los bytes descargados. Un sobre se etiqueta como extracto.

El rol web recibe SELECT/INSERT en `spatial_snapshot`, SELECT en `spatial_layer`, sin UPDATE/DELETE/TRUNCATE. Consultas concurrentes idénticas se agrupan dentro del proceso. Las consultas no aceptan URLs de usuario ni filtros SQL libres. El pin se guarda localmente; la consulta pública y sus coordenadas se archivan para trazabilidad, como se explica en la interfaz.

## Comparaciones económicas

Reutiliza referencias verificadas en Azure: EVA municipal, estructuras de costos UPRA, SIPSA, FNC y FEPCafé. Los costos propios se ingresan por ha; transporte en COP totales y comisión en porcentaje. Cada rubro UPRA conserva el enlace al PDF/página. El usuario confirma sistema, período, alcance y diferencia temporal antes de comparar. Diferencia nominal = supuesto propio por ha − costo del estudio por ha; no hay ajuste de inflación implícito ni ranking de eficiencia.

El [CNA 2014](https://microdatos.dane.gov.co/index.php/catalog/513) excluye explícitamente costos, precios de venta e ingresos. [EMICRON 2024, P3057_D](https://microdatos.dane.gov.co/index.php/catalog/875/variable/F8/V147?name=P3057_D) contiene costos agrupados de producción agrícola, pecuaria y extractiva; no es un benchmark de cada rubro de un cultivo por hectárea. Por eso no se presentan pares ficticios. FEPCafé es referencia nacional nominal de febrero de 2026, con método y período visibles.

Fórmulas compartidas de tabla y cascada (`lib/cleansheet.ts`):

- Kilos vendibles = ha × kg/ha × (1 − pérdidas).
- Ingresos = kilos vendibles × precio/kg.
- Producción = ha × suma de costos/ha.
- Comisión = ingresos × porcentaje.
- Utilidad = ingresos − producción − transporte/venta − comisión.
- Equilibrio = (producción + transporte/venta) / (kilos vendibles × (1 − comisión)).

Una celda vacía impide mostrar resultados. Cero solo se usa cuando fue ingresado. Tabla y cascada admiten utilidad negativa. Las sensibilidades mantienen costos constantes y varían rendimiento y precio, sin probabilidades. El usuario descarga JSON con entradas, resultados y fuentes. Los registros previos de `agroamigo-farms-v2` siguen intactos; `/farm/[id]` carga su ubicación en el nuevo espacio.
