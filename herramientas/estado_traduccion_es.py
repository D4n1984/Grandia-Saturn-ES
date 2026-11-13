#!/usr/bin/env python3
"""Cuenta cobertura real de una hoja; no considera pendiente como traducido."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / 'trabajo/traduccion-en-es/textos-ingles-espanol.csv'
REVIEWED = {'revisado_editorial', 'verificado_emulador', 'aprobado_usuario'}


def status(path):
    raw = Path(path).read_bytes()
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not {'id', 'disco', 'categoria', 'espanol', 'ingles', 'revision', 'notas'} <= set(reader.fieldnames):
            raise ValueError('Cabecera incompleta')
        rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError('Columnas incorrectas')
    if not rows or len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Hoja vacía o con IDs duplicados')
    categories = defaultdict(Counter)
    pending = []; identical = []; review = []
    for r in rows:
        group = categories[f"D{r['disco']}/{r['categoria']}"]
        group['total'] += 1
        if not r['espanol'].strip():
            pending.append(r['id']); group['pendientes'] += 1
            continue
        group['traducidas'] += 1
        if r['espanol'] == r['ingles'] and not r['notas'].startswith(('sin_cambio_justificado:', 'conservar_nombre:')):
            identical.append(r['id'])
        if r['revision'] not in REVIEWED:
            review.append(r['id'])
        else:
            group['revisadas_editorialmente'] += 1
    return dict(sha256_hoja=hashlib.sha256(raw).hexdigest(), total=len(rows),
                traducidas=len(rows)-len(pending), pendientes=len(pending),
                pendientes_revision=len(review), identicas_sin_justificar=len(identical),
                completa=not pending and not review and not identical,
                grupos=dict(categories), ids_pendientes=pending,
                ids_pendientes_revision=review, ids_identicos_sin_justificar=identical,
                alcance='cobertura de la hoja; no acredita recursos fuera de ella ni ejecución')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hoja', type=Path, default=MASTER)
    p.add_argument('--informe', type=Path, default=ROOT/'trabajo/traduccion-en-es/estado-cobertura.json')
    p.add_argument('--exigir-completa', action='store_true')
    a = p.parse_args(); r = status(a.hoja)
    out = a.informe.resolve(); out.relative_to((ROOT/'trabajo').resolve())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"{r['traducidas']}/{r['total']} con español; {r['pendientes']} pendientes; {r['pendientes_revision']} por revisar; completa={r['completa']}")
    return int(a.exigir_completa and not r['completa'])


if __name__ == '__main__':
    sys.exit(main())
