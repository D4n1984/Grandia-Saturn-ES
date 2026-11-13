#!/usr/bin/env python3
"""Añade 16 glifos 8×8 al FDATA que ya contiene los glifos 8×16.

E2..F1 sustituyen kana del atlas EN: la comprobación de ausencia se limita a
las familias de listas documentadas, no acredita cadenas fuera del catálogo.
"""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from codificacion_es import SPANISH_TO_BYTE

ROOT=Path(__file__).resolve().parent.parent
BASE=0xAC00
SOURCE_SHA='26DD216A9409DDE00E37E248B8E0B31958BE025EEF8C42081D32606FC69E339A'
FONT16_SHA='FEE734334BEC4619DDC87CC85783115C3AB9859639AD705A691B77EFD2CAB5F0'
BASES='naeiouu?!NAEIOUU'


def sha(data): return hashlib.sha256(data).hexdigest().upper()


def body(tile):
    pixels=[p for b in tile for p in (b>>4,b&15)]
    return [sum(1<<(7-x) for x in range(8) if pixels[y*8+x]==14) for y in range(8)]


def pack(rows):
    # Original font uses body E and a one-pixel shadow at right and below.
    pixels=[[0]*8 for _ in range(8)]
    for y,row in enumerate(rows):
        for x in range(8):
            if row & (0x80>>x):
                for dx,dy in ((1,0),(0,1),(1,1)):
                    if x+dx<8 and y+dy<8:pixels[y+dy][x+dx]=1
    for y,row in enumerate(rows):
        for x in range(8):
            if row & (0x80>>x):pixels[y][x]=14
    flat=[p for row in pixels for p in row]
    return bytes((flat[i]<<4)|flat[i+1] for i in range(0,64,2))


def accented(source,char,base):
    rows=body(source[BASE+ord(base)*32:BASE+(ord(base)+1)*32])
    if char in '¿¡':
        return pack([int(f'{r:08b}'[::-1],2) for r in rows[::-1]])
    if char.isupper():
        # Five body rows leave two rows for the accent and one for shadow.
        live=[i for i,r in enumerate(rows) if r]
        first,last=min(live),max(live)
        old=rows[first:last+1]
        indices=([0,1,2,4,5] if base=='E' else [0,1,3,4,5]) if len(old)==6 else [round(i*(len(old)-1)/4) for i in range(5)]
        rows=[0,0]+[old[i] for i in indices]+[0]
    else:
        rows[0:2]=[0,0]
    if char in 'ñÑ':rows[0]=0x34
    elif char in 'üÜ':rows[0]=0x24
    else:rows[0:2]=[0x0C,0x18]
    return pack(rows)


def build(source,font16):
    if sha(source)!=SOURCE_SHA or sha(font16)!=FONT16_SHA:
        raise ValueError('Fuente inglesa o fuente 8×16 distinta de la comprobada')
    if len(source)!=len(font16) or source[BASE:BASE+8192]!=font16[BASE:BASE+8192]:
        raise ValueError('Atlas 8×8 ya modificado')
    checked=0
    families={'wdata':{2,6},'text2':{1,7},'bbg_region':{0,1,5}}
    with (ROOT/'trabajo/traduccion-en-es/tablas/tablas-respaldo.jsonl').open(encoding='utf8') as f:
        for line in f:
            r=json.loads(line)
            if r['tipo'] not in families:continue
            section=int(r.get('seccion',-1))
            if r['tipo'] in families and section in families[r['tipo']]:
                raw=bytes.fromhex(r['bytes_hex'])
                if any(b in SPANISH_TO_BYTE.values() for b in raw):
                    raise ValueError('Código español ya usado en una lista fuente: '+r['id'])
                checked+=1
    if not checked:raise ValueError('La auditoría de listas no comprobó entradas')
    out=bytearray(font16)
    for (char,code),base in zip(SPANISH_TO_BYTE.items(),BASES):
        out[BASE+code*32:BASE+(code+1)*32]=accented(source,char,base)
    start,end=BASE+0xE2*32,BASE+0xF2*32
    if out[:start]!=font16[:start] or out[end:]!=font16[end:]:
        raise AssertionError('Se alteraron bytes ajenos a los 16 glifos')
    return bytes(out),checked


def main():
    work=ROOT/'trabajo/prueba-es/glifos'
    source=(ROOT/'trabajo/fuente8-probe/FDATA_EN_D1.bin').read_bytes()
    out,checked=build(source,(work/'FDATA_ES_prueba.bin').read_bytes())
    dest=work/'FDATA_ES_completa.bin'
    if dest.exists() and dest.read_bytes()!=out:raise ValueError('Salida existente diferente')
    dest.write_bytes(out)
    report=dict(archivo=str(dest),sha256_original=sha(source),sha256_nuevo=sha(out),atlas8_offset=BASE,codigos={c:f'{b:02X}' for c,b in SPANISH_TO_BYTE.items()},entradas_auditadas=checked,limite='Sustituye kana E2..F1; pendiente de validación visual y de consumidores fuera del catálogo')
    (work/'fuente8-resultado.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(f'Fuente combinada preparada; {checked} entradas auditadas. Pendiente de comprobar en emulador.')


if __name__=='__main__':main()
