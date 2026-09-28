# Mi finca: ubicación y referencias agrícolas

Mi finca permite guardar un punto, consultar el clima y explorar referencias territoriales y agrícolas. No contiene una calculadora manual de rentabilidad ni un editor de presupuestos.

## Recorrido

1. Buscar un lugar, usar el GPS o fijar un pin en el mapa.
2. Consultar el pronóstico y las capas territoriales.
3. Explorar cultivos publicados para el municipio de referencia.
4. Abrir calendarios históricos, estudios de costos y precios históricos con sus fuentes.

Mover el mapa no mueve el pin guardado. El municipio elegido para consultar referencias tampoco cambia la ubicación de la finca. `/farm/[id]` conserva el acceso a una finca guardada; `/plan` presenta referencias de solo lectura. Los enlaces antiguos con `?tab=budget` abren estas referencias y explican que los registros anteriores se conservan.

## Datos visibles

| Referencia | Interpretación |
|---|---|
| Pronóstico Open-Meteo | Temperatura, lluvia, probabilidad, viento y otros campos del modelo, con unidades y coordenadas explícitas |
| Normales IDEAM de lluvia/temperatura | Condiciones habituales del período climatológico publicado, no un pronóstico del mes o año actual |
| Suelos IGAC | Unidad cartográfica, paisaje y atributos regionales; no un análisis químico del predio |
| Erosión e inundación IDEAM | Cartografía histórica y susceptibilidad; no un evento activo ni una garantía de ausencia de amenaza |
| Producción EVA | Cultivo, sistema, año, área cosechada, producción y rendimiento municipal |
| Aptitud SIPRA | Áreas y clases publicadas para el cultivo; no una recomendación automática de siembra |
| Calendarios | Porcentajes históricos por actividad y mes; no fechas óptimas de siembra |
| Estudios de costos | Componentes y total publicados, región, sistema, período y unidad |
| Historia de precios | Producto y mercado comparables; datos insuficientes se muestran como tales |

Las señales meteorológicas de atención son reglas orientativas de la aplicación. No equivalen a alertas oficiales ni a un modelo validado de riesgo por cultivo. Los valores ausentes permanecen sin dato.

## Implementación y privacidad

[LocationWorkspace](../apps/web/src/components/location/LocationWorkspace.tsx) mantiene el pin y la exploración. [CropOptions](../apps/web/src/components/planning/CropOptions.tsx) presenta cultivos y [CropReferences](../apps/web/src/components/planning/CropReferences.tsx) sus referencias. Los datos proceden de las APIs de planificación y ubicación; [layers.json](../pipelines/spatial/layers.json) delimita las capas permitidas.

Las consultas públicas de clima y geografía envían las coordenadas seleccionadas al servidor/proveedor y conservan la respuesta con su procedencia. El visor enlaza la entidad, escala, período y original o consulta correspondiente. Una coordenada del modelo y el pin solicitado no se presentan como el mismo dato.

El pin y los registros privados se guardan en el dispositivo. Las vistas de referencias no reescriben los presupuestos, cultivos o escenarios anteriores. No hay sincronización de esos registros entre dispositivos. Las conversiones FNC y la comparación de ofertas continúan fuera de las herramientas de Mi finca.
