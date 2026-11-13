#!/usr/bin/env python3
"""Audita la hoja EN->ES. Los informes y contextos permanecen en trabajo/."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from codificacion_es import encode_field
from formatos_texto_es import validar_printf
from extraer_dialogos_ingles_traduccion import decode
from preparar_recursos_traducidos_es import ROOT, dialogue_controls, prepare, protected
from reinsertar_tablas_menus_es import records, controls
from perfiles_residuales_es import ResidualProfiles

WORK = ROOT / 'trabajo/traduccion-en-es'


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def layout(raw, dialog):
    """Cuenta orientativamente por página y línea, omitiendo parámetros conocidos."""
    pages = [[0]]; mode = 2; i = 0
    while i < len(raw):
        b = raw[i]; size = 0
        if dialog:
            if b == 15 and i+6 <= len(raw) and raw[i+1] in (3,18,33) and raw[i+2] == 10: size = 6
            elif b == 9 and i+4 <= len(raw) and raw[i+1] in (11,12,15): size = 4
            elif b == 14 and i+3 <= len(raw) and raw[i+1] == 0: size = 3
            elif b == 16 and i+2 <= len(raw): size = 2
        elif mode == 2 and 0x10 <= b <= 0x1f and i+2 <= len(raw): size = 2
        if size:
            i += size; continue
        if b == 3: mode = 1
        elif b == 4: mode = 2
        elif dialog and b == 1: pages[-1].append(0)
        elif dialog and b == 8: pages.append([0])
        elif b >= 32 and b != 127: pages[-1][-1] += 1
        i += 1
    return pages


def chosen_profile(profile, row):
    if not profile: return None
    if 'columnas' in profile: return profile
    return profile.get('ids', {}).get(row['id']) or profile.get('categorias', {}).get(row['categoria'])


def validate_profiles(profile):
    if not profile: return
    entries = [profile] if 'columnas' in profile else [v for group in ('ids','categorias') for v in profile.get(group, {}).values()]
    for item in entries:
        if (not item.get('nombre') or not item.get('evidencia') or
                any(type(item.get(k)) is not int or item[k] < 1 for k in ('columnas','lineas'))):
            raise ValueError('Cada perfil requiere nombre, evidencia, columnas y líneas positivas')


def audit(sheet, require_complete=False, structural=False, repairs=(), profile=None):
    data = Path(sheet).read_bytes()
    with Path(sheet).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = reader.fieldnames or []
    required = {'id','categoria','disco','ruta','referencia','ingles','espanol'}
    if not required <= set(fields):
        raise ValueError('Faltan columnas obligatorias')
    issues = []
    def issue(level, code, row, message):
        issues.append(dict(nivel=level, codigo=code, id=row.get('id',''), mensaje=str(message)))
    if not rows: issue('ERROR','hoja',{},'La hoja está vacía')
    validate_profiles(profile)
    total = len(rows)
    valid_rows = []
    for line, row in enumerate(rows, 2):
        if None in row or any(value is None for value in row.values()):
            issue('ERROR','columnas',{'id': row.get('id') or ''},f'Fila CSV {line} con columnas ausentes o sobrantes')
        else:
            valid_rows.append(row)
    rows = valid_rows
    counts = Counter(r['id'] for r in rows)
    refs = Counter(r['referencia'] for r in rows)
    for value, count in counts.items():
        if not value or count != 1: issue('ERROR','id',{'id':value},'ID vacío o duplicado')
    for value, count in refs.items():
        if not value or count != 1: issue('ERROR','referencia',{'id':value},'Referencia vacía o duplicada')
    dialogs = {}
    with (WORK/'dialogos-verificados/dialogos-respaldo.jsonl').open(encoding='utf-8') as f:
        for line in f:
            x = json.loads(line); raw = bytes.fromhex(x['bytes_hex'])
            if sha(raw) != x['sha256_payload'].upper() or len(raw) != x['longitud']:
                raise ValueError('Respaldo de diálogo corrupto: '+x['id'])
            if x['id'] in dialogs: raise ValueError('ID duplicado en respaldo: '+x['id'])
            dialogs[x['id']] = x, raw
    tables = {}
    locations = {}
    for rec in records():
        if rec['id'] in tables and tables[rec['id']]['raw'] != rec['raw']:
            raise ValueError('Copias distintas en respaldo: '+rec['id'])
        tables.setdefault(rec['id'], rec)
        locations.setdefault(rec['id'], set()).add(rec['key'])
    pending = 0; translated = 0; visual = []
    residuals = ResidualProfiles(master_path=sheet)
    for row in rows:
        ref = row['referencia']; dialog = row['categoria'] == 'dialogos'
        rec = dialogs.get(ref) if dialog else tables.get(ref)
        if rec is None:
            issue('ERROR','respaldo',row,'Referencia ausente en respaldo'); continue
        raw = rec[1] if dialog else rec['raw']
        try:
            if decode(row['ingles']) != raw: issue('ERROR','ingles',row,'Inglés distinto del respaldo')
            if dialog and (str(rec[0]['disco']) != row['disco'] or rec[0]['ruta'] != row['ruta']):
                issue('ERROR','ubicacion',row,'Disco o ruta distintos del respaldo')
            if not dialog and (int(row['disco']),row['ruta']) not in locations[ref]:
                issue('ERROR','ubicacion',row,'Disco o ruta distintos del respaldo')
        except ValueError as e: issue('ERROR','ingles',row,e)
        text = row['espanol']
        if not text.strip(): pending += 1; continue
        translated += 1
        try:
            encoded = encode_field(text)
            if not dialog:
                try: validar_printf(row['ingles'], text)
                except ValueError as e: issue('ERROR','printf',row,e)
            if residuals.has(ref):
                residuals.validate(ref, raw, encoded, row=row)
            elif protected(row['ingles']) != protected(text):
                issue('ERROR','marcadores',row,'Controles o parámetros expresados como marcadores modificados')
            if residuals.has(ref):
                pass
            elif dialog:
                if dialogue_controls(raw) != dialogue_controls(encoded):
                    issue('ERROR','controles',row,'Controles o parámetros binarios modificados')
            elif controls(raw) != controls(encoded):
                issue('ERROR','controles',row,'Controles o parámetros binarios modificados')
            before = layout(raw, dialog); after = layout(encoded, dialog)
            selected = chosen_profile(profile, row)
            visual.append(dict(id=row['id'], paginas_es=after, paginas_ingles=before,
                               referencia=selected['nombre'] if selected else 'inglés de la misma entrada',
                               estado='estimación no acreditada en juego'))
            for page, lines in enumerate(after):
                reference = before[page] if page < len(before) else []
                columns = selected['columnas'] if selected else max(reference, default=0)
                line_limit = selected['lineas'] if selected else len(reference)
                if max(lines, default=0) > columns or len(lines) > line_limit:
                    origin = selected['nombre'] if selected else 'inglés de esta página'
                    issue('AVISO','perfil',row,f'Página {page+1}: {len(lines)} líneas, máximo {max(lines, default=0)} caracteres; referencia {origin}: {line_limit} líneas y {columns} caracteres. Revisar en juego')
        except ValueError as e: issue('ERROR','codificacion',row,e)
    if require_complete and pending: issue('ERROR','pendientes',{},f'{pending} traducciones pendientes')
    if structural and translated and not any(i['nivel']=='ERROR' for i in issues):
        try:
            with tempfile.TemporaryDirectory(prefix='qa-', dir=ROOT/'trabajo/calidad-traduccion') as tmp:
                prepare(sheet, Path(tmp)/'recursos', repairs=repairs)
        except (ValueError, OSError, KeyError) as e:
            groups = {}
            for row in rows:
                if row['espanol'].strip():
                    groups.setdefault(f"D{row['disco']}/{row['ruta']}", []).append(row['id'])
            issue('ERROR','estructural',{},'Falló la comprobación conjunta; no se identifica una fila responsable: '+str(e))
            issues[-1]['grupos_seleccionados'] = groups
    return dict(sha256_hoja=sha(data), total=total, traducidas=translated, pendientes=pending,
                estructural='ejecutada' if structural and translated and not any(i['codigo'] == 'estructural' for i in issues) and not any(i['nivel']=='ERROR' for i in issues) else 'no acreditada',
                perfil=profile, medidas_orientativas=visual, incidencias=issues)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hoja',type=Path,default=WORK/'textos-ingles-espanol.csv')
    p.add_argument('--exigir-completa',action='store_true')
    p.add_argument('--estructural',action='store_true')
    p.add_argument('--reparar',action='append',choices=('2404','E414','B108'),default=[])
    p.add_argument('--perfil',type=Path,help='JSON con nombre, evidencia, columnas y lineas; límites orientativos')
    p.add_argument('--informe',type=Path,default=ROOT/'trabajo/calidad-traduccion/informe.json')
    a=p.parse_args()
    destination=a.informe.resolve(); destination.relative_to((ROOT/'trabajo/calidad-traduccion').resolve())
    destination.parent.mkdir(parents=True,exist_ok=True)
    profile=json.loads(a.perfil.read_text(encoding='utf-8')) if a.perfil else None
    try: validate_profiles(profile)
    except ValueError as e: p.error(str(e))
    result=audit(a.hoja,a.exigir_completa,a.estructural,a.reparar,profile)
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    errors=sum(i['nivel']=='ERROR' for i in result['incidencias'])
    print(f"{result['traducidas']} traducidas; {result['pendientes']} pendientes; {errors} errores; informe: {destination}")
    return int(bool(errors))

if __name__=='__main__': raise SystemExit(main())

