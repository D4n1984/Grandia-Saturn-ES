#!/usr/bin/env python3
"""Aplicar un paquete experimental Grandia JP a ES con xdelta3 y SHA-256."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

class Error(ValueError):
    pass

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return {'size': path.stat().st_size, 'sha256': h.hexdigest()}

def name(s):
    if (not isinstance(s, str) or not s or s in ('.', '..') or
        re.search(r'[<>:"/\\|?*\x00-\x1f]', s) or s.endswith((' ', '.')) or
        s.split('.')[0].upper() in {'CON','PRN','AUX','NUL', *(f'COM{i}' for i in range(1,10)), *(f'LPT{i}' for i in range(1,10))}):
        raise Error(f'Nombre no válido: {s!r}')
    return s

def cue(path):
    text = path.read_text(encoding='utf-8-sig')
    files = []
    def replace(m):
        files.append(name(m.group(1)))
        return f'FILE "{{{len(files)-1}}}" BINARY'
    normalized = re.sub(r'^\s*FILE\s+"([^"]+)"\s+BINARY\s*$', replace, text, flags=re.I | re.M)
    if not files or re.search(r'^\s*FILE\b(?!\s+"\{\d+\}"\s+BINARY\s*$)', normalized, flags=re.I | re.M):
        raise Error('CUE no compatible: solo FILE "nombre" BINARY')
    if len({x.casefold() for x in files}) != len(files):
        raise Error('Pistas repetidas en CUE')
    return normalized.replace('\r\n','\n').strip() + '\n', files

def check(path, expected):
    if not path.is_file() or digest(path) != expected:
        raise Error(f'Tamaño o SHA-256 incorrecto: {path}')

def load(package):
    def pairs(items):
        d = {}
        for k,v in items:
            if k in d: raise Error(f'Clave duplicada: {k}')
            d[k] = v
        return d
    data = json.loads((package / 'manifiesto.json').read_text(encoding='utf-8'), object_pairs_hook=pairs)
    if data.get('formato') != 'grandia-xdelta3-v1' or data.get('disco') not in ('D1','D2'):
        raise Error('Manifiesto incompatible')
    for field in ('delta','xdelta','chdman'):
        entry = data[field]
        name(entry['nombre'])
        check(package / entry['nombre'], entry['identidad'])
    name(data['salida_bin'])
    name(data['salida_cue'])
    if len(data['pistas']) < 1 or not isinstance(data['cue_origen'], str) or not isinstance(data['cue_destino'], str):
        raise Error('Manifiesto incompleto')
    return data

def apply(package, source_cue, output):
    package, source_cue, output = package.resolve(), source_cue.resolve(), output.resolve()
    d = load(package)
    structure, files = cue(source_cue)
    if structure != d['cue_origen'] or len(files) != len(d['pistas']):
        raise Error('Estructura CUE de origen diferente de la esperada')
    paths = [source_cue.parent / x for x in files]
    for p, expected in zip(paths, d['pistas']):
        if p.resolve().parent != source_cue.parent:
            raise Error('La pista apunta fuera de la carpeta del CUE')
        check(p, expected)
    if output.exists(): raise Error(f'La carpeta de salida ya existe: {output}')
    if not output.parent.is_dir(): raise Error('La carpeta padre de salida no existe')
    with tempfile.TemporaryDirectory(prefix='.grandia-', dir=output.parent) as tmp:
        tmp = Path(tmp)
        source = tmp / 'origen.bin'
        with source.open('xb') as w:
            for p in paths:
                with p.open('rb') as r: shutil.copyfileobj(r, w, 1024 * 1024)
        # Check a second time: the source could have changed during concatenation.
        check(source, d['origen_concatenado'])
        result = tmp / name(d['salida_bin'])
        subprocess.run([str(package / d['xdelta']['nombre']), '-d', '-s', str(source), str(package / d['delta']['nombre']), str(result)], check=True)
        check(result, d['destino'])
        source.unlink()
        cue_out = tmp / name(d['salida_cue'])
        cue_out.write_text(d['cue_destino'], encoding='utf-8', newline='\n')
        chdman = str(package / d['chdman']['nombre'])
        chd = tmp / name(d['salida_chd'])
        subprocess.run([chdman, 'createcd', '-i', str(cue_out), '-o', str(chd)], check=True)
        subprocess.run([chdman, 'verify', '-i', str(chd)], check=True)
        extracted_cue = tmp / 'comprobacion.cue'
        extracted_bin = tmp / 'comprobacion.bin'
        subprocess.run([chdman, 'extractcd', '-i', str(chd), '-o', str(extracted_cue), '-ob', str(extracted_bin)], check=True)
        check(extracted_bin, d['destino'])
        extracted_cue.unlink(); extracted_bin.unlink(); cue_out.unlink(); result.unlink()
        # Same-volume rename is atomic; no existing output is overwritten.
        os.rename(tmp, output)
    print(f"{d['disco']} verificado: {output}")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('paquete', type=Path)
    p.add_argument('cue_japones', type=Path)
    p.add_argument('carpeta_salida', type=Path, help='Carpeta nueva, que no debe existir')
    a = p.parse_args()
    try: apply(a.paquete, a.cue_japones, a.carpeta_salida)
    except (Error, OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as e:
        print(f'Error: {e}', file=sys.stderr); return 1
    return 0
if __name__ == '__main__': sys.exit(main())
