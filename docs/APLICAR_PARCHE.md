# Aplicar el parche español de Grandia Saturn

El parche está preparado para **los dos discos japoneses de Grandia de Sega Saturn**. Cada disco tiene su propio instalador. Autor de la edición española: **D4n1984**.

## Descargas

- [Disco 1 — Completa01.1](https://github.com/D4n1984/Grandia-Saturn-ES/releases/download/completa01.1/Grandia_Saturn_ES_Completa01_1_D1.zip).
- [Disco 2](https://github.com/D4n1984/Grandia-Saturn-ES/releases/download/completa01.1/Grandia_Saturn_ES_Completa01_D2.zip).

Descarga estos ZIP de instalador, no el archivo automático «Source code». No contienen imágenes del juego ni BIOS.

## Requisitos

- Windows de 64 bits.
- Tus imágenes japonesas compatibles en **CUE/BIN**, con todas las pistas BIN junto al CUE de su disco.
- Espacio libre para los archivos temporales de aplicación y el CHD de salida.

No necesitas instalar Python ni aplicar previamente el parche inglés. El instalador no admite directamente una imagen CHD de entrada.

## Pasos

1. Extrae el ZIP del disco 1 a una carpeta y conserva todo su contenido.
2. Abre `aplicar.cmd`.
3. Introduce la ruta del **CUE japonés del disco 1**. Puede contener espacios y comillas.
4. Introduce la ruta de una **carpeta nueva** para el resultado. Su carpeta padre debe existir.
5. Espera a que termine la aplicación y la verificación. Obtendrás `Grandia_ES_D1.chd`.
6. Repite con el instalador del disco 2 y su CUE japonés. Obtendrás `Grandia_ES_D2.chd`.

También puedes pasar las rutas por argumentos, desde la carpeta del instalador:

```bat
aplicar.cmd "C:\Originales\Disco 1.cue" "C:\Resultados\Grandia_D1"
```

Los originales no se modifican y una carpeta de salida existente no se sobrescribe. La validación de hashes rechaza imágenes o herramientas que no coincidan con las esperadas. Se comprueba el BIN español, se genera y verifica el CHD y se extrae temporalmente para confirmar el hash del BIN recuperado.

## Contenido del instalador

Cada ZIP incluye el delta terminado de su disco (`D1.xdelta` o `D2.xdelta`), `manifiesto.json`, `aplicar.cmd`, `aplicar_parche_es.py`, Python portátil, xdelta3, chdman, licencias y `LEEME.txt`. No hay que generar ningún parche antes de usarlo.

El código del aplicador y los manifiestos también se pueden consultar en [parche/](../parche/README.md). Si ya dispones de Python, puedes ejecutar ese aplicador contra una carpeta de instalador extraída:

```powershell
python parche/aplicar_parche_es.py "C:\Parches\Grandia_ES_Completa01_1_D1" "C:\Originales\Disco 1.cue" "C:\Resultados\Grandia_D1"
```

## Estado

La traducción editorial cubre ambos discos. Es una candidata pendiente de completar las pruebas visuales y una partida completa en emulador, incluido guardado y cambio de disco. La verificación del parche no certifica todas las escenas del juego.
