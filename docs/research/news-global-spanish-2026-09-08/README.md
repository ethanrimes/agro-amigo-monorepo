# Noticias internacionales en español: verificación del 8 de septiembre de 2026

Ventana solicitada: **25 de agosto–7 de septiembre de 2026**, inclusive en Colombia. La recopilación se ejecutó el 8 de septiembre UTC. Son resultados privados de investigación; no se importaron noticias a Azure ni se activó un cron de Luna.

## Tres artículos revisados

| Publicación | Fecha del artículo | Hecho verificado y posible uso |
| --- | --- | --- |
| [FAO, índice mundial de alimentos](https://www.fao.org/newsroom/detail/supply-concerns-drive-fao-food-price-index-higher/es) | 4 septiembre | El índice aumentó 1,9 % en agosto frente a julio revisado. La relación con cotizaciones colombianas es una inferencia; no es un precio en finca. |
| [Portal Frutícola, análisis de Decofrut de la semana 36](https://www.portalfruticola.com/noticias/2026/09/07/mercado-semana-36-2026/) | 7 septiembre | Oferta y comercialización internacional de aguacates y cítricos. Los destinos compartidos permiten vigilar competencia para exportadores colombianos, sin garantizar precios locales. |
| [FreshPlaza, temporada de mango de Ecuador](https://www.freshplaza.es/spain/article/9868472/ecuador-inicia-la-temporada-de-mango-con-una-produccion-que-podria-caer-un-40/) | 1 septiembre | Recoge una previsión de la Fundación Mango Ecuador de una caída de producción de al menos 40 %. Es una estimación, no un resultado final. El posible efecto sobre competencia exportadora colombiana se señala como inferencia. |

El titular pertenece a su editor. El informe de Portal Frutícola identifica a Decofrut como autor del análisis; FreshPlaza remite a El Universo. Se guardan enlaces al artículo consultado y metadatos, sin cuerpos de noticias ni fotografías. [Handoff revisado](review-handoff.json), [registros y evidencia](records.json), [selección privada](research-feed.json).

La revisión fue realizada por el asistente principal (`parent_assistant`), **no por una ejecución de Luna**. El backfill anterior de Luna y su validación se conservan [por separado](../news-backfill-2026-09-07/report.md). No se deben sumar las cifras de pases distintos sin deduplicar.

## Conflicto de fecha retenido

El [boletín El Niño/La Niña de la OMM en español](https://public.wmo.int/es/resources/publication-series/el-ninola-nina-updates/agosto-de-2026) muestra **3 de septiembre**, mientras que `article:published_time` informa **1 de septiembre**. El parser conserva ambas pruebas y deja `published_at` vacío. Permanece [en revisión](review-queue.json); no se incluye automáticamente. Además, una perspectiva estacional mundial no constituye un pronóstico puntual de una finca.

## Cobertura realmente comprobada

El catálogo contiene 95 candidatos en español: 88 habilitados para comprobar acceso y siete deshabilitados. La [auditoría amplia](catalog-audit.json) intentó los 88 habilitados con un máximo de una página y un artículo por fuente. Registró 36 fuentes con estado `checked`, 52 parciales y siete deshabilitadas. `checked` significa que terminó ese intento limitado, no cobertura completa ni un artículo utilizable.

Se conservaron 57 registros: 46 en revisión y 11 descartados. Dentro de ese total, 25 pasaron las comprobaciones de idioma/fecha y quedaron pendientes de clasificación semántica; 16 no tenían fecha extraíble, cuatro tenían texto insuficiente y uno tenía fechas conflictivas. Nueve estaban fuera de la ventana y dos no verificaron español. No se publicaron automáticamente los 25 candidatos.

La prueba encontró dominios oficiales que sólo resolvían con `www`; se corrigieron cinco orígenes y se [volvió a comprobar el acceso](government-origin-recheck.json). ICA/MinAgricultura/AGROSAVIA reciben filtros de rutas de noticias para excluir enlaces de servicios. AGROSAVIA necesita su fecha visible con mes inicial; se añadió su selector y una regresión. El título de un mango enviado a Canadá ya no produce una etiqueta falsa de caña de azúcar.

La [verificación de listados](listing-verification.json) prueba siete publicaciones y conserva sus páginas pendientes. La [verificación de cuatro URLs originales](seed-verification.json) es distinta: no se presenta como un barrido de archivos. Las barreras de acceso, respuestas grandes, errores de red y publicaciones sin fecha quedan explícitas. Se requieren más adaptadores y seguimiento continuado para declarar completa la cobertura de cada editor.

## Operación

El [recolector](../../../pipelines/news/README.md) tiene estado SQLite, reintentos, cooldowns persistentes, revisión por hash, caducidad anclada a publicación y selección diversa por editor/evento. La clasificación determinista sólo propone etiquetas. El [prompt de tarea](../../automation/news-cloud-prompt.txt) pide al revisor abrir originales, conservar IDs/hashes y distinguir efectos inferidos. La ejecución diaria y la entrega autorizada a la app aún no están conectadas.
