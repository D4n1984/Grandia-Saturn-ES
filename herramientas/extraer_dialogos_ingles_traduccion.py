#!/usr/bin/env python3
"""Exporta SCN ingleses, sus bloques conocidos y fragmentos adicionales, sin modificar juego."""
import argparse
import csv
import hashlib
import json
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INV = ROOT / 'inventario'
OUT = ROOT / 'trabajo/traduccion-en-es/dialogos'


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def encode(raw):
    protected = set()
    for i in range(max(0,len(raw)-3)):
        if raw[i:i+2] in (b'\x09\x0f',b'\x09\x0c'):
            protected.update(range(i,i+4))
    for i in range(max(0, len(raw)-5)):
        if raw[i] == 15 and raw[i+1] in (3,18,33) and raw[i+2] == 10:
            protected.update(range(i,i+6))
    return ''.join(chr(b) if 32 <= b <= 126 and b not in (60,62) and i not in protected else f'<{b:02X}>'
                   for i,b in enumerate(raw))


def decode(text):
    result = bytearray()
    i = 0
    while i < len(text):
        if text[i] == '<':
            token = text[i:i+4]
            if not re.fullmatch(r'<[0-9A-F]{2}>', token):
                raise ValueError('Marcador inválido')
            result.append(int(token[1:3],16)); i += 4
        else:
            n = ord(text[i])
            if not 32 <= n <= 126 or n == 62:
                raise ValueError('Carácter fuera de la codificación fuente')
            result.append(n); i += 1
    return bytes(result)


