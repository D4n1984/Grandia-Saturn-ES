# Parche publicado — código del instalador

Estos archivos corresponden a los instaladores ya publicados de **Grandia Saturn ES Completa01.1**:

- `aplicar_parche_es.py`: código que aplica el delta al original japonés, comprueba el resultado y genera el CHD.
- `aplicar.cmd`: lanzador Windows incluido en ambos instaladores.
- `manifiestos/D1.json` y `manifiestos/D2.json`: manifiestos exactos de los dos paquetes, con sus archivos y hashes esperados.
- `version.json`: enlaces y hashes de los ZIP preparados.

Para instalar, descarga los **ZIP de los discos** desde [Releases](https://github.com/D4n1984/Grandia-Saturn-ES/releases/tag/completa01.1): incluyen los deltas `.xdelta`, Python portátil, xdelta3, chdman, el aplicador y las licencias. Esta carpeta permite consultar el código del instalador; el archivo automático «Source code» de GitHub no sustituye a esos ZIP completos.

Las [instrucciones de aplicación](../docs/APLICAR_PARCHE.md) explican el procedimiento. Aquí no se incluyen generadores ni herramientas de elaboración de la traducción.
