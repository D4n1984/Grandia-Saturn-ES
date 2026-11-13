"""Reinserción conservadora de cajas catalogadas. No es un desensamblador universal.

API: rebuild(source, catalog, edits), catalog = filas v5 del MDT, edits =
{id: (payload_original, payload_nuevo)}. Requiere recorrido íntegro y sin
operandos desconocidos de cada pieza modificada. No modifica archivos.
"""
from __future__ import annotations
import hashlib
from collections import defaultdict
from dataclasses import dataclass

class MDTError(ValueError): pass

def u32(b, p): return int.from_bytes(b[p:p+4], 'big')
def put32(b, p, n):
    if not 0 <= n <= 0xffffffff: raise MDTError('desbordamiento de descriptor')
    b[p:p+4] = n.to_bytes(4, 'big')
def sha(b): return hashlib.sha256(b).hexdigest().upper()

@dataclass(frozen=True)
class Layout:
    ofs: int
    scn: int
    size: int
    entries: tuple
    graphics_end: int
    footer: int

def layout(src):
    if len(src)<512: raise MDTError('tamaño MDT inválido')
    ofs, ol, scn, sl = (u32(src,p) for p in (0x58,0x5c,0x60,0x64))
    if (ofs,ol,scn,sl)==(0xffffffff,0,0xffffffff,0): return None
    ge=u32(src,0x1fc); footer=u32(src,0x180)*2048
    if u32(src,0x1f4)*2048!=footer: raise MDTError('sectores de footer inconsistentes')
    if not (512<=ofs and ol>=8 and ol%4==0 and ofs+ol==scn and scn+sl<=ge<=footer<=len(src)):
        raise MDTError('límites OFS/SCN/gráficos inválidos')
    table=src[ofs:scn]
    if table[-4:]!=b'\xff'*4: raise MDTError('falta centinela OFS')
    entries=tuple((int.from_bytes(table[i:i+2],'big'),int.from_bytes(table[i+2:i+4],'big')) for i in range(0,ol-4,4))
    if not entries or entries[0][1]!=0 or any(a[1]>b[1] for a,b in zip(entries,entries[1:])) or entries[-1][1]>sl:
        raise MDTError('límites de pieza inválidos')
    return Layout(ofs,scn,sl,entries,ge,footer)

