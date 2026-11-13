#!/usr/bin/env python3
"""Traduce rótulos de la presentación inglesa en su formato gráfico nativo."""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'herramientas'))
from inventariar_videos_bloques import read_movie
OUT=ROOT/'trabajo/prueba-es/presentacion'
PIXELS=0x2DD3C
REGIONS=[(130,33,514,67),(50,225,590,326),(48,352,592,428)]


def sha(raw):return hashlib.sha256(raw).hexdigest().upper()


def address(x,y):
    return PIXELS+((y//16)*40+x//16)*256+((y%16)//8*2+(x%16)//8)*64+(y%8)*8+x%8


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--salida',type=Path,help='Directorio nuevo dentro de trabajo para la salida')
    args=parser.parse_args()
    global OUT
    if args.salida is not None:
        OUT=args.salida.resolve()
        if not OUT.is_relative_to((ROOT/'trabajo').resolve()) or OUT==(ROOT/'trabajo').resolve():
            parser.error('--salida debe estar dentro de trabajo')
        OUT.mkdir(parents=True,exist_ok=False)
    else:
        OUT.mkdir(parents=True,exist_ok=True)
    with (ROOT/'trabajo/ingles/analisis/archivos-disco1.csv').open(encoding='utf-8-sig',newline='') as stream:
        item=next(r for r in csv.DictReader(stream) if r['ruta']=='0')
    with (ROOT/'trabajo/ingles/salida/Grandia_EN_D1.bin').open('rb') as track:source=read_movie(track,item)
    with (ROOT/'inventario/comparacion-archivos-jp-en.csv').open(encoding='utf-8-sig',newline='') as stream:
        expected=next(r['sha256_ingles'] for r in csv.DictReader(stream) if r['disco']=='1' and r['ruta']=='0')
    assert sha(source)==expected and int.from_bytes(source[0x2DD38:PIXELS],'big')==640*448
    assert int.from_bytes(source[0x2D930:0x2D934],'big')==256
    palette=[tuple(source[0x2D938+i*4+1:0x2D938+i*4+4][::-1]) for i in range(256)]
    render=OUT/'rotulos.ps1'
    render.write_text(r'''
param([string]$Salida)
Add-Type -AssemblyName System.Drawing
$bitmap=New-Object System.Drawing.Bitmap 640,448
$g=[Drawing.Graphics]::FromImage($bitmap)
$g.Clear([Drawing.Color]::Transparent)
$g.TextRenderingHint=[Drawing.Text.TextRenderingHint]::AntiAliasGridFit
function Label([string]$Text,[int]$Top,[int]$Size,[Drawing.Color]$Color) {
 $font=New-Object Drawing.Font('Arial Narrow',$Size,[Drawing.FontStyle]::Bold,[Drawing.GraphicsUnit]::Pixel)
 $format=[Drawing.StringFormat]::GenericTypographic
 $width=$g.MeasureString($Text,$font,1000,$format).Width
 $state=$g.Save()
 $scale=[Math]::Min(1,530/$width)
 $g.TranslateTransform([float](320-$width*$scale/2),[float]$Top)
 $g.ScaleTransform([float]$scale,1)
 $g.DrawString($Text,$font,[Drawing.Brushes]::Black,1,1,$format)
 $brush=New-Object Drawing.SolidBrush($Color)
 $g.DrawString($Text,$font,$brush,0,0,$format)
 $brush.Dispose();$g.Restore($state);$font.Dispose()
}
Label 'POR CORTESÍA DE' 35 25 ([Drawing.Color]::White)
Label 'NO SE AUTORIZA LA DISTRIBUCIÓN DE ESTE' 228 18 ([Drawing.Color]::FromArgb(235,25,25))
Label 'PARCHE POR PARTE DE GRUPOS DE TERCEROS.' 249 18 ([Drawing.Color]::FromArgb(235,25,25))
Label 'TRADUCCIÓN Y PARCHE AL ESPAÑOL: D4n1984' 277 20 ([Drawing.Color]::White)
Label 'https://github.com/D4n1984/Grandia-Saturn-ES' 304 17 ([Drawing.Color]::White)
Label 'APOYA A LOS DESARROLLADORES.' 357 23 ([Drawing.Color]::White)
Label 'NO APOYES A LOS PIRATAS.' 390 23 ([Drawing.Color]::White)
$g.Flush()
$rect=New-Object Drawing.Rectangle 0,0,640,448
$bits=$bitmap.LockBits($rect,[Drawing.Imaging.ImageLockMode]::ReadOnly,[Drawing.Imaging.PixelFormat]::Format32bppArgb)
$bytes=New-Object byte[] (640*448*4)
[Runtime.InteropServices.Marshal]::Copy($bits.Scan0,$bytes,0,$bytes.Length)
$bitmap.UnlockBits($bits)
[IO.File]::WriteAllBytes($Salida,$bytes)
$g.Dispose();$bitmap.Dispose()
''',encoding='utf-8-sig')
    mask_path=OUT/'rotulos-bgra.raw'
    subprocess.run(['powershell','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(render),str(mask_path)],check=True)
    mask=bytearray(mask_path.read_bytes());assert len(mask)==640*448*4
    # Punto rojo incluido en la vista previa aprobada.
    pixel=(240*640+265)*4
    mask[pixel:pixel+4]=bytes((25,25,235,255))
    mask_path.write_bytes(mask)
    result=bytearray(source);cache={}
    for left,top,right,bottom in REGIONS:
        for y in range(top,bottom):
            for x in range(left,right):
                sample_x=(45+x%4) if top==225 else (10+x%16)
                result[address(x,y)]=source[address(sample_x,y)]
    for y in range(448):
        for x in range(640):
            off=(y*640+x)*4;b,g,r,a=mask[off:off+4]
            if not a:continue
            assert any(left<=x<right and top<=y<bottom for left,top,right,bottom in REGIONS),'Rótulo fuera de región revisada'
            target=address(x,y);bg=palette[result[target]]
            color=tuple((new*a+old*(255-a)+127)//255 for new,old in zip((r,g,b),bg))
            if color not in cache:cache[color]=min(range(256),key=lambda i:sum((v-c)**2 for v,c in zip(palette[i],color)))
            result[target]=cache[color]
    allowed={address(x,y) for left,top,right,bottom in REGIONS for y in range(top,bottom) for x in range(left,right)}
    assert len(result)==len(source)
    assert all(a==b or index in allowed for index,(a,b) in enumerate(zip(source,result)))
    assert source[:PIXELS]==result[:PIXELS] and source[PIXELS+640*448:]==result[PIXELS+640*448:]
    # El programa comprueba la suma unsigned del recurso completo. Actualizar
    # su constante, preservando todas las instrucciones de la comprobación.
    checksum_original=sum(source[0x2D930:0x73D3C])
    assert int.from_bytes(source[0x195C:0x1960],'big')==checksum_original
    checksum_new=sum(result[0x2D930:0x73D3C])
    result[0x195C:0x1960]=checksum_new.to_bytes(4,'big')
    assert all(a==b or index in allowed or 0x195C<=index<0x1960 for index,(a,b) in enumerate(zip(source,result)))
    dest=OUT/'0.bin';dest.write_bytes(result)
    report=[dict(ruta='0',sector=int(item['sector']),bytes=len(source),sha256_original=sha(source),
                 sha256_nuevo=sha(result),archivo=str(dest),regiones_texto=REGIONS,
                 checksum_offset=0x195C,checksum_original=checksum_original,checksum_nuevo=checksum_new,
                 preservado='Instrucciones; paleta; URL; logotipo; bordes; tamaño y resto de píxeles. Suma de recurso recalculada.')]
    (OUT/'manifiesto.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('Presentación preparada; código, logotipo, URL y paleta conservados.')


if __name__=='__main__':main()
