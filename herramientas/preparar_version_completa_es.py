#!/usr/bin/env python3
"""Construye recursos e imágenes solo tras acreditar cobertura editorial y QA.

Las imágenes intermedias y los paquetes permanecen privados. La conversión a
CHD verificada la realiza crear_parche_es.py al preparar el instalador JP->ES.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from estado_traduccion_es import status, MASTER, ROOT
from comprobar_traduccion_es import audit
from preparar_recursos_traducidos_es import prepare
from construir_imagen_recursos_es import build


def prepare_complete(sheet, output, version, *, repairs=(), extras=()):
    sheet = Path(sheet).resolve()
    sheet.relative_to((ROOT/'trabajo/traduccion-en-es').resolve())
    output = Path(output).resolve(); output.relative_to((ROOT/'trabajo').resolve())
    if not version or not version.replace('_', '').isalnum():
        raise ValueError('La versión debe usar letras, números y guion bajo')
    if output.exists(): raise ValueError('La carpeta de salida ya existe')
    original = sheet.read_bytes()
    coverage = status(sheet)
    if not coverage['completa']:
        raise ValueError(f"Traducción incompleta: {coverage['pendientes']} sin español, "
                         f"{coverage['pendientes_revision']} por revisar y "
                         f"{coverage['identicas_sin_justificar']} idénticas sin justificar")
    blockers = json.loads((ROOT/'inventario/bloqueos-version-es.json').read_text(encoding='utf-8'))
    pending = [b['id'] for b in blockers['bloqueos'] if b['estado'] != 'resuelto']
    if pending: raise ValueError('Cobertura adicional sin resolver: ' + ', '.join(pending))
    quality = audit(sheet, require_complete=True, structural=True, repairs=repairs)
    errors = [i['mensaje'] for i in quality['incidencias'] if i['nivel'] == 'ERROR']
    if errors: raise ValueError('; '.join(errors))
    if sheet.read_bytes() != original: raise ValueError('La hoja cambió durante la comprobación')
    report = prepare(sheet, output/'recursos', repairs=repairs)
    images = []
    for disc in (1, 2):
        manifest = output/f'recursos/manifiesto-D{disc}.json'
        if not manifest.is_file(): raise ValueError(f'No hay recursos D{disc}')
        manifests = [manifest]
        for extra in extras:
            extra = Path(extra).resolve(); extra.relative_to((ROOT/'trabajo').resolve())
            rows = json.loads(extra.read_text(encoding='utf-8-sig'))
            if not isinstance(rows, list) or not rows or any(int(r['disco']) not in (1, 2) for r in rows):
                raise ValueError('Manifiesto adicional sin disco válido')
            selected = [r for r in rows if int(r['disco']) == disc]
            if selected:
                dest = output/f'extra-D{disc}-{len(manifests)}.json'
                dest.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding='utf-8')
                manifests.append(dest)
        images.append(build(manifests, f'Grandia_ES_{version}_D{disc}', disc))
    result = dict(estado='candidato_completo_pendiente_pruebas_emulador',
                  sha256_hoja=hashlib.sha256(original).hexdigest(), cobertura=coverage,
                  calidad=quality, preparacion=report, imagenes=images)
    (output/'version.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hoja', type=Path, default=MASTER)
    p.add_argument('--salida', type=Path, required=True)
    p.add_argument('--version', required=True)
    p.add_argument('--reparar', action='append', choices=('2404', 'E414', 'B108'), default=[])
    p.add_argument('--extra-manifiesto', action='append', type=Path, default=[])
    a = p.parse_args()
    try: prepare_complete(a.hoja, a.salida, a.version, repairs=a.reparar, extras=a.extra_manifiesto)
    except (ValueError, OSError, KeyError) as e:
        print(str(e), file=sys.stderr); return 1
    return 0


if __name__ == '__main__': sys.exit(main())