def _scan(body, blocks, *, validate_refs=True, allow_d0_tail=False, exception_positions=frozenset()):
    """Recorre cajas catalogadas y comandos reconocidos del dispatcher SCNRL.

    Verifica spans y saltos relativos; rechaza comandos desconocidos, destinos
    fuera de limites y longitudes excepcionales. 9NNN solo se admite en el
    catalogo, nunca mediante busqueda de bytes dentro de texto.
    """
    pos=0; spans=[]; refs=[]; boundaries={0}; found=set()
    while pos<len(body):
        if pos+2>len(body): raise MDTError('cola impar')
        w=int.from_bytes(body[pos:pos+2],'big'); kind=w>>12
        if pos in blocks:
            n=blocks[pos]; end=pos+2+n
            if kind not in (2,9) or ((w&4095)!=n and not (pos in exception_positions and w==0x202a and n==38)) or not n or end>len(body): raise MDTError('caja incompatible o longitud excepcional')
            if not (body[pos+2:end].endswith(b'\x07') or body[pos+2:end].endswith(b'\x07\0')): raise MDTError('terminador de caja inválido')
            found.add(pos); pos=end
        elif kind==3:
            end=pos+2+(w&4095)
            if end>len(body): raise MDTError(f'span en {pos:#x} destino {end:#x} fuera de pieza {len(body):#x}')
            spans.append((pos,end,w&4095)); pos+=2
        elif kind==1:
            pos+=2
        elif kind in (4,6):
            if kind==4 and not w&0x0800:
                size=4
            else:
                if pos+4>len(body): raise MDTError(f'descriptor 40/60 truncado en {pos:#x}')
                descriptor=int.from_bytes(body[pos+2:pos+4],'big')
                size=8 if w&0x0400 and descriptor>>14==3 else 6
            if kind==4 and w&0x70==0x30:
                operand=pos+size; size+=2
                if pos+size>len(body): raise MDTError(f'span 40 truncado en {pos:#x}')
                distance=int.from_bytes(body[operand:operand+2],'big')
                refs.append((operand,operand+2,operand+2+distance,False))
            if pos+size>len(body): raise MDTError(f'operando 40/60 truncado en {pos:#x}')
            pos+=size
        elif w&0xfff0==0x5000:
            if pos+4>len(body): raise MDTError(f'operando 50 truncado en {pos:#x}')
            pos+=4
        elif kind==7:
            if pos+4>len(body): raise MDTError(f'descriptor 70 truncado en {pos:#x}')
            descriptor=int.from_bytes(body[pos+2:pos+4],'big')
            count=(w&15)+1; kind_arg=descriptor>>14
            size=(0,(count+1)&~1,count*2,count*4)[kind_arg]
            if pos+4+size>len(body): raise MDTError(f'operando 70 truncado en {pos:#x}')
            pos+=4+size
        elif kind==8:
            if pos+4>len(body): raise MDTError(f'salto 8 truncado en {pos:#x}')
            distance=int.from_bytes(body[pos+2:pos+4],'big',signed=True)
            refs.append((pos+2,pos+4,pos+4+distance,True))
            pos+=4
        elif w==0xf000:
            pos+=2
            # Dos bytes finales tras F000: cola ASCII o residuo de nombre D0xx. No se
            # publica su inicio como destino valido en el analisis global.
            if not any(body[pos:]) or (pos not in blocks and len(body)-pos>=2 and ((allow_d0_tail and body[pos:pos+2]!=b'\xf0\0' and not any(body[pos+2:])) or (pos==2 and len(body)==4) or (len(body)-pos==2 and all(32<=x<=126 for x in body[pos:])))): pos=len(body)
        else:
            raise MDTError(f'instrucción no modelada {w:04X} en {pos:#x}')
        boundaries.add(pos)
    if found!=set(blocks): raise MDTError('catálogo no coincide con recorrido')
    for start,end,_ in spans:
        if end not in boundaries: raise MDTError(f'span en {start:#x} destino {end:#x} no es limite')
    for operand,origin,target,signed in refs:
        if validate_refs and target not in boundaries: raise MDTError(f'salto {"8" if signed else "40"} en {operand-2:#x} destino {target:#x} no es limite')
    return spans, refs, boundaries

_AUDIT_CACHE = {}
def _audit_scn(source, lay, catalog):
    """Recorre todas las piezas y valida saltos usando limites globales SCN."""
    key=(sha(source),tuple((r['id'],r['ordinal_pieza'],r['offset_bloque'],r['longitud']) for r in catalog))
    if key in _AUDIT_CACHE: return _AUDIT_CACHE[key]
    by_piece=defaultdict(dict); exception_by_piece=defaultdict(set)
    for r in catalog:
        i=int(r['ordinal_pieza'])
        if not 0<=i<len(lay.entries): raise MDTError('ordinal catalogado fuera de OFS')
        pos=int(r['offset_bloque'])-lay.scn-lay.entries[i][1]
        if pos in by_piece[i]: raise MDTError('cajas catalogadas duplicadas')
        by_piece[i][pos]=int(r['longitud'])
        if r['id']=='EN-D2-E414-P0000-B0000179A': exception_by_piece[i].add(pos)
    boundaries=set(); refs=[]
    for i,(_,lo) in enumerate(lay.entries):
        hi=lay.entries[i+1][1] if i+1<len(lay.entries) else lay.size
        try: spans,local,bounds=_scan(source[lay.scn+lo:lay.scn+hi],by_piece[i],validate_refs=False, allow_d0_tail=(lay.entries[i][0]>>8 in (0xc0,0xd0) and bool(by_piece[i])), exception_positions=exception_by_piece[i])
        except MDTError as exc: raise MDTError(f'SCN pieza {i}: {exc}') from exc
        boundaries.update(lo+x for x in bounds)
        refs.extend((lo+op,lo+origin,lo+target,signed) for op,origin,target,signed in local)
    for op,origin,target,signed in refs:
        if target not in boundaries: raise MDTError(f'SCN salto en {op-2:#x} destino {target:#x} no es limite')
    result=(tuple(refs),frozenset(boundaries))
    if len(_AUDIT_CACHE)>=2: _AUDIT_CACHE.clear()
    _AUDIT_CACHE[key]=result
    return result

