#!/usr/bin/env python3
"""Construye una copia experimental D1 con BA38 reubicado antes de la pista CDDA.

La reconstrucción no verifica la semántica del MDT ni su ejecución en consola.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from construir_imagen_prueba_es import repair

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / 'trabajo/prueba-es'
SOURCE = ROOT / 'trabajo/ingles/salida/Grandia_EN_D1.bin'
CUE = ROOT / 'trabajo/ingles/salida/Grandia_EN_D1.cue'
OUT = WORK / 'reubicacion'
RAW, DATA = 2352, 2048
INSERT, AUDIO, INDEX01, VOLUME = 267710, 267860, 268010, 268825
SYNC = bytes.fromhex('00FFFFFFFFFFFFFFFFFFFF00')

class ImageError(ValueError): pass

def require(condition, message):
    if not condition: raise ImageError(message)

def u32both(b, pos):
    le = int.from_bytes(b[pos:pos+4], 'little'); be = int.from_bytes(b[pos+4:pos+8], 'big')
    require(le == be, 'campos ISO de ambos órdenes no coinciden')
    return le

def putboth(b, pos, value):
    b[pos:pos+4] = value.to_bytes(4, 'little'); b[pos+4:pos+8] = value.to_bytes(4, 'big')

def msf(lba):
    n = lba + 150; m, n = divmod(n, 4500); s, f = divmod(n, 75)
    require(m < 100, 'dirección MSF fuera de rango')
    return bytes(((m//10)*16+m%10, (s//10)*16+s%10, (f//10)*16+f%10))

def formatted(template, lba, data):
    require(len(template) == RAW and template[:12] == SYNC and template[15] == 1, 'sector MODE1 inválido')
    require(len(data) == DATA, 'datos de sector inválidos')
    b = bytearray(template); b[12:15] = msf(lba); b[16:2064] = data
    return bytes(repair(b))

def get_sector(f, lba):
    f.seek(lba*RAW); b = f.read(RAW)
    require(len(b) == RAW, f'sector ausente {lba}')
    return b

def iso_data(f, lba):
    b = get_sector(f, lba)
    require(b[:12] == SYNC and b[15] == 1 and b[12:15] == msf(lba), f'MODE1 o dirección inválida {lba}')
    return b[16:2064]

def iso_files(f):
    pvd = iso_data(f,16)
    require(pvd[:7] == b'\x01CD001\x01' and u32both(pvd,80) == VOLUME, 'PVD inesperado')
    root = pvd[156:190]; root_lba = u32both(root,2); root_size = u32both(root,10)
    files, seen = {}, set()
    def visit(prefix, lba, size):
        require((lba,size) not in seen, 'directorio ISO repetido')
        seen.add((lba,size)); require(lba + (size+2047)//2048 < INSERT, 'directorio fuera de zona de datos')
        raw = b''.join(iso_data(f,lba+i) for i in range((size+2047)//2048))[:size]
        pos = 0
        while pos < len(raw):
            n = raw[pos]
            if not n: pos = (pos//2048+1)*2048; continue
            require(n >= 34 and pos+n <= len(raw) and pos//2048 == (pos+n-1)//2048, 'registro ISO inválido')
            r = raw[pos:pos+n]; namelen = r[32]
            require(33+namelen <= n and not (r[25] & 0x80), 'nombre o archivo multiextensión no admitido')
            ident = r[33:33+namelen]
            if ident not in (b'\x00',b'\x01'):
                name = ident.decode('ascii').split(';')[0]; path = prefix + name
                extent, length = u32both(r,2), u32both(r,10)
                if r[25] & 2: visit(path+'/',extent,length)
                else:
                    require(path not in files, 'nombre ISO duplicado')
                    files[path] = (extent,length,lba+pos//2048,pos%2048)
            pos += n
    visit('',root_lba,root_size)
    return files

def extract_hash(f, lba, size):
    h=hashlib.sha256()
    for i in range((size+2047)//2048): h.update(iso_data(f,lba+i)[:min(2048,size-i*2048)])
    return h.hexdigest().upper()

def cue_time(lba):
    m, rem=divmod(lba,4500); s, fr=divmod(rem,75)
    return f'{m:02}:{s:02}:{fr:02}'

def build(manifest_paths, name):
    require(name.replace('_','').isalnum(), 'nombre inválido')
    OUT.mkdir(parents=True,exist_ok=True)
    dest=OUT/(name+'.bin'); cue_dest=OUT/(name+'.cue'); report_dest=OUT/(name+'-manifiesto.json')
    require(not any(p.exists() for p in (dest,cue_dest,report_dest)), 'salida ya existente')
    entries=[x for path in manifest_paths for x in json.loads(Path(path).read_text(encoding='utf-8-sig'))]
    require(len({x['ruta'] for x in entries}) == len(entries), 'rutas de manifiesto repetidas')
    cue=CUE.read_text(encoding='utf-8-sig')
    require(cue.count('Grandia_EN_D1.bin')==1 and 'TRACK 01 MODE1/2352' in cue and 'TRACK 02 AUDIO' in cue and
            'INDEX 00 '+cue_time(AUDIO) in cue and 'INDEX 01 '+cue_time(INDEX01) in cue, 'CUE inesperado')
    with SOURCE.open('rb') as src:
        require(SOURCE.stat().st_size % RAW == 0 and SOURCE.stat().st_size >= INDEX01*RAW, 'tamaño de imagen inválido')
        files=iso_files(src)
        require('FIELD/BA38.MDT' in files and 'CDDA1' in files, 'faltan BA38 o CDDA1')
        require(files['CDDA1'][0] == INDEX01 and files['CDDA1'][1] == (VOLUME-INDEX01)*2048, 'reserva CDDA1 inesperada')
        extents=sorted((v[0],v[0]+(v[1]+2047)//2048,k) for k,v in files.items() if k!='CDDA1' and v[1])
        require(extents and extents[-1][1] == INSERT, 'último archivo no termina en la reserva')
        require(all(a[1]==b[0] for a,b in zip(extents,extents[1:])), 'archivos no contiguos o solapados')
        for lba in range(INSERT,AUDIO):
            s=get_sector(src,lba)
            require(s[12:15]==msf(lba) and s[16:2064]==bytes(2048) and repair(s)==s, 'reserva MODE1 no es cero o EDC/ECC inválido')
        patches={}; payloads={}; original_hashes={}
        for item in entries:
            path=item['ruta']; require(path in files and path!='CDDA1', 'archivo no encontrado')
            lba,size,_,_=files[path]
            require(lba==int(item['sector']) and size==int(item['bytes']), 'manifiesto no coincide con ISO')
            p=Path(item['archivo']).resolve(); p.relative_to(WORK.resolve()); data=p.read_bytes()
            require(hashlib.sha256(data).hexdigest().upper()==item['sha256_nuevo'].upper(), 'hash de recurso nuevo incorrecto')
            h=extract_hash(src,lba,size); require(h==item['sha256_original'].upper(), 'hash de recurso original incorrecto')
            payloads[path]=data; original_hashes[path]=h
        require('FIELD/BA38.MDT' in payloads, 'BA38 debe figurar en manifiesto')
        oldsize=files['FIELD/BA38.MDT'][1]; new=payloads['FIELD/BA38.MDT']
        require(len(new)>oldsize and len(new)%2048==0, 'BA38 debe crecer a un tamaño de sector entero')
        require(all(k=='FIELD/BA38.MDT' or len(v)==files[k][1] for k,v in payloads.items()), 'solo BA38 puede cambiar de tamaño')
        n=len(new)//2048
        # Insertamos el archivo entero, por lo que la cola crece N sectores, no solo el delta del MDT.
        for path,data in payloads.items():
            if path=='FIELD/BA38.MDT': continue
            lba,size,_,_=files[path]
            for i in range((size+2047)//2048):
                old=get_sector(src,lba+i); require(repair(old)==old, 'EDC/ECC original incorrecto')
                part=data[i*2048:(i+1)*2048]; block=part+old[16+len(part):2064]
                changed=formatted(old,lba+i,block)
                if changed!=old: patches[lba+i]=changed
        for path,new_lba,new_len in [('FIELD/BA38.MDT',INSERT,len(new)),('CDDA1',INDEX01+n,files['CDDA1'][1])]:
            _,_,sector,offset=files[path]; base=bytearray(patches.get(sector,get_sector(src,sector)))
            require(repair(base)==base, 'EDC/ECC directorio incorrecto')
            putboth(base,16+offset+2,new_lba);putboth(base,16+offset+10,new_len)
            patches[sector]=bytes(repair(base))
        pvd=bytearray(get_sector(src,16)); require(repair(pvd)==pvd, 'EDC/ECC PVD incorrecto')
        putboth(pvd,16+80,VOLUME+n);patches[16]=bytes(repair(pvd))
        # Stream output and verify every unchanged sector during a second read.
        with dest.open('xb') as out:
            for lba in range(INSERT):
                original=get_sector(src,lba);out.write(patches.get(lba,original))
            template=get_sector(src,INSERT)
            for i in range(n): out.write(formatted(template,INSERT+i,new[i*2048:(i+1)*2048]))
            for i in range(AUDIO-INSERT):
                old=get_sector(src,INSERT+i);out.write(formatted(old,INSERT+n+i,old[16:2064]))
            src.seek(AUDIO*RAW)
            while chunk:=src.read(4*1024*1024):out.write(chunk)
        with dest.open('rb') as built:
            for lba in range(INSERT):
                require(get_sector(built,lba)==patches.get(lba,get_sector(src,lba)), f'sector cambiado inesperado {lba}')
            for i in range(n):
                a=get_sector(built,INSERT+i);require(a==formatted(template,INSERT+i,new[i*2048:(i+1)*2048]), 'MDT reubicado incorrecto')
            for i in range(AUDIO-INSERT):
                a=get_sector(src,INSERT+i);b=get_sector(built,INSERT+n+i)
                require(b==formatted(a,INSERT+n+i,a[16:2064]), 'cola MODE1 incorrecta')
            src.seek(AUDIO*RAW);built.seek((AUDIO+n)*RAW)
            audio_hash=hashlib.sha256()
            while chunk:=src.read(4*1024*1024):
                require(built.read(len(chunk))==chunk, 'audio no coincide');audio_hash.update(chunk)
            require(not built.read(1), 'bytes adicionales tras audio')
            hashes={}
            for path,(lba,size,_,_) in files.items():
                if path=='CDDA1': continue
                original=original_hashes.get(path) or extract_hash(src,lba,size)
                new_lba=INSERT if path=='FIELD/BA38.MDT' else lba
                new_size=len(payloads[path]) if path in payloads else size
                actual=extract_hash(built,new_lba,new_size)
                expected=hashlib.sha256(payloads[path]).hexdigest().upper() if path in payloads else original
                require(actual==expected, f'hash de archivo incorrecto: {path}')
                hashes[path]={'original':original,'nuevo':actual}
    updated=cue.replace('Grandia_EN_D1.bin',dest.name).replace('INDEX 00 '+cue_time(AUDIO),'INDEX 00 '+cue_time(AUDIO+n)).replace('INDEX 01 '+cue_time(INDEX01),'INDEX 01 '+cue_time(INDEX01+n))
    cue_dest.write_text(updated,encoding='utf-8')
    report={'imagen':str(dest),'sectores_insertados':n,'BA38_lba':INSERT,'CDDA1_lba':INDEX01+n,'audio_sha256':audio_hash.hexdigest().upper(),'archivos':hashes,'advertencia':'Referencias VM y ejecución no verificadas'}
    report_dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifiestos',nargs='+',type=Path);p.add_argument('--nombre',required=True)
    a=p.parse_args();r=build(a.manifiestos,a.nombre);print(f"Construida y verificada: {r['imagen']} ({r['sectores_insertados']} sectores insertados)")
if __name__=='__main__':main()
