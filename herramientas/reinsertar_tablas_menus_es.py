"""Reinserción estructural de campos respaldados, sin escribir imágenes.

WDATA, TEXT2 y BBG reconstruyen offsets de sección, preservando las demás secciones.
Algunos tramos de ITGET, CMDMN, CNFIG, SVLD y SHOP permiten redistribuir longitud sin
crecimiento total; los demás overlays exigen longitud idéntica. Las ranuras
M_DAT admiten cambios dentro del relleno NUL. Las fuentes deben coincidir con
el respaldo; la capacidad de carga y el resultado visual siguen sin validar.
"""
from collections import defaultdict
from pathlib import Path
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / 'trabajo/traduccion-en-es'


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def records():
    specs = [('tablas/tablas-respaldo.jsonl', 'tabla'),
             ('tablas/bbg-ayuda-respaldo.jsonl', 'tabla'),
             ('menus/menus-respaldo.jsonl', 'menu'),
             ('menus-complementarios/menus-complementarios-raw.jsonl', 'complementario')]
    if (WORK/'menus-confirmados/menus-confirmados-raw.jsonl').is_file():
        specs.append(('menus-confirmados/menus-confirmados-raw.jsonl', 'complementario'))
    for name, family in specs:
        with (WORK / name).open(encoding='utf-8') as f:
            for line in f:
                r = json.loads(line)
                raw = bytes.fromhex(r['bytes_hex'])
                if family == 'tabla':
                    if sha(raw) != r['sha256'] or len(raw) != r['longitud']:
                        raise ValueError('Respaldo de campo corrupto: ' + r['id'])
                    for loc in r['ubicaciones']:
                        yield dict(id=r['id'], key=(int(loc['disco']), loc['ruta']),
                                   offset=int(loc['offset']), source=loc['sha256_fuente'].upper(),
                                   raw=raw, fixed=bytes.fromhex(r['campo_fijo_hex']) if 'campo_fijo_hex' in r else None,
                                   family=r['tipo'])
                else:
                    digest = r['sha256_campo_ingles'] if family == 'menu' else r['sha256_campo']
                    if not raw.endswith(b'\0') or sha(raw) != digest.upper():
                        raise ValueError('Respaldo de menú corrupto')
                    yield dict(id=r.get('id', r.get('id_traduccion')), key=(int(r['disco']), r['ruta']),
                               offset=int(r['offset_ingles']), source=(r.get('sha256_archivo_ingles') or r['sha256_archivo']).upper(),
                               raw=raw[:-1], fixed=None, family=family)


def controls(raw):
    """Conserva controles, cambios 03/04 y códigos 10-1F en charset 2."""
    out = []; i = 0; charset = 2
    while i < len(raw):
        b = raw[i]
        if b == 0:
            raise ValueError('NUL no permitido fuera de argumento 10xx')
        if charset == 2 and 0x10 <= b <= 0x1f:
            if i + 1 >= len(raw): raise ValueError('Código de dos bytes truncado')
            out.append(raw[i:i+2]); i += 2
        else:
            if b < 0x20 or b == 0x7f: out.append(raw[i:i+1])
            if b == 3: charset = 1
            elif b == 4: charset = 2
            i += 1
    return out


def entry_end(data, start, limit):
    pos = start; charset = 2
    while pos < limit:
        b = data[pos]
        if charset == 2 and 0x10 <= b <= 0x1f:
            pos += 2
        elif b == 0:
            return pos
        else:
            if b == 3: charset = 1
            elif b == 4: charset = 2
            pos += 1
    raise ValueError('Campo sin terminador dentro de tabla')


