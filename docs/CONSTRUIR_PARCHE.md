# Construir y comprobar el parche

Autor: **D4n1984**. Los instaladores ya preparados y las instrucciones para jugadores están en el [README principal](../README.md) y en [Releases](https://github.com/D4n1984/Grandia-Saturn-ES/releases/tag/completa01.1).

## Requisitos

- Python 3.12 o posterior para ejecutar el código fuente.
- xdelta3 y chdman, con sus licencias, para generar o aplicar paquetes.
- Imágenes japonesas compatibles en CUE/BIN, con las pistas junto a su CUE.
- Para crear un paquete: una imagen española ya construida en CUE/BIN de una sola pista BIN combinada, además de Python portátil para Windows.
- Para renderizar gráficos: Windows, PowerShell, System.Drawing y Arial Narrow.

Los instaladores publicados incluyen sus herramientas y licencias. No es necesario descargar una BIOS para aplicar el parche. No se distribuyen las imágenes originales ni las traducidas.

## Aplicar desde el código fuente

Extrae el instalador del disco correspondiente y utiliza su carpeta como primer argumento:

```powershell
python herramientas/aplicar_parche_es.py "C:\Parches\Grandia_ES_Completa01_1_D1" "C:\Originales\Disco 1.cue" "C:\Resultados\Grandia_D1"
```

La carpeta padre de la salida debe existir; la carpeta de salida debe ser nueva. El aplicador valida los hashes de las pistas japonesas y de las herramientas, concatena las pistas temporalmente, aplica el delta, comprueba el BIN español, crea el CHD y lo verifica. Después extrae el BIN desde el CHD para comprobar su hash. Conserva solo el CHD final y no modifica los originales.

## Crear un instalador directo JP→ES

Desde la raíz de este repositorio, con tus archivos y herramientas locales:

```powershell
python herramientas/crear_parche_es.py `
  --disco D1 `
  --origen "C:\Originales\Disco 1.cue" `
  --destino "C:\Construccion\Grandia_ES_D1.cue" `
  --xdelta "C:\Herramientas\xdelta3.exe" `
  --licencia "C:\Herramientas\LICENSE-xdelta-APACHE-2.0.txt" `
  --chdman "C:\Herramientas\chdman.exe" `
  --licencia-chdman "C:\Herramientas\MAME_COPYING.txt" `
  --python "trabajo\python312" `
  --salida "trabajo\distribucion\Grandia_ES_ejemplo_D1"
```

`MAME_GPL-2.0.txt` debe estar junto a `MAME_COPYING.txt`. El directorio de Python portátil debe contener un intérprete Windows funcional y sus bibliotecas. El generador copia las herramientas y sus licencias, crea `aplicar.cmd`, el manifiesto y el delta, y comprueba una aplicación completa antes de entregar el paquete. Repite con `--disco D2` y los archivos de ese disco.

Para comprobar de nuevo un paquete existente sin conservar el resultado:

```powershell
python herramientas/verificar_parche_es.py "trabajo\distribucion\Grandia_ES_ejemplo_D1" "C:\Originales\Disco 1.cue"
```

## Reconstruir los recursos editoriales

El código de reinserción y reconstrucción está incluido. Esta fase requiere datos locales que no forman parte de la distribución pública:

- Imágenes japonesas y la base inglesa reconstruida, bajo `trabajo/`.
- Hoja EN→ES y respaldos originales de guiones, tablas y menús en `trabajo/traduccion-en-es/`.
- Perfiles cerrados por entrada para los remanentes japoneses y los marcadores especiales.
- Catálogos de archivos, offsets, piezas y hashes en `inventario/`, y el estado de cobertura de `inventario/bloqueos-version-es.json`.
- Recursos locales de las fuentes españolas y manifiestos de presentación y título.

Estos datos contienen material extraído del juego y no se publican. Un clon del repositorio, por sí solo, no reconstruye la traducción editorial completa. El generador de instaladores sí puede crear el delta cuando se le proporcionan un original compatible y una imagen española ya construida.

Con el espacio de trabajo editorial preparado, la secuencia es:

```powershell
python herramientas/estado_traduccion_es.py --exigir-completa
python herramientas/preparar_version_completa_es.py `
  --salida trabajo/version-ejemplo `
  --version Ejemplo `
  --reparar 2404 --reparar E414 --reparar B108 `
  --extra-manifiesto trabajo/prueba-es/presentacion-completa/manifiesto.json
```

El manifiesto adicional debe referenciar los recursos gráficos y discos correspondientes. Para regenerar la presentación con los créditos de **D4n1984** y el enlace GitHub, usando la base y los catálogos locales:

```powershell
python herramientas/prueba_presentacion_es.py --salida trabajo/prueba-es/presentacion-nueva
```

La salida debe ser nueva. El constructor comprueba la cobertura editorial y las estructuras, preserva controles y parámetros, y verifica recursos y audio. La validación binaria no sustituye a las pruebas de disposición visual y partida completa en emulador.

## Comprobación del lanzador

Con el Python portátil ubicado en `trabajo/python312`:

```powershell
python herramientas/verificar_lanzador_parche_es.py
```

Esta prueba utiliza un aplicador simulado: comprueba en CMD real rutas con espacios, entrada interactiva con y sin comillas y propagación de errores. No necesita imágenes del juego.
