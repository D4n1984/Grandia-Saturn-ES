# Grandia para Sega Saturn — Español

Parche de traducción al español para los dos discos japoneses de **Grandia de Sega Saturn**.

**Autor de la traducción y del parche en español: [D4n1984](https://github.com/D4n1984).**

Se utiliza como base técnica la traducción inglesa 1.1.1 de **TrekkiesUnite118 y colaboradores**, conservando sus referencias y las de **SegaXtreme**. La pantalla inicial incluye los créditos de la edición española y el enlace a este repositorio.

## Descargar el parche

**[Completa01.1 — candidata para pruebas](https://github.com/D4n1984/Grandia-Saturn-ES/releases/tag/completa01.1)**

- [Instalador del disco 1, con los nuevos créditos](https://github.com/D4n1984/Grandia-Saturn-ES/releases/download/completa01.1/Grandia_Saturn_ES_Completa01_1_D1.zip).
- [Instalador del disco 2](https://github.com/D4n1984/Grandia-Saturn-ES/releases/download/completa01.1/Grandia_Saturn_ES_Completa01_D2.zip). Este disco no cambia respecto a Completa01.

Los archivos descargables contienen **únicamente el parche, sus herramientas y licencias**. No incluyen imágenes del juego.

## Instalación

1. Necesitas Windows de 64 bits y tus imágenes japonesas compatibles en formato **CUE/BIN**. Conserva las pistas BIN junto a su CUE.
2. Descarga y extrae el instalador de cada disco.
3. Abre `aplicar.cmd`, indica el CUE japonés correspondiente y una **carpeta nueva** para el resultado.
4. Espera a que termine la aplicación y verificación. Obtendrás `Grandia_ES_D1.chd` o `Grandia_ES_D2.chd`.

No necesitas instalar Python ni aplicar antes la traducción inglesa. El instalador incluye Python portátil, xdelta3 y chdman. Comprueba las imágenes de entrada y salida, conserva los originales y rechaza una carpeta de salida que ya exista. La entrada del instalador es CUE/BIN; no admite directamente un CHD original.

Para una lista multidisco, coloca ambos CHD juntos y utiliza el archivo [Grandia (Español).m3u](<Grandia (Español).m3u>) incluido en este repositorio. El soporte de M3U y del cambio de disco depende del emulador; también puedes abrir los CHD por separado.

## Estado de la traducción

La hoja de trabajo contiene **25.350 entradas traducidas y revisadas editorialmente**, sin pendientes de traducción. Incluye diálogos, historia, menús y textos codificados de objetos, habilidades, enemigos y avisos. Los textos integrados en gráficos conservan su idioma salvo la presentación y el menú inicial acordados.

Esta entrega es una **candidata para pruebas**, no una versión con una partida completa certificada. Se han comprobado la reconstrucción binaria, los controles y parámetros, los archivos del disco, el audio y la generación de CHD. Quedan las pruebas en emulador de disposición visual, estabilidad, guardado y cambio de disco. La verificación binaria no acredita que todos los textos quepan en sus ventanas ni que todas las escenas funcionen.

Las imágenes del juego, transcripciones y material de trabajo se mantienen fuera del repositorio. Los paquetes de parche se publican en Releases.

## Créditos

- Traducción y parche al español: **D4n1984**.
- Base técnica: **Grandia Saturn English Patch 1.1.1**, de **TrekkiesUnite118 y colaboradores**; [SegaXtreme](https://segaxtreme.net/resources/grandia-english-patch.67/).
- Grandia y sus materiales originales pertenecen a sus respectivos titulares.
- Las licencias de las herramientas distribuidas acompañan a cada instalador.

## Apoyar el proyecto

Si quieres apoyar el trabajo, puedes hacerlo en [Buy Me a Coffee](https://buymeacoffee.com/danielgarciagarcia).
