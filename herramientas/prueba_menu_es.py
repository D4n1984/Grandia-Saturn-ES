#!/usr/bin/env python3
"""Prepara una prueba de etiquetas del título, sin modificar la imagen de disco.

Windows: requiere System.Drawing y Arial Narrow. Los offsets son ventanas gráficas
candidatas; su uso y apariencia deben comprobarse en el emulador.
"""
import csv, hashlib, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'herramientas'))
from inventariar_videos_bloques import read_movie

OUT = ROOT / 'trabajo/prueba-es/menu'
TRACK = ROOT / 'trabajo/ingles/salida/Grandia_EN_D1.bin'
INVENTORY = ROOT / 'trabajo/ingles/analisis/archivos-disco1.csv'
EXPECTED = {'BIN/TTL1.DAT': '72BEC999AB557BF809C080CD430F378DBDBF37AA0D993F0CAF17241E5FF63B6F',
            'BIN/TTL2.DAT': '2A1207D843426B2FC9D7FE10D8803FAECB4D17474CCC911955ABFFA7ECADAF8A'}
LABELS = [(0x6AF4, 'Nueva partida'), (0x6D74, 'Cargar partida')]

def sha(data):
    return hashlib.sha256(data).hexdigest().upper()

def generate_pixels(text, dest):
    # Draw 80×16 grayscale, 4-bit indexed after quantization. Store pixels in
    # row order; the later encoder converts them to 8×8 Saturn character tiles.
    ps = r'''
Add-Type -AssemblyName System.Drawing
$b = New-Object System.Drawing.Bitmap 80,16
$g = [System.Drawing.Graphics]::FromImage($b)
$g.Clear([System.Drawing.Color]::Black)
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$f = New-Object System.Drawing.Font('Arial Narrow', 13, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$format = [System.Drawing.StringFormat]::GenericTypographic
$size = $g.MeasureString($args[0], $f, 1000, $format)
if ($size.Width -gt 78) { $g.ScaleTransform(78 / $size.Width, 1) }
$g.DrawString($args[0], $f, [System.Drawing.Brushes]::White, 1, 0, $format)
$g.Flush()
$bytes = New-Object byte[] 1280
for ($y=0; $y -lt 16; $y++) { for ($x=0; $x -lt 80; $x++) { $bytes[$y*80+$x] = $b.GetPixel($x,$y).R } }
[System.IO.File]::WriteAllBytes($args[1], $bytes)
$f.Dispose(); $g.Dispose(); $b.Dispose()
'''
    p = OUT / 'render.ps1'
    p.write_text(ps, encoding='utf-8')
    subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(p), text, str(dest)], check=True)
    pixels = dest.read_bytes()
    if len(pixels) != 1280:
        raise ValueError('Tamaño de imagen inesperado')
    result = bytearray()
    for tile_y in range(2):
        for tile_x in range(10):
            for y in range(8):
                row = (tile_y * 8 + y) * 80 + tile_x * 8
                for x in range(0, 8, 2):
                    a = (pixels[row+x] * 15 + 127) // 255
                    b = (pixels[row+x+1] * 15 + 127) // 255
                    result.append(a << 4 | b)
    assert len(result) == 640
    return bytes(result)

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with INVENTORY.open(encoding='utf-8-sig', newline='') as f:
        entries = {r['ruta']: r for r in csv.DictReader(f)}
    tiles = [(offset, label, generate_pixels(label, OUT / f'label-{offset:04x}.raw')) for offset, label in LABELS]
    manifest = []
    with TRACK.open('rb') as track:
        for route, expected in EXPECTED.items():
            source = read_movie(track, entries[route])
            if sha(source) != expected:
                raise ValueError(f'Hash de fuente inesperado: {route}')
            target = bytearray(source)
            for offset, label, data in tiles:
                target[offset:offset+len(data)] = data
            if len(source) != len(target):
                raise ValueError('Cambió la longitud')
            dest = OUT / Path(route).name
            dest.write_bytes(target)
            manifest.append(dict(ruta=route, sector=int(entries[route]['sector']), bytes=len(source), sha256_original=sha(source), sha256_nuevo=sha(target), archivo=str(dest), rangos=[dict(offset=hex(off), bytes=len(data), texto=label, sha256_original=sha(source[off:off+len(data)]), sha256_nuevo=sha(data)) for off,label,data in tiles]))
    (OUT / 'manifiesto.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(manifest, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