def bbg_parent(data, base):
    """Subdirectorio único que contiene el item y termina exactamente en EOF."""
    if int.from_bytes(data[:4], 'big') != 40: raise ValueError('Raíz BBG inesperada')
    root = [int.from_bytes(data[4*i:4*i+4], 'big') for i in range(10)]
    if root != sorted(root) or root[-1] >= base: raise ValueError('Raíz BBG inesperada')
    found = []
    for pos in range(root[-1], base, 4):
        if int.from_bytes(data[pos:pos+4], 'big') != 32: continue
        siblings = [int.from_bytes(data[pos+4*i:pos+4*i+4], 'big') for i in range(8)]
        if (siblings == sorted(siblings) and all(x % 4 == 0 for x in siblings)
                and pos+siblings[1] == base and pos+siblings[-1] == len(data)
                and siblings[2] > siblings[1]):
            found.append((pos, siblings))
    if len(found) != 1: raise ValueError(f'Subdirectorio BBG no único: {len(found)} candidatos')
    return found[0]


def reinsert(sources, translations, *, mode='bytes_fuente_no_validada', repairs=None, profiles=None):
    """sources: {(disco, ruta): bytes}; translations: {id: bytes sin NUL}.

    Devuelve archivos reconstruidos; nunca modifica fuentes. El modo identifica
    la fuente usada: el códec español de FDATA no acredita otras fuentes.
    repairs={(2,'BATLE/B108.BBG'): bytes_japoneses} habilita una reparación
    experimental de root[9], previa comprobación de ambas fuentes originales.
    No acredita capacidad de RAM ni funcionamiento en el juego.
    """
    if not isinstance(mode, str) or not mode: raise ValueError('Modo de fuente requerido')
    repairs = {} if repairs is None else repairs
    repair_key = (2, 'BATLE/B108.BBG')
    if set(repairs) - {repair_key} or any(k not in sources for k in repairs):
        raise ValueError('Reparación desconocida o sin fuente')
    rows = list(records()); known = {r['id'] for r in rows}
    unknown = set(translations) - known
    if unknown: raise ValueError('IDs desconocidos: ' + ', '.join(sorted(unknown)))
    grouped = defaultdict(list)
    for r in rows:
        if r['key'] in sources: grouped[r['key']].append(r)
        elif r['id'] in translations:
            raise ValueError(f'Falta fuente para copia {r["key"]}: {r["id"]}')
    result = {}
    for key, data in sources.items():
        if key not in grouped: raise ValueError(f'Fuente sin respaldo: {key}')
        rows_file = sorted(grouped[key], key=lambda r:r['offset'])
        digest = sha(data)
        if any(digest != r['source'] for r in rows_file): raise ValueError(f'SHA de fuente distinto: {key}')
        output = bytearray(data); previous_end = -1; variable = []; itget_changes = {}; cmdmn_changes = {}; cnfig_changes = {}; svld_changes = {}; shop_changes = {}
        if key in repairs:
            jp = repairs[key]
            if not isinstance(jp, bytes): raise TypeError('La fuente japonesa debe ser bytes')
            if digest != '643B008DAAA099B9D86BF661D3911CA494CCAE4046DF4D8D752572940F2A80E1' or sha(jp) != 'B3F631E9AD7081B6D14E4EAD805D18FF9B88C2D25701BB1DA1ABB04F429E81CB':
                raise ValueError('B108: SHA de fuente inglesa o japonesa no coincide')
            if len(jp) != 405988 or int.from_bytes(jp[36:40],'big') != 0x4c7b0 or int.from_bytes(jp[0x4c7b0:0x4c7b4],'big') != 32:
                raise ValueError('B108: cabecera japonesa inesperada')
            if len(data) != 430696 or int.from_bytes(data[36:40],'big') != 0x4c738:
                raise ValueError('B108: raíz inglesa inesperada')
            parent, siblings = bbg_parent(data, 327312)
            if parent != 0x4f52c or siblings != [32,2404,37340,64172,70824,81884,100428,105788]:
                raise ValueError('B108: subdirectorio inglés inesperado')
            output[36:40] = parent.to_bytes(4,'big')
        for r in rows_file:
            pos = r['offset']; old = r['raw']; slot = r['fixed']; size = len(slot) if slot is not None else len(old)+1
            if pos < previous_end: raise ValueError(f'Ubicaciones solapadas: {key} {pos:#x}')
            previous_end = pos+size
            expected = slot if slot is not None else old+b'\0'
            if data[pos:pos+size] != expected or (slot is not None and not slot.startswith(old+b'\0')):
                raise ValueError(f'Bytes de origen distintos: {r["id"]}')
            if r['id'] not in translations: continue
            new = translations[r['id']]
            if not isinstance(new, bytes): raise TypeError(f'Se requieren bytes: {r["id"]}')
            if profiles is not None and profiles.has(r['id']):
                profiles.validate(r['id'],old,new,record=r)
            elif controls(new) != controls(old): raise ValueError(f'Controles modificados: {r["id"]}')
            if new == old: continue
            if slot is None:
                if r['family'] in ('wdata', 'text2', 'bbg_region', 'bbg_ayuda_cola'):
                    variable.append((pos, old, new))
                elif r['id'].startswith('MENU-ITGET-') and key[1] == 'FIELD/ITGET.BIN':
                    itget_changes[r['id']] = new
                elif r['id'] in {f'MENU-CMDMN-{i:02}' for i in range(1,7)} and key[1] == 'FIELD/CMDMN.BIN':
                    cmdmn_changes[r['id']] = new
                elif r['id'] in {f'MENU-CNFIG-{i:02}' for i in range(1,10)} and key[1] == 'FIELD/CNFIG.BIN':
                    cnfig_changes[r['id']] = new
                elif key[1] == 'FIELD/SVLD.BIN' and r['family'] == 'complementario' and 0xb124 <= pos < 0xb23b:
                    svld_changes[pos] = new
                elif key[1] == 'FIELD/SHOP.BIN' and r['family'] == 'complementario' and pos in range(0xe192,0xe1d2,8):
                    shop_changes[pos] = new
                else:
                    if len(new) != len(old): raise ValueError(f'Longitud variable no acreditada para {r["id"]}')
                    output[pos:pos+size] = new+b'\0'
            else:
                if len(new)+1 > size: raise ValueError(f'Campo fijo excedido: {r["id"]} ({len(new)+1}>{size})')
                if any(slot[len(old)+1:]): raise ValueError(f'Relleno no NUL en campo fijo: {r["id"]}')
                output[pos:pos+size] = new + bytes(size-len(new))
        if itget_changes:
            items = sorted((r for r in rows_file if r['id'].startswith('MENU-ITGET-')), key=lambda r:r['offset'])
            if [r['id'] for r in items] != [f'MENU-ITGET-{i:02}' for i in range(1,9)]:
                raise ValueError(f'Tabla ITGET incompleta: {key}')
            start = items[0]['offset']; end = items[-1]['offset']+len(items[-1]['raw'])+1
            if start != 0xd358 or any(a['offset']+len(a['raw'])+1 != b['offset'] for a,b in zip(items,items[1:])):
                raise ValueError(f'Tabla ITGET discontinua: {key}')
            if sha(data[0x2e92:0x2f14]) != 'CDDD54D7A2441E014B7EED26E9A4337EB1DB9ADDD7436C6FEAC211DDCCA02DF5':
                raise ValueError(f'Consumidor ITGET distinto: {key}')
            if any(0x060b2000+start < int.from_bytes(data[p:p+4], 'big') < 0x060b2000+end for p in range(0,len(data)-3,4)):
                raise ValueError(f'Referencia absoluta interior ITGET: {key}')
            table = b''.join(itget_changes.get(r['id'], r['raw'])+b'\0' for r in items)
            if len(table) > end-start:
                raise ValueError(f'Tabla ITGET excedida: {len(table)}>{end-start} bytes en {key}')
            output[start:end] = table+bytes(end-start-len(table))
        if cnfig_changes:
            if sha(data[0x152a:0x15ac]) != 'F05932BA09480EFA9E3998B316D9836B59F7D0B39B3E979E7725912E5D2C7CDE':
                raise ValueError(f'Consumidor CNFIG distinto: {key}')
            for start, end in ((0x98b0,0x98df),(0x98df,0x990e)):
                items = {r['offset']:r for r in rows_file if r['id'] in cnfig_changes and start <= r['offset'] < end}
                if not items: continue
                if any(0x060b2000+start < int.from_bytes(data[p:p+4], 'big') < 0x060b2000+end for p in range(0,len(data)-3,4)):
                    raise ValueError(f'Referencia absoluta interior CNFIG: {key}')
                parts = []; pos = start; seen = set()
                while pos < end:
                    terminator = entry_end(data,pos,end); item = items.get(pos); raw = data[pos:terminator]
                    if item:
                        if item['raw'] != raw: raise ValueError(f'Límite CNFIG inesperado: {item["id"]}')
                        seen.add(item['id']); raw = cnfig_changes[item['id']]
                    parts.append(raw+b'\0'); pos = terminator+1
                if len(seen) != len(items): raise ValueError(f'Campos CNFIG fuera del recorrido: {key}')
                table = b''.join(parts)
                if len(table) > end-start: raise ValueError(f'Tabla CNFIG excedida: {len(table)}>{end-start} bytes en {key}')
                output[start:end] = table+bytes(end-start-len(table))
        if svld_changes:
            if sha(data[0x2c56:0x2cd8]) != '5CC6D4004FA1CBE0B70C7CA6E548F78D000E9DE5374C381EF1394F4BB4C043BB':
                raise ValueError(f'Consumidor SVLD distinto: {key}')
            for start,end in ((0xb124,0xb130),(0xb130,0xb148),(0xb148,0xb23b)):
                edits={p:v for p,v in svld_changes.items() if start <= p < end}
                if not edits: continue
                if any(0x060b2000+start < int.from_bytes(data[p:p+4], 'big') < 0x060b2000+end for p in range(0,len(data)-3,4)):
                    raise ValueError(f'Referencia absoluta interior SVLD: {key}')
                parts=[]; pos=start; seen=set()
                while pos < end:
                    terminator=entry_end(data,pos,end); raw=data[pos:terminator]
                    if pos in edits: seen.add(pos); raw=edits[pos]
                    parts.append(raw+b'\0'); pos=terminator+1
                if seen != set(edits): raise ValueError(f'Campos SVLD fuera del recorrido: {key}')
                table=b''.join(parts)
                if len(table)>end-start: raise ValueError(f'Tabla SVLD excedida: {len(table)}>{end-start} bytes en {key}')
                output[start:end]=table+bytes(end-start-len(table))
        if shop_changes:
            start,end,pointers=0xe192,0xe1d2,0xec30
            if sha(data[0x5fe0:0x60b0]) != '093F02FE19D8D5B52D861F6D8F449B4300AE25A57D14BBF6E876957B445CC9F0':
                raise ValueError(f'Consumidor SHOP distinto: {key}')
            expected={pointers+4*i:0x060b2000+start+8*i for i in range(8)}
            found={p:int.from_bytes(data[p:p+4],'big') for p in range(0,len(data)-3,4)
                   if 0x060b2000+start <= int.from_bytes(data[p:p+4],'big') < 0x060b2000+end}
            if found != expected: raise ValueError(f'Referencias SHOP distintas: {key}')
            items={r['offset']:r for r in rows_file if r['family']=='complementario' and r['offset'] in range(start,end,8)}
            if len(items)!=8: raise ValueError(f'Tabla SHOP incompleta: {key}')
            table=bytearray(); newptr=[]
            for pos in range(start,end,8):
                item=items[pos]
                if data[pos:pos+8] != item['raw']+b'\0\xff': raise ValueError(f'Ranura SHOP inesperada: {key} {pos:#x}')
                newptr.append(0x060b2000+start+len(table));table.extend(shop_changes.get(pos,item['raw'])+b'\0\xff')
            if len(table)>end-start: raise ValueError(f'Tabla SHOP excedida: {len(table)}>{end-start} bytes en {key}')
            output[start:end]=table+bytes(end-start-len(table))
            for i,p in enumerate(newptr): output[pointers+4*i:pointers+4*i+4]=p.to_bytes(4,'big')
        if cmdmn_changes:
            start, end = 0x16038, 0x16069
            if sha(data[0x8eda:0x8f60]) != 'BF6DC54FF22BD04BAB47D1305503C6BFB264BF911967A3D8E28729AC6BADFBB9':
                raise ValueError(f'Consumidor CMDMN distinto: {key}')
            if any(0x060b2000+start < int.from_bytes(data[p:p+4], 'big') < 0x060b2000+end for p in range(0,len(data)-3,4)):
                raise ValueError(f'Referencia absoluta interior CMDMN: {key}')
            items = {r['offset']:r for r in rows_file if r['id'] in {f'MENU-CMDMN-{i:02}' for i in range(1,7)}}
            if len(items) != 6: raise ValueError(f'Tabla CMDMN incompleta: {key}')
            parts = []; pos = start; seen = set()
            while pos < end:
                terminator = entry_end(data, pos, end); item = items.get(pos)
                raw = data[pos:terminator]
                if item:
                    if item['raw'] != raw: raise ValueError(f'Límite CMDMN inesperado: {item["id"]}')
                    seen.add(item['id']); raw = cmdmn_changes.get(item['id'], raw)
                parts.append(raw+b'\0'); pos = terminator+1
            if len(seen) != 6: raise ValueError(f'Campos CMDMN fuera del recorrido: {key}')
            table = b''.join(parts)
            if len(table) > end-start: raise ValueError(f'Tabla CMDMN excedida: {len(table)}>{end-start} bytes en {key}')
            output[start:end] = table+bytes(end-start-len(table))
        if variable:
            is_bbg = key[1].endswith('.BBG')
            count = 9 if is_bbg else 13 if key[1] == 'FIELD/WDATA.DAT' else 11 if key[1] == 'BATLE/TEXT2.BIN' else 0
            if not count: raise ValueError(f'Tabla no reconocida: {key}')
            base = 0; item_end = len(data)
            if is_bbg:
                with (ROOT/'inventario/bbg-regiones-ingles.csv').open(encoding='utf-8-sig', newline='') as f:
                    matches = [r for r in csv.DictReader(f) if int(r['disco']) == key[0] and r['ruta'] == key[1] and r['estado'] == 'cabecera_candidata_valida']
                if len(matches) != 1: raise ValueError(f'Región BBG no identificada: {key}')
                base = int(matches[0]['offset_region'])
                try: parent, siblings = bbg_parent(data, base)
                except ValueError as error: raise ValueError(f'{key}: {error}') from error
                root_parent = int.from_bytes(data[36:40], 'big')
                if parent != root_parent and key not in repairs:
                    raise ValueError(f'{key}: directorio BBG no coincide con root[9] ({parent:#x} != {root_parent:#x}); reparación de raíz pendiente')
                item_end = parent+siblings[2]
            offsets = [int.from_bytes(data[base+i*4:base+i*4+4], 'big') for i in range(count)]
            if offsets[0] != count*4 or any(x % 4 for x in offsets) or any(a >= b for a,b in zip(offsets,offsets[1:])) or base+offsets[-1] >= item_end:
                raise ValueError(f'Cabecera de secciones inesperada: {key}')
            bounds = [base+x for x in offsets] + [item_end]; chunks = []; new_offsets = []; cursor = count*4
            for i, (start, end) in enumerate(zip(bounds, bounds[1:])):
                chunk = bytearray(output[start:end])
                for pos, old, new in sorted((v for v in variable if start <= v[0] < end), reverse=True):
                    if pos+len(old) >= end: raise ValueError('Campo cruza sección')
                    chunk[pos-start:pos-start+len(old)] = new
                new_offsets.append(cursor); chunks.append(chunk); cursor += len(chunk)
                if i+1 < count and cursor % 4:
                    padding = 4-cursor%4; chunk.extend(bytes(padding)); cursor += padding
            item = bytearray().join(x.to_bytes(4,'big') for x in new_offsets)
            for chunk in chunks: item.extend(chunk)
            if is_bbg:
                item.extend(bytes(-len(item) % 4))
                delta = len(item)-(item_end-base)
                output = bytearray(output[:base]) + item + output[item_end:]
                for i in range(2,8):
                    output[parent+4*i:parent+4*i+4] = (siblings[i]+delta).to_bytes(4,'big')
            else: output = item
        result[key] = bytes(output)
    return result