def immutable(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Respaldo existente distinto: '+str(path))
    else:
        path.write_bytes(data)


def csv_output(path, rows, editable=False):
    if not rows:
        raise ValueError('Salida vacía: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    if editable and path.exists():
        existing = read(path)
        stable = [k for k in rows[0] if k not in ('espanol','revision','notas')]
        if len(existing) != len(rows) or any(any(a[k] != str(b[k]) for k in stable) for a,b in zip(existing,rows)):
            raise ValueError('Hoja existente con fuentes distintas; se conserva: '+str(path))
        return
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def complete_headers(pieces, candidates, reviewed_tails=None, reviewed_instructions=None, size_overrides=None):
    """Amplía desde límites de pieza, sin buscar cabeceras dentro de los textos."""
    audit=[];reviewed_tails=reviewed_tails or {};reviewed_instructions=reviewed_instructions or {};size_overrides=size_overrides or {}
    by_piece=defaultdict(set)
    for key,start,size in candidates:by_piece[key].add((start,size))
    for key,(piece,body) in sorted(pieces.items()):
        previous=by_piece[key];valid=[];reasons=[]
        # 9xxx puede ser texto o instrucciones. No generalizarlo fuera del catálogo.
        for mode in ('9_catalogado','solo_2'):
            pos=0;frames=set();reason=''
            while pos+2<=len(body):
                if key in reviewed_tails and body[pos:]==reviewed_tails[key] and body[pos-2:pos]==b'\xf0\0':
                    pos=len(body);break
                word=int.from_bytes(body[pos:pos+2],'big');n=word&4095
                if word==0x7000 and key in reviewed_instructions:
                    pos+=reviewed_instructions[key];continue
                n=size_overrides.get((key,piece['offset']+pos),n)
                frame=(piece['offset']+pos,n)
                if word>>12==2 or (mode=='9_catalogado' and word>>12==9 and frame in previous):
                    payload=body[pos+2:pos+2+n]
                    if not n or len(payload)!=n or not (payload.endswith(b'\x07') or payload.endswith(b'\x07\0')):
                        reason='longitud_o_terminador_no_coherente';break
                    frames.add(frame);pos+=2+n
                else:pos+=2
            if not reason and pos!=len(body):reason='fin_de_pieza_no_exacto'
            if not reason and not previous.issubset(frames):reason='conflicto_con_bloques_previos'
            if reason:reasons.append(mode+':'+reason)
            else:valid.append((mode,frames))
        # Si dos recorridos compatibles discrepan, añadir solo sus coincidencias.
        accepted=set.intersection(*(frames for _,frames in valid)) if valid else set()
        added=accepted-previous
        for start,size in added:
            candidates[key,start,size]='cabecera_recuperada_por_recorrido_completo_sin_solapes'
        audit.append(dict(disco=key[0],ruta=key[1],ordinal_pieza=key[2],id_pieza=piece['id_hex'],
                          sha256_pieza=piece['sha256_pieza'],bloques_previos=len(previous),
                          bloques_recuperados=len(added),recorridos_validos=';'.join(mode for mode,_ in valid),
                          estado='recorrido_completo_compatible' if valid else 'conservar_sin_ampliar_requiere_revision',
                          observaciones=';'.join(reasons)))
    return audit


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--salida',type=Path,default=OUT)
    parser.add_argument('--prefijo',default='base-ingles-dialogos')
    parser.add_argument('--revision-limites',type=Path)
    parser.add_argument('--completar-cabeceras',action='store_true',help='Recuperar bloques omitidos mediante recorridos completos compatibles.')
    args=parser.parse_args()
    OUT=args.salida.resolve()
    OUT.relative_to((ROOT/'trabajo').resolve())
    if not re.fullmatch(r'[a-z0-9-]+',args.prefijo):parser.error('Prefijo inválido')
    refs = {(r['disco'],r['ruta']): r for r in read(INV/'comparacion-archivos-jp-en.csv')}
    original_pieces = {(r['disco'],r['ruta'],int(r['ordinal'])): r for r in read(INV/'mdt-piezas-extraidas.csv') if r['version']=='ingles'}
    pieces, files, archives, summary = {}, {}, [], []
    for disc in ('1','2'):
        paths = sorted((ROOT/'trabajo/ingles/analisis/mdt-extraidos'/('D'+disc)/'FIELD').glob('*.MDT'))
        expected = {route for (d,route),r in refs.items() if d==disc and route.endswith('.MDT') and r['sha256_ingles']}
        if {f'FIELD/{p.name}' for p in paths} != expected:
            raise ValueError('El conjunto de MDT no coincide con la base inglesa')
        for path in paths:
            route = 'FIELD/'+path.name
            raw = path.read_bytes(); ref=refs[disc,route]
            if sha(raw) != ref['sha256_ingles'].upper() or len(raw) != int(ref['bytes_ingles']):
                raise ValueError('MDT inglés distinto: '+str(path))
            files[disc,route] = raw
            ho,hl,so,sl = struct.unpack_from('>IIII',raw,0x58)
            if ho == so == 0xffffffff and hl == sl == 0:
                summary.append(dict(disco=disc,ruta=route,piezas=0,bytes_scn=0,sha256_scn='',bloques=0,fragmentos_adicionales=0,estado='sin_seccion_scn'))
                continue
            if ho<512 or so<512 or hl<8 or hl%4 or ho+hl>len(raw) or so+sl>len(raw):
                raise ValueError('Límites OFS/SCN inválidos')
            table=raw[ho:ho+hl];scn=raw[so:so+sl]
            if table[-4:] != b'\xff'*4:
                raise ValueError('Tabla OFS sin centinela')
            entries=[struct.unpack_from('>HH',table,i) for i in range(0,hl-4,4)]
            if not entries or entries[0][1] or any(a[1]>b[1] for a,b in zip(entries,entries[1:])) or entries[-1][1]>len(scn):
                raise ValueError('Entradas OFS inválidas')
            rebuilt=bytearray();seen=Counter()
            for ordinal,(ident,lo) in enumerate(entries):
                hi=entries[ordinal+1][1] if ordinal+1<len(entries) else len(scn)
                body=scn[lo:hi]; absolute=so+lo;key=disc,route,ordinal
                old=original_pieces[key]
                if absolute!=int(old['offset_archivo']) or sha(body)!=old['sha256_pieza'].upper() or len(body)!=int(old['longitud_bytes']):
                    raise ValueError('Pieza inglesa no coincide con la extracción previa')
                piece=dict(disco=disc,ruta=route,ordinal=ordinal,id_hex=f'{ident:04X}',ocurrencia=seen[ident],
                           offset=absolute,longitud=len(body),sha256_pieza=sha(body),sha256_mdt=sha(raw))
                seen[ident]+=1; pieces[key]=(piece,body)
                text=encode(body)
                if decode(text)!=body:raise ValueError('Pieza no reversible')
                archives.append(dict(**piece,bytes_hex=body.hex().upper(),codigo_conservado=text))
                rebuilt.extend(body)
            if bytes(rebuilt)!=scn:
                raise ValueError('Las piezas no conservan toda la sección SCN')
            summary.append(dict(disco=disc,ruta=route,piezas=len(entries),bytes_scn=len(scn),sha256_scn=sha(scn),
                                bloques=0,fragmentos_adicionales=0,estado='scn_completo_preservado_y_reconstruido_sin_cambios'))
    if set(pieces)!=set(original_pieces):
        raise ValueError('Cobertura de piezas inglesas incompleta')
    candidates={}
    for r in read(INV/'mdt-bloques-candidatos-ingles.csv'):
        key=r['disco'],r['ruta'],int(r['indice_entrada'])
        candidates[key,int(r['offset_bloque_ingles']),int(r['longitud_payload'])] = 'mdt-bloques-candidatos-ingles.csv'
    for name in ('mdt-dialogo-20-inicial.csv','mdt-dialogo-20-interno.csv'):
        for r in read(INV/name):
            if r['idioma']=='ingles':
                key=r['disco'],r['ruta'],int(r['ordinal'])
                candidates.setdefault((key,int(r['offset_bloque']),int(r['bytes_payload'])),name)
    reviewed_tails={};reviewed_instructions={};size_overrides={}
    if args.revision_limites:
        report_path=args.revision_limites.resolve();report_path.relative_to(ROOT.resolve())
        report=json.loads(report_path.read_text(encoding='utf-8'))
        decisions={r['id']:r for r in report['decisiones']}
        for reviewed in report['piezas']:
            key=str(reviewed['disco']),reviewed['ruta'],int(reviewed['ordinal'])
            piece,body=pieces[key]
            if piece['sha256_pieza']!=reviewed['sha256_pieza'] or piece['sha256_mdt']!=reviewed['sha256_mdt']:
                raise ValueError('Fuente de revisión distinta')
            verified=[];pos=0
            expected_offsets={int(x['offset_bloque']) for x in reviewed['bloques']}
            tail=bytes.fromhex(reviewed.get('cola_no_textual_hex',''))
            instruction_size=reviewed.get('instruccion_7000_bytes')
            if instruction_size:
                if instruction_size!=6:raise ValueError('Longitud de instrucción no admitida')
                reviewed_instructions[key]=instruction_size
            for block in reviewed['bloques']:
                if 'longitud_declarada' in block and block['longitud_declarada']!=block['longitud']:
                    relative=int(block['offset_bloque'])-piece['offset']
                    if int.from_bytes(body[relative:relative+2],'big')&4095!=block['longitud_declarada']:
                        raise ValueError('Longitud declarada de excepción distinta')
                    size_overrides[key,int(block['offset_bloque'])]=int(block['longitud'])
            while pos+2<=len(body):
                if tail and body[pos:]==tail and body[pos-2:pos]==b'\xf0\0':
                    reviewed_tails[key]=tail;pos=len(body);break
                word=int.from_bytes(body[pos:pos+2],'big')
                if word==0x7000 and instruction_size:
                    pos+=instruction_size;continue
                if word>>12==2 or (word>>12==9 and piece['offset']+pos in expected_offsets):
                    n=size_overrides.get((key,piece['offset']+pos),word&4095);payload=body[pos+2:pos+2+n]
                    if not n or len(payload)!=n or not (payload.endswith(b'\x07') or payload.endswith(b'\x07\0')):
                        raise ValueError('Caja de la revisión no termina coherentemente')
                    verified.append((piece['offset']+pos,n,sha(payload)))
                    pos+=2+n
                else:pos+=2
            if pos!=len(body) or verified!=[(int(x['offset_bloque']),int(x['longitud']),x['sha256_payload']) for x in reviewed['bloques']]:
                raise ValueError('La revisión no coincide con el recorrido completo de pieza')
            true_offsets={(a,n) for a,n,_ in verified}
            old=[k for k in candidates if k[0]==key]
            for candidate in old:
                _,offset,size=candidate
                if (offset,size) not in true_offsets:
                    identifier=f"EN-D{key[0]}-{Path(key[1]).stem}-P{key[2]:04}-B{offset:08X}"
                    decision=decisions.get(identifier)
                    rel=offset-piece['offset']
                    if not decision or not decision['decision'].startswith('excluir') or sha(body[rel+2:rel+2+size])!=decision['sha256_payload']:
                        raise ValueError('Ventana excluida sin evidencia explícita')
                del candidates[candidate]
            for offset,size,_ in verified:
                candidates[key,offset,size]='recorrido_completo_verificado_en_revision_de_limites'
    audit=complete_headers(pieces,candidates,reviewed_tails,reviewed_instructions,size_overrides) if args.completar_cabeceras else []
    masks=defaultdict(list); rows=[]; metadata=[]; backup=[]
    for (key,start,size),catalog in sorted(candidates.items()):
        piece,body=pieces[key];relative=start-piece['offset']
        if relative<0 or relative+2+size>len(body):
            raise ValueError('Bloque fuera de pieza')
        word=int.from_bytes(body[relative:relative+2],'big');payload=body[relative+2:relative+2+size]
        if (word&4095!=size and size_overrides.get((key,start))!=size) or word>>12 not in (2,9):
            raise ValueError('Cabecera de texto incompatible')
        encoded=encode(payload)
        if decode(encoded)!=payload:raise ValueError('Bloque no reversible')
        identifier=f"EN-D{key[0]}-{Path(key[1]).stem}-P{key[2]:04}-B{start:08X}"
        row=dict(id=identifier,disco=key[0],ruta=key[1],pieza=piece['id_hex'],offset=start+2,
                 ingles=encoded,espanol='',revision='',notas='Conservar controles; bloque candidato, no incluye la cabecera de longitud.')
        if word&4095!=size:
            row['notas']+=f' Excepción verificada: cabecera declara {word&4095} bytes; payload observado {size}. Revisar al reinsertar; fuente intacta.'
        rows.append(row)
        meta=dict(id=identifier,disco=key[0],ruta=key[1],ordinal_pieza=key[2],id_pieza=piece['id_hex'],
                  offset_bloque=start,offset_payload=start+2,longitud=size,longitud_declarada=word&4095,sha256_payload=sha(payload),
                  sha256_pieza=piece['sha256_pieza'],sha256_mdt=piece['sha256_mdt'],catalogo_origen=catalog,
                  estado='extraido_base_inglesa_controles_conservados_sin_traduccion')
        metadata.append(meta);backup.append(dict(**meta,cabecera_hex=f'{word:04X}',bytes_hex=payload.hex().upper()))
        masks[key].append((relative,relative+2+size))
    extras=[];extra_meta=[];extra_backup=[]
    for key,(piece,body) in sorted(pieces.items()):
        # Los fragmentos fuera de bloques se entregan aparte, sin confundir bytecode con diálogo confirmado.
        intervals=sorted(masks[key])
        merged=[]
        for lo,hi in intervals:
            if merged and lo<=merged[-1][1]:merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
            else:merged.append((lo,hi))
        for match in re.finditer(rb'[\x20-\x7e]{2,}',body):
            spans=[(match.start(),match.end())]
            for lo,hi in merged:
                spans=[part for a,b in spans for part in ((a,min(b,lo)),(max(a,hi),b)) if part[0]<part[1]]
                if not spans:break
            for lo,hi in spans:
                raw=body[lo:hi]
                if sum(65<=b<=90 or 97<=b<=122 for b in raw)<2:continue
                offset=piece['offset']+lo
                identifier=f"EN-D{key[0]}-{Path(key[1]).stem}-P{key[2]:04}-F{offset:08X}"
                value=encode(raw)
                if decode(value)!=raw:raise ValueError('Fragmento no reversible')
                extras.append(dict(id=identifier,disco=key[0],ruta=key[1],pieza=piece['id_hex'],offset=offset,
                                   ingles=value,espanol='',revision='',notas='Fragmento adicional: puede incluir parámetros, nombres técnicos o cabeceras; revisar antes de traducir.'))
                meta=dict(id=identifier,disco=key[0],ruta=key[1],ordinal_pieza=key[2],id_pieza=piece['id_hex'],
                          offset=offset,longitud=len(raw),sha256=sha(raw),sha256_pieza=piece['sha256_pieza'],
                          estado='fragmento_ascii_fuera_bloques_no_es_dialogo_confirmado')
                extra_meta.append(meta);extra_backup.append(dict(**meta,bytes_hex=raw.hex().upper()))
    counts=Counter((r['disco'],r['ruta']) for r in metadata);ecounts=Counter((r['disco'],r['ruta']) for r in extra_meta)
    for r in summary:r.update(bloques=counts[r['disco'],r['ruta']],fragmentos_adicionales=ecounts[r['disco'],r['ruta']])
    OUT.mkdir(parents=True,exist_ok=True)
    for name,data in [('piezas-respaldo.jsonl',archives),('dialogos-respaldo.jsonl',backup),('fragmentos-respaldo.jsonl',extra_backup)]:
        immutable(OUT/name,''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data).encode('utf-8'))
    csv_output(OUT/'dialogos-ingles-espanol.csv',rows,True)
    csv_output(OUT/'fragmentos-adicionales-revisar.csv',extras,True)
    csv_output(INV/(args.prefijo+'-campos.csv'),metadata)
    csv_output(INV/(args.prefijo+'-fragmentos.csv'),extra_meta)
    csv_output(INV/(args.prefijo+'-resumen.csv'),summary)
    if audit:csv_output(INV/(args.prefijo+'-auditoria-cabeceras.csv'),audit)
    print(f'{len(files)} MDT; {len(pieces)} piezas; {len(rows)} bloques; {len(extras)} fragmentos adicionales; todas las SCN conservadas')


if __name__=='__main__':
    main()
