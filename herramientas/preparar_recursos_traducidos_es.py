#!/usr/bin/env python3
"""Aplica traducciones de la hoja maestra a copias verificadas de los recursos EN.

No escribe imágenes ni modifica la hoja. Los caracteres españoles de listas y
texto estrecho requieren FDATA combinado; el texto de modo ancho queda protegido.
"""
import argparse
from collections import defaultdict
from contextlib import ExitStack
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'herramientas'))
from codificacion_es import encode_field, SPANISH_TO_BYTE
from extraer_dialogos_ingles_traduccion import decode
from inventariar_videos_bloques import read_movie
from reinsertar_guiones_es import rebuild, reparar_2404_opt_in, reparar_e414_opt_in
from reinsertar_tablas_menus_es import records, reinsert
from soporte_fuente8_es import build as build_font
from soporte_fuente_disco2_es import build as build_font_d2
from formatos_texto_es import validar_printf
from perfiles_residuales_es import ResidualProfiles


def rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def protected(text):
    # Includes printable parameters deliberately escaped by the extractor.
    return [s for s in re.findall(r'<[0-9A-F]{2}>', text) if s != '<01>']


def dialogue_controls(raw):
    """Permit line reflow while retaining 01 when it is a binary parameter."""
    out=[];pos=0
    while pos<len(raw):
        b=raw[pos];size=0
        if b==15 and pos+6<=len(raw) and raw[pos+1] in (3,18,33) and raw[pos+2]==10:size=6
        elif b==9 and pos+4<=len(raw) and raw[pos+1] in (11,12,15):size=4
        elif b==14 and pos+3<=len(raw) and raw[pos+1]==0:size=3
        elif b==16 and pos+2<=len(raw):size=2
        if size:out.append(raw[pos:pos+size]);pos+=size;continue
        if b<32 and b!=1 or b==127:out.append(raw[pos:pos+1])
        pos+=1
    return out