_2404_EN_SHA = '5233F42CF365B870B88E25BEFEC65D1A5A5EB58D739BA1ADA7DD7D031F06D212'
_2404_JP_SHA = '12BA8131960A65A1959BBF3BE010836C3062795D0AAD0B56245F77254EA15559'

def reparar_2404_opt_in(source, japanese_source, catalog):
    """Repara explicitamente 39CE -> 3C0A en D1/2404, fuentes exactas.

    Devuelve (bytes reparados, catalogo copiado con hashes actualizados).
    El cotejo con el MDT japones exacto comprueba la posicion F000 original.
    No modifica ningun archivo y rebuild() nunca invoca esta funcion.
    """
    source=bytes(source); japanese_source=bytes(japanese_source)
    if sha(source)!=_2404_EN_SHA or sha(japanese_source)!=_2404_JP_SHA:
        raise MDTError('2404: hashes de fuentes inglesa/japonesa inesperados')
    a=layout(source); j=layout(japanese_source)
    if (a.scn,j.scn)!=(0x4de0,0x4de0) or len(a.entries)<3 or len(j.entries)<3:
        raise MDTError('2404: cabeceras de pieza inesperadas')
    if (a.scn+a.entries[1][1],a.scn+a.entries[2][1],j.scn+j.entries[1][1],j.scn+j.entries[2][1])!=(0x4df4,0x5a0e,0x4df4,0x57d2):
        raise MDTError('2404: limites de pieza inesperados')
    if source[0x4e00:0x4e02]!=b'\x39\xce' or japanese_source[0x4e00:0x4e02]!=b'\x39\xce' or source[0x5a0c:0x5a0e]!=b'\xf0\x00' or japanese_source[0x57d0:0x57d2]!=b'\xf0\x00':
        raise MDTError('2404: span o terminador original inesperado')
    if not catalog or any(r['disco']!='1' or r['ruta']!='FIELD/2404.MDT' or r['sha256_mdt'].upper()!=_2404_EN_SHA for r in catalog):
        raise MDTError('2404: catalogo no corresponde a fuente exacta')
    piece_old=source[0x4df4:0x5a0e]
    if any(r['sha256_pieza'].upper()!=sha(piece_old) for r in catalog if int(r['ordinal_pieza'])==1):
        raise MDTError('2404: hash original de pieza no coincide')
    patched=bytearray(source); patched[0x4e00:0x4e02]=b'\x3c\x0a'; patched=bytes(patched)
    patched_sha=sha(patched); piece_sha=sha(patched[0x4df4:0x5a0e]); updated=[]
    for r in catalog:
        copy=dict(r); copy['sha256_mdt']=patched_sha
        if int(r['ordinal_pieza'])==1: copy['sha256_pieza']=piece_sha
        updated.append(copy)
    _audit_scn(patched,layout(patched),updated)
    return patched,updated

_E414_EN_SHA = '96101AD53C6BD1933ACA9B7FA2AD0C9337C97A82FE05F48E37E04E91F11981E3'
_E414_FIXED_SHA = '478E562A6902E029374062625B332417C7BCDCC3435B2EB7E664BAB93CE9B538'

