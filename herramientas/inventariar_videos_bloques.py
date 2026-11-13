#!/usr/bin/env python3
"""Relaciona bloques candidatos de vídeo por ordinal en ambos idiomas."""
import csv
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha(b):
    return hashlib.sha256(b).hexdigest().upper()


def read_movie(track, item):
    length, sector = int(item['bytes']), int(item['sector'])
    out = bytearray()
    for off in range(0, length, 2048):
        track.seek((sector + off // 2048) * 2352 + 16)
        out.extend(track.read(min(2048, length - off)))
    if len(out) != length:
        raise ValueError('Pista incompleta')
    return bytes(out)


def scan(blob):
    table, pos, frames, audio = 0x284, 0x1c000, [], 0
    while table + 2 <= 0x4000:
        size = int.from_bytes(blob[table:table+2], 'big'); table += 2
        if size == 0:
            break
        if size == 12:
            if table + 2 > 0x4000:
                raise ValueError('Marcador de audio truncado')
            table += 2; pos += 0x6000; audio += 1
            continue
        if size < 16 or pos + size > len(blob):
            raise ValueError('Bloque fuera del archivo')
        block = blob[pos:pos+size]
        frames.append((pos, size, block[2], block[3], sha(block)))
        pos += size
    else:
        raise ValueError('La tabla no terminó dentro de la cabecera')
    if pos != len(blob):
        raise ValueError('El recorrido no alcanza el final del archivo')
    return frames, audio


def write(path, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def main():
    with (ROOT / 'inventario/comparacion-archivos-jp-en.csv').open(encoding='utf-8-sig', newline='') as f:
        refs = {(r['disco'], r['ruta']): r for r in csv.DictReader(f)}
    summary, details = [], []
    for disc in (1, 2):
        sources = {}
        for lang in ('jp', 'en'):
            inv = ROOT / (f'inventario/archivos-disco{disc}.csv' if lang == 'jp' else f'trabajo/amap-probe/english-d{disc}-files.csv')
            with inv.open(encoding='utf-8-sig', newline='') as f:
                sources[lang] = {r['ruta']: r for r in csv.DictReader(f) if r['ruta'].endswith('.MOV')}
        if sources['jp'].keys() != sources['en'].keys():
            raise ValueError('Las rutas de vídeo no coinciden')
        jp_path = next((ROOT / f'trabajo/originales/disco{disc}').glob('*Track 1*.bin'))
        en_path = ROOT / f'trabajo/ingles/salida/Grandia_EN_D{disc}.bin'
        with jp_path.open('rb') as jp_track, en_path.open('rb') as en_track:
            for route in sorted(sources['jp']):
                movies = []
                for lang, track, field in (('jp', jp_track, 'sha256_japones'), ('en', en_track, 'sha256_ingles')):
                    blob = read_movie(track, sources[lang][route])
                    if sha(blob) != refs[(str(disc), route)][field].upper():
                        raise ValueError(f'Hash incorrecto: {disc}/{lang}/{route}')
                    movies.append(scan(blob))
                (jp, jp_audio), (en, en_audio) = movies
                if len(jp) != len(en):
                    raise ValueError(f'Recuentos distintos: {disc}/{route}')
                changed = 0
                for i, (a, b) in enumerate(zip(jp, en), 1):
                    different = a[4] != b[4]; changed += different
                    details.append(dict(disco=disc, ruta=route, ordinal=i, offset_jp_hex=hex(a[0]), bytes_jp=a[1],
                        dimensiones_jp=f'{a[2]}x{a[3]}', sha256_jp=a[4], offset_en_hex=hex(b[0]), bytes_en=b[1],
                        dimensiones_en=f'{b[2]}x{b[3]}', sha256_en=b[4], diferente='si' if different else 'no',
                        estado='bloque_candidato_sin_decodificar_ni_validar_en_juego'))
                summary.append(dict(disco=disc, ruta=route, bloques_candidatos=len(jp), bloques_diferentes=changed,
                    marcadores_audio_jp=jp_audio, marcadores_audio_en=en_audio,
                    estado='limites_estructurales_no_validados_visualmente'))
    write(ROOT / 'inventario/videos-bloques-candidatos.csv', details)
    write(ROOT / 'inventario/videos-resumen-bloques.csv', summary)
    print(f'{len(summary)} vídeos; {len(details)} parejas de bloques candidatos')


if __name__ == '__main__':
    main()
