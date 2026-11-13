# Código del parche

Código propio en Python para construir, aplicar y comprobar el parche de Grandia Saturn ES. La distribución preparada para Windows está en [Releases](https://github.com/D4n1984/Grandia-Saturn-ES/releases/tag/completa01.1).

| Función | Punto de entrada |
| --- | --- |
| Aplicar un instalador a un original japonés y producir CHD | `aplicar_parche_es.py` |
| Crear un paquete xdelta directo JP→ES, con herramientas portátiles | `crear_parche_es.py` |
| Comprobar un paquete mediante aplicación y extracción inversa | `verificar_parche_es.py` |
| Probar el lanzador CMD con espacios, comillas y errores | `verificar_lanzador_parche_es.py` |
| Integrar lotes editoriales con controles y respaldos | `integrar_lotes_es.py` |
| Contar cobertura y auditar una hoja de traducción | `estado_traduccion_es.py`, `comprobar_traduccion_es.py` |
| Preparar recursos traducidos y construir las imágenes | `preparar_recursos_traducidos_es.py`, `preparar_version_completa_es.py` |
| Reconstruir guiones, tablas y sectores ISO | `reinsertar_guiones_es.py`, `reinsertar_tablas_menus_es.py`, `construir_imagen_recursos_es.py` |
| Renderizar los créditos y las etiquetas del título | `prueba_presentacion_es.py`, `prueba_menu_es.py` |

Los demás módulos son dependencias de esos puntos de entrada: codificación y fuentes, validación de formatos y perfiles cerrados, lectura de recursos, derivación específica de TEXT2 D2 y comprobación de imágenes. Los módulos llamados `extraer_*`, `inventariar_*` o `comparar_*` de esta carpeta aportan funciones que el constructor importa; no se publica el conjunto de herramientas de investigación del espacio de trabajo.

La aplicación y el empaquetado emplean la biblioteca estándar de Python, xdelta3 y chdman. El renderizado gráfico usa PowerShell, System.Drawing y Arial Narrow en Windows. Consulta [CONSTRUIR_PARCHE.md](../docs/CONSTRUIR_PARCHE.md) para comandos y requisitos.

Este código no incluye imágenes, BIOS, transcripciones ni datos de prueba extraídos del juego. Los archivos que cada comando genera se mantienen en `trabajo/`.