def prepare(sheet, output, identifiers=(), *, repairs=()):
    repairs=set(repairs)
    if repairs-{'2404','E414','B108'}:raise ValueError('Reparación inglesa desconocida')
    applied=[]
    output = Path(output).resolve()
    output.relative_to((ROOT/'trabajo').resolve())
    master = rows(sheet)
    if len({r['id'] for r in master}) != len(master):
        raise ValueError('IDs repetidos en la hoja')
    selected = {r['id']:r for r in master if r['espanol'].strip() and
                (not identifiers or r['id'] in identifiers)}
    if set(identifiers)-set(selected):
        raise ValueError('ID desconocido o sin español: '+', '.join(sorted(set(identifiers)-set(selected))))
    if not selected:
        raise ValueError('No hay traducciones seleccionadas')
    selected = {r['referencia']:r for r in selected.values()}
    if len(selected) != sum(bool(r['espanol'].strip()) and (not identifiers or r['id'] in identifiers) for r in master):
        raise ValueError('Referencias repetidas entre las traducciones seleccionadas')
    translations = {}
    residuals = ResidualProfiles(master_path=sheet)
    for identifier, r in selected.items():
        if residuals.has(identifier):
            residuals.validate(identifier, decode(r['ingles']), encode_field(r['espanol']), row=r)
        elif protected(r['ingles']) != protected(r['espanol']):
            raise ValueError('Controles o parámetros modificados: '+identifier)
        translations[identifier] = encode_field(r['espanol'])
    catalogs = defaultdict(list)
    for r in rows(ROOT/'inventario/base-ingles-dialogos-v5-campos.csv'):
        catalogs[int(r['disco']), r['ruta']].append(r)
    scripts = {i for i,r in selected.items() if r['categoria']=='dialogos'}
    table_ids = set(selected)-scripts
    table_records = [r for r in records() if r['id'] in table_ids] if table_ids else []
    if table_ids-{r['id'] for r in table_records}:
        raise ValueError('Familia no admitida por el reinsertor: '+', '.join(sorted(table_ids-{r['id'] for r in table_records})))
    for r in table_records:
        if decode(selected[r['id']]['ingles'])!=r['raw']:
            raise ValueError('Inglés de la hoja distinto del respaldo: '+r['id'])
        validar_printf(selected[r['id']]['ingles'],selected[r['id']]['espanol'])
    raw8_ids=set()
    narrow_sections={'wdata':{2,6},'text2':{1,7},'bbg_region':{0,1,5}}
    if table_ids:
        with (ROOT/'trabajo/traduccion-en-es/tablas/tablas-respaldo.jsonl').open(encoding='utf8') as f:
            for line in f:
                r=json.loads(line)
                if r['id'] in table_ids and r['tipo'] in narrow_sections and int(r['seccion']) in narrow_sections[r['tipo']]:raw8_ids.add(r['id'])
        for i in table_ids:
            if residuals.has(i): continue
            mode=1 if i in raw8_ids else 2
            tokens=re.findall(r'<[0-9A-F]{2}>|.',selected[i]['espanol'],re.DOTALL);pos=0
            while pos<len(tokens):
                token=tokens[pos];pos+=1
                if i not in raw8_ids and mode==2 and re.fullmatch(r'<1[0-9A-F]>',token):
                    if pos==len(tokens):raise ValueError('Parámetro ancho truncado: '+i)
                    if tokens[pos] in SPANISH_TO_BYTE:raise ValueError('Parámetro ancho no puede ser texto: '+i)
                    pos+=1;continue
                if i not in raw8_ids and token=='<03>':mode=1
                elif i not in raw8_ids and token=='<04>':mode=2
                elif token in SPANISH_TO_BYTE and mode!=1:
                    raise ValueError('Fuente de menú ancha o sin selector estrecho: '+i)
    by_resource = defaultdict(dict)
    if scripts:
        with (ROOT/'trabajo/traduccion-en-es/dialogos-verificados/dialogos-respaldo.jsonl').open(encoding='utf-8') as f:
            for line in f:
                r=json.loads(line)
                if r['id'] not in scripts: continue
                original=bytes.fromhex(r['bytes_hex'])
                row=selected[r['id']]
                if decode(row['ingles']) != original:
                    raise ValueError('Inglés de la hoja distinto del respaldo: '+r['id'])
                new=translations[r['id']]
                if residuals.has(r['id']):
                    residuals.validate(r['id'], original, new, row=row)
                elif dialogue_controls(original)!=dialogue_controls(new):
                    raise ValueError('Controles o parámetros binarios de diálogo modificados: '+r['id'])
                # The VM reads words: preserve even deltas and all terminators.
                if (len(new)-len(original)) & 1:
                    end=2 if new.endswith(b'\x07\0') else 1 if new.endswith(b'\x07') else 0
                    if not end: raise ValueError('Terminador de diálogo no reconocido')
                    new=new[:-end]+b' '+new[-end:]
                by_resource[int(row['disco']),row['ruta']][r['id']]=(original,new)
        if scripts-{i for edits in by_resource.values() for i in edits}:
            raise ValueError('Falta respaldo de diálogo')
    keys=set(by_resource)|{r['key'] for r in table_records}
    result={}; sources={}; locations={}
    with ExitStack() as stack:
        images={d:stack.enter_context((ROOT/f'trabajo/ingles/salida/Grandia_EN_D{d}.bin').open('rb')) for d in {k[0] for k in keys}}
        indices={d:{r['ruta']:r for r in rows(ROOT/f'trabajo/ingles/analisis/archivos-disco{d}.csv')} for d in images}
        def source(key):
            d,path=key
            if key not in sources:
                locations[key]=indices[d][path]
                sources[key]=read_movie(images[d],indices[d][path])
            return sources[key]
        for key,edits in by_resource.items():
            old=source(key); catalog=catalogs[key]
            if key==(1,'FIELD/2404.MDT') and '2404' in repairs:
                old,catalog=reparar_2404_opt_in(old,(ROOT/'trabajo/japones/mdt/D1/FIELD/2404.MDT').read_bytes(),catalog)
                applied.append('2404')
            if key==(2,'FIELD/E414.MDT') and 'E414' in repairs:
                old,catalog=reparar_e414_opt_in(old,catalog); applied.append('E414')
            result[key]=rebuild(old,catalog,edits)
        if table_ids:
            table_sources={key:source(key) for key in {r['key'] for r in table_records}}
            table_repairs={}
            if (2,'BATLE/B108.BBG') in table_sources and 'B108' in repairs:
                table_repairs[2,'BATLE/B108.BBG']=(ROOT/'trabajo/bbg-hud/jp-d2-B108.bin').read_bytes();applied.append('B108')
            result.update(reinsert(table_sources,{i:translations[i] for i in table_ids},mode='FDATA_8x8_y_8x16_ES_listas_y_estrecho',repairs=table_repairs,profiles=residuals))
        # D2 retains JP TEXT2 in the English patch. Derive it only for a full
        # selection of D1 TEXT2, including its closed residual profiles.
        text2_key=(1,'BATLE/TEXT2.BIN')
        text2_ids={r['id'] for r in records() if r['key']==text2_key}
        if (text2_key in result and text2_ids <= table_ids and
                any(residuals.has(i) for i in text2_ids)):
            from derivar_text2_disco2_es import derive
            for d in (1,2):
                if d not in images:
                    images[d]=stack.enter_context((ROOT/f'trabajo/ingles/salida/Grandia_EN_D{d}.bin').open('rb'))
                    indices[d]={r['ruta']:r for r in rows(ROOT/f'trabajo/ingles/analisis/archivos-disco{d}.csv')}
            d2key=(2,'BATLE/TEXT2.BIN'); wkey=(2,'FIELD/WDATA.DAT')
            if wkey not in result: raise ValueError('Falta WDATA D2 traducido para derivar TEXT2')
            result[d2key]=derive(source(d2key),result[text2_key],result[wkey])
        # Font bytes are accepted only against the exact source already proved.
        accent_discs={int(selected[i]['disco']) for i in scripts if any(c in SPANISH_TO_BYTE for c in selected[i]['espanol'])}
        accent_discs.update(r['key'][0] for r in table_records if any(c in SPANISH_TO_BYTE for c in selected[r['id']]['espanol']))
        for d in accent_discs:
            key=(d,'BIN/FDATA.BIN'); old=source(key)
            font16=ROOT/'trabajo/prueba-es/glifos/FDATA_ES_prueba.bin'
            if d==1:
                result[key],_=build_font(old,font16.read_bytes())
            elif d==2:
                if 1 not in images:
                    images[1]=stack.enter_context((ROOT/'trabajo/ingles/salida/Grandia_EN_D1.bin').open('rb'))
                    indices[1]={r['ruta']:r for r in rows(ROOT/'trabajo/ingles/analisis/archivos-disco1.csv')}
                original_d1=source((1,'BIN/FDATA.BIN'))
                combinado_d1,_=build_font(original_d1,font16.read_bytes())
                result[key]=build_font_d2(old,original_d1,combinado_d1)
            else:raise ValueError('Disco sin fuente española comprobada')
            if len(result[key])!=len(old): raise ValueError('Longitud de FDATA diferente')
    # Prepare and validate everything before writing. Never overwrite an experiment.
    if output.exists(): raise ValueError('La carpeta de salida ya existe')
    output.mkdir(parents=True)
    manifest=[]
    for (d,path),new in sorted(result.items()):
        dest=output/f'D{d}'/path; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(new)
        old=sources[d,path]; row=locations[d,path]
        manifest.append(dict(disco=d,ruta=path,sector=int(row['sector']),bytes=len(old),bytes_nuevos=len(new),sha256_original=sha(old),sha256_nuevo=sha(new),archivo=str(dest)))
    for d in {r['disco'] for r in manifest}:
        (output/f'manifiesto-D{d}.json').write_text(json.dumps([r for r in manifest if r['disco']==d],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=dict(hoja=str(Path(sheet).resolve()),sha256_hoja=sha(Path(sheet).read_bytes()),ids=sorted(r['id'] for r in selected.values()),reparaciones_experimentales=applied,recursos=manifest,estado='estructura_verificada_pendiente_emulador')
    (output/'resultado.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hoja',type=Path,default=ROOT/'trabajo/traduccion-en-es/textos-ingles-espanol.csv')
    p.add_argument('--salida',type=Path,required=True)
    p.add_argument('--id',action='append',default=[])
    p.add_argument('--reparar',action='append',choices=('2404','E414','B108'),default=[],help='Activar una reparación experimental de un defecto heredado, protegida por hashes exactos.')
    a=p.parse_args(); r=prepare(a.hoja,a.salida,set(a.id),repairs=a.reparar)
    print(f"{len(r['ids'])} traducciones; {len(r['recursos'])} recursos preparados. Pendiente de comprobar en emulador.")


if __name__=='__main__': main()
