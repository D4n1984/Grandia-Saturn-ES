#!/usr/bin/env python3
"""Contrasta las secciones japonesas TEXT2 de ambos discos y sus campos."""
import csv
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INV = ROOT/'inventario'


def read(name):
    with (INV/name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def original(disc):
    rows = [r for r in read(f'archivos-disco{disc}.csv') if r['ruta'] == 'BATLE/TEXT2.BIN']
    images = list((ROOT/f'trabajo/originales/disco{disc}').glob('*Track 1*.bin'))
    if len(rows) != 1 or len(images) != 1:
        raise ValueError(f'Fuente ambigua para el disco {disc}')
    row = rows[0]; size = int(row['bytes']); data = bytearray()
    with images[0].open('rb') as f:
        f.seek(int(row['sector'])*2352)
        while len(data) < size:
            sector = f.read(2352)
            if len(sector) != 2352:
                raise ValueError('Pista truncada')
            data.extend(sector[16:2064])
    data = bytes(data[:size])
    comparison = next(r for r in read('comparacion-archivos-jp-en.csv')
                      if r['disco'] == str(disc) and r['ruta'] == 'BATLE/TEXT2.BIN')
    if sha(data) != comparison['sha256_japones'].upper():
        raise ValueError('Hash de TEXT2 incorrecto')
    return data


def main():
    a,b = original(1),original(2)
    offsets = [[int.from_bytes(data[i:i+4],'big') for i in range(0,44,4)]+[len(data)] for data in (a,b)]
    if offsets[0] != offsets[1] or offsets[0][0] != 44 or offsets[0] != sorted(offsets[0]):
        raise ValueError('Cabeceras o límites de sección distintos')
    sections = []
    for i,(start,end) in enumerate(zip(offsets[0],offsets[0][1:])):
        first,second=a[start:end],b[start:end]
        sections.append(dict(seccion=i,offset=start,bytes=end-start,sha256_jp_d1=sha(first),
                             sha256_jp_d2=sha(second),bytes_distintos=sum(x!=y for x,y in zip(first,second)),
                             estado='identica' if first==second else 'diferente'))
    entries = read('text2-entradas.csv')
    classifications = {(r['seccion'],r['indice']):r for r in read('text2-clasificacion.csv') if r['disco']=='1'}
    d2 = {(r['seccion'],r['offset_ingles']):r for r in entries if r['disco']=='2'}
    rows = []
    for r in entries:
        if r['disco'] != '1' or not r['offset_japones_candidato']:
            continue
        offset = int(r['offset_japones_candidato']); end = a.find(b'\x00',offset,offsets[0][int(r['seccion'])+1])
        match = d2.get((r['seccion'],str(offset)))
        if end < 0 or not match or a[offset:end+1] != b[offset:end+1] or int(match['bytes_ingles']) != end-offset:
            continue
        c = classifications[(r['seccion'],r['indice'])]
        rows.append(dict(disco='2',ruta='BATLE/TEXT2.BIN',seccion=r['seccion'],offset_japones=offset,
                         bytes_japones=end-offset,sha256_japones=sha(b[offset:end]),
                         indice_campo_disco2=match['indice'],indice_ingles_disco1=r['indice'],
                         offset_ingles_disco1=r['offset_ingles'],categoria_provisional=c['categoria'],
                         estado='bytes_japoneses_identicos_equivalencia_inglesa_por_indice_sin_validar'))
    if not rows:
        raise ValueError('Sin coincidencias de campos')
    for path, data in ((INV/'text2-secciones-jp-discos.csv',sections), (INV/'text2-disco2-campos-compartidos.csv',rows)):
        with path.open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(data[0])); writer.writeheader(); writer.writerows(data)
    print(f'{len(sections)} secciones; {sum(r["estado"]=="identica" for r in sections)} idénticas; {len(rows)} campos compartidos con candidato inglés')


if __name__ == '__main__':
    main()