def reparar_e414_opt_in(source, catalog):
    """Corrige 202A a 2026 en el E414 ingles exacto, sin modificar archivos.

    El handler suma la longitud declarada al PC del payload; 42 salta a 17C6
    dentro del comando 7000, mientras 38 llega a su inicio 17C2. Devuelve
    bytes y catalogo copiado con hashes y longitud declarada actualizados.
    """
    source=bytes(source)
    if sha(source)!=_E414_EN_SHA: raise MDTError('E414: hash de fuente inesperado')
    if source[0x179a:0x179c]!=b'\x20\x2a' or source[0x17c0:0x17c8]!=bytes.fromhex('070070008011003c'):
        raise MDTError('E414: caja o comando siguiente inesperado')
    if not catalog or any(r['disco']!='2' or r['ruta']!='FIELD/E414.MDT' or r['sha256_mdt'].upper()!=_E414_EN_SHA for r in catalog):
        raise MDTError('E414: catalogo no corresponde a fuente exacta')
    target=[r for r in catalog if r['id']=='EN-D2-E414-P0000-B0000179A']
    if len(target)!=1 or int(target[0]['longitud'])!=38 or int(target[0]['longitud_declarada'])!=42 or sha(source[0x179c:0x17c2])!=target[0]['sha256_payload'].upper():
        raise MDTError('E414: metadatos de excepcion no coinciden')
    l=layout(source);lo=l.scn+l.entries[0][1];hi=l.scn+l.entries[1][1] if len(l.entries)>1 else l.scn+l.size
    if any(r['sha256_pieza'].upper()!=sha(source[lo:hi]) for r in catalog if int(r['ordinal_pieza'])==0): raise MDTError('E414: hash original de pieza no coincide')
    patched=bytearray(source);patched[0x179a:0x179c]=b'\x20\x26';patched=bytes(patched)
    patched_sha=sha(patched);piece_sha=sha(patched[lo:hi]);updated=[]
    for r in catalog:
        copy=dict(r);copy['sha256_mdt']=patched_sha
        if int(r['ordinal_pieza'])==0:copy['sha256_pieza']=piece_sha
        if r['id']=='EN-D2-E414-P0000-B0000179A':copy['longitud_declarada']='38'
        updated.append(copy)
    _audit_scn(patched,layout(patched),updated)
    return patched,updated

