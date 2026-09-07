# Imágenes de AgroAmigo

`fetch_images.py` descarga familias faltantes de Wikimedia Commons y conserva el manifiesto revisado en `apps/web/src/lib/image-library.json`. No reemplaza selecciones existentes. Cada descarga debe revisarse visualmente antes de publicar: una coincidencia de búsqueda no garantiza que muestre el producto.

El manifiesto guarda archivo, título original, autor, licencia, enlace y SHA-256. Las imágenes se sirven localmente; `/credits` expone su atribución. Las ilustraciones SVG propias de garbanzos y envases genéricos se identifican como ilustraciones. Los insumos no muestran empaques comerciales verificados; las fotos de familia pueden diferir de la variedad. Las plazas sin foto específica usan una imagen de referencia, indicada en el texto alternativo.

Ejecutar desde la raíz con el entorno Python del proyecto: `.venv/bin/python pipelines/assets/fetch_images.py`.