def rebuild(source, catalog, edits):
    source=bytes(source); lay=layout(source)
    if not edits: return source
    if lay is None: raise MDTError('MDT sin SCN')
    rows={r['id']:r for r in catalog}
    if len(rows)!=len(catalog) or not set(edits)<=rows.keys(): raise MDTError('ID ausente o duplicado')
    digest=sha(source); grouped=defaultdict(list)
    for ident,(old,new) in edits.items():
        r=rows[ident]; old=bytes(old); new=bytes(new)
        if ident=='EN-D2-E414-P0000-B0000179A' and digest!=_E414_FIXED_SHA: raise MDTError('caja excepcional E414 requiere reparacion opt-in exacta')
        if digest!=r['sha256_mdt'].upper() or sha(old)!=r['sha256_payload'].upper(): raise MDTError('fuente o payload no coincide')
        ordinal=int(r['ordinal_pieza']); off=int(r['offset_bloque'])
        if ordinal>=len(lay.entries) or f'{lay.entries[ordinal][0]:04X}'!=r['id_pieza'].upper(): raise MDTError('ordinal o ID de pieza no coincide')
        lo=lay.entries[ordinal][1]; hi=lay.entries[ordinal+1][1] if ordinal+1<len(lay.entries) else lay.size
        if off<lay.scn+lo or off+2+len(old)>lay.scn+hi or source[off+2:off+2+len(old)]!=old: raise MDTError('payload fuera de pieza o distinto')
        if len(new)>4095 or not new or not (new.endswith(b'\x07') or new.endswith(b'\x07\0')): raise MDTError('payload nuevo inválido')
        if (len(new)-len(old))%2: raise MDTError('delta impar')
        grouped[ordinal].append((off,old,new))
    # No inferir por ID: la tabla puede contener IDs repetidos y offsets alias.
    if any(lay.entries[i][1]==lay.entries[i+1][1] for i in grouped if i+1<len(lay.entries)):
        raise MDTError('ordinal vacío con alias no editable')
    global_refs,global_boundaries=_audit_scn(source,lay,catalog)
    patches=[]; all_deltas=[]; edits_abs=[]
    for ordinal, changes in grouped.items():
        lo=lay.entries[ordinal][1]; hi=lay.entries[ordinal+1][1] if ordinal+1<len(lay.entries) else lay.size
        base=lay.scn+lo; body=source[base:lay.scn+hi]
        if sha(body)!=rows[next(k for k in edits if int(rows[k]['ordinal_pieza'])==ordinal)]['sha256_pieza'].upper(): raise MDTError('hash de pieza distinto')
        blocks={int(r['offset_bloque'])-base:int(r['longitud']) for r in catalog if int(r['ordinal_pieza'])==ordinal}
        exceptions={int(r['offset_bloque'])-base for r in catalog if r['id']=='EN-D2-E414-P0000-B0000179A' and int(r['ordinal_pieza'])==ordinal}
        spans,refs,_=_scan(body,blocks,validate_refs=False,allow_d0_tail=(lay.entries[ordinal][0]>>8 in (0xc0,0xd0) and bool(blocks)),exception_positions=exceptions)
        local=[]
        for off,old,new in changes:
            p=off-base
            if p not in blocks or len(old)!=blocks[p]: raise MDTError('caja no catalogada')
            local.append((p,p+2+len(old),new,len(new)-len(old)))
        local.sort()
        if any(a[1]>b[0] for a,b in zip(local,local[1:])): raise MDTError('cajas solapadas')
        for p,end,n in spans:
            ds=sum(d for a,b,_,d in local if p<a and b<=end)
            if any(p<a<end<b for a,b,_,_ in local): raise MDTError('span cruza caja')
            if not 0<=n+ds<=4095:
                path=rows[next(iter(edits))].get('ruta','MDT')
                raise MDTError(f'span 3NNN desbordado: {path} pieza {ordinal}, MDT {base+p:#x}, '
                               f'tramo {base+p:#x}..{base+end:#x}, {n}+({ds})={n+ds} fuera de 0..4095')
            if ds: patches.append((base+p,base+p+2,(0x3000|n+ds).to_bytes(2,'big')))
        for a,b,new,d in local:
            edits_abs.append((lo+a,lo+b,d))
            word=int.from_bytes(body[a:a+2],'big'); patches.append((base+a,base+b,((word&0xf000)|len(new)).to_bytes(2,'big')+new)); all_deltas.append((lo,d))
    def relocated(pos):
        if any(a<pos<b for a,b,_ in edits_abs): raise MDTError(f'salto apunta dentro de caja editada en {pos:#x}')
        return pos+sum(d for a,b,d in edits_abs if b<=pos)
    new_boundaries={relocated(x) for x in global_boundaries if not any(a<x<b for a,b,_ in edits_abs)}
    for operand,origin,target,signed in global_refs:
        new_target=relocated(target); new_origin=relocated(origin)
        if new_target not in new_boundaries: raise MDTError('destino reubicado no es limite')
        distance=new_target-new_origin
        if not ((-32768<=distance<=32767) if signed else (0<=distance<=65535)):
            raise MDTError('salto 8/40 desbordado')
        old=int.from_bytes(source[lay.scn+operand:lay.scn+operand+2],'big',signed=signed)
        if distance!=old:
            patches.append((lay.scn+operand,lay.scn+operand+2,distance.to_bytes(2,'big',signed=signed)))
    vm_delta=sum(d for _,d in all_deltas)
    # Reserve at SCN end; sector multiples retain graphic DMA alignment.
    section_delta=max(0,(vm_delta+2047)//2048*2048)
    reserve=section_delta-vm_delta
    if lay.size+section_delta>65535: raise MDTError('SCN supera 16 bits')
    if u32(source,0x180)!=lay.footer//2048 or u32(source,0x1f4)!=lay.footer//2048 or (u32(source,0x184)!=0xffffffff and u32(source,0x184)*2048>len(source)-lay.footer): raise MDTError('sectores de footer inconsistentes')
    h=bytearray(source[:512])
    for p in range(0,0x100,8):
        if p in (0x20,0x58,0x60,0x68): continue
        v=u32(source,p)
        if v==0xffffffff: continue
        addr=v&0xffffff
        if not lay.scn+lay.size<=addr<=lay.graphics_end or addr+section_delta>0xffffff: raise MDTError(f'puntero gráfico no admitido {p:#x}')
        put32(h,p,(v&0xff000000)|(addr+section_delta))
    put32(h,0x64,lay.size+section_delta)
    for p in (0x1f8,0x1fc): put32(h,p,u32(source,p)+section_delta)
    sectors=section_delta//2048
    for p in (0x180,0x1f4,*range(0x190,0x1f1,8)):
        v=u32(source,p)
        if v!=0xffffffff: put32(h,p,v+sectors)
    table=bytearray(source[lay.ofs:lay.scn])
    for i,(_,off) in enumerate(lay.entries):
        moved=off+sum(d for start,d in all_deltas if start<off)
        if not 0<=moved<=65535: raise MDTError('OFS supera 16 bits')
        table[i*4+2:i*4+4]=moved.to_bytes(2,'big')
    script=bytearray(); cursor=lay.scn
    for a,b,new in sorted(patches):
        if a<cursor: raise MDTError('parches solapados')
        script+=source[cursor:a]+new; cursor=b
    script+=source[cursor:lay.scn+lay.size]+bytes(reserve)
    result=bytes(h)+source[512:lay.ofs]+bytes(table)+bytes(script)+source[lay.scn+lay.size:lay.footer]+source[lay.footer:]
    if len(result)!=len(source)+section_delta: raise MDTError('tamaño reconstruido inconsistente')
    new_layout=layout(result)
    # Reparse every edited piece using relocated catalog entries and new lengths.
    for ordinal, changes in grouped.items():
        lo=new_layout.entries[ordinal][1]
        hi=new_layout.entries[ordinal+1][1] if ordinal+1<len(new_layout.entries) else new_layout.size
        old_lo=lay.entries[ordinal][1]; base=lay.scn+old_lo
        local=sorted((off-base, len(new)-len(old)) for off,old,new in changes)
        relocated={}
        for r in catalog:
            if int(r['ordinal_pieza'])!=ordinal: continue
            pos=int(r['offset_bloque'])-base
            moved=pos+sum(d for start,d in local if start<pos)
            length=len(edits[r['id']][1]) if r['id'] in edits else int(r['longitud'])
            if moved in relocated: raise MDTError('cajas catalogadas duplicadas')
            relocated[moved]=length
        exceptions={int(r['offset_bloque'])-base+sum(d for start,d in local if start<int(r['offset_bloque'])-base) for r in catalog if r['id']=='EN-D2-E414-P0000-B0000179A' and int(r['ordinal_pieza'])==ordinal}
        actual_hi=hi-reserve if ordinal+1==len(new_layout.entries) else hi
        _scan(result[new_layout.scn+lo:new_layout.scn+actual_hi],relocated,validate_refs=False,allow_d0_tail=(lay.entries[ordinal][0]>>8 in (0xc0,0xd0) and bool(relocated)),exception_positions=exceptions)
    return result

