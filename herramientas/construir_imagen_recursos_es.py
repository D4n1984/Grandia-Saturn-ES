#!/usr/bin/env python3
"""Construye D1 o D2 con recursos ISO de longitud variable; no valida semántica del juego."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from construir_imagen_reubicada_es import (ROOT, RAW, DATA, ImageError, require, putboth, formatted, get_sector, iso_data, u32both, extract_hash, cue_time, msf, repair)

WORK = ROOT / 'trabajo'
OUT = WORK / 'prueba-es' / 'recursos'

def iso_files(f, volume, directory_limit):
    pvd=iso_data(f,16)
    require(pvd[:7]==b'\x01CD001\x01' and u32both(pvd,80)==volume, 'PVD inesperado')
    root=pvd[156:190]; files={}; seen=set()
    def visit(prefix,lba,size):
        require((lba,size) not in seen, 'directorio ISO repetido')
        seen.add((lba,size)); require(lba+(size+DATA-1)//DATA < directory_limit, 'directorio fuera de datos')
        raw=b''.join(iso_data(f,lba+i) for i in range((size+DATA-1)//DATA))[:size]; pos=0
        while pos<len(raw):
            n=raw[pos]
            if not n: pos=(pos//DATA+1)*DATA; continue
            require(n>=34 and pos+n<=len(raw) and pos//DATA==(pos+n-1)//DATA, 'registro ISO inválido')
            r=raw[pos:pos+n]; namelen=r[32]
            require(33+namelen<=n and not(r[25]&0x80), 'nombre o archivo multiextensión no admitido')
            ident=r[33:33+namelen]
            if ident not in (b'\0',b'\1'):
                path=prefix+ident.decode('ascii').split(';')[0]; extent,length=u32both(r,2),u32both(r,10)
                if r[25]&2: visit(path+'/',extent,length)
                else:
                    require(path not in files, 'nombre ISO duplicado')
                    files[path]=(extent,length,lba+pos//DATA,pos%DATA)
            pos+=n
    visit('',u32both(root,2),u32both(root,10)); return files

def geometry(disc):
    require(disc in (1,2), 'disco no admitido')
    source=WORK/f'ingles/salida/Grandia_EN_D{disc}.bin'; cue_path=source.with_suffix('.cue')
    cue=cue_path.read_text(encoding='utf-8-sig')
    pattern=r'FILE "'+re.escape(source.name)+r'" BINARY\s+TRACK 01 MODE1/2352\s+INDEX 01 00:00:00\s+TRACK 02 AUDIO\s+INDEX 00 (\d\d):(\d\d):(\d\d)\s+INDEX 01 (\d\d):(\d\d):(\d\d)\s*'
    match=re.fullmatch(pattern,cue); require(match is not None, 'CUE inesperado')
    nums=list(map(int,match.groups()))
    require(all(nums[i]<60 and nums[i+1]<75 for i in (1,4)), 'tiempo CUE inválido')
    audio=nums[0]*4500+nums[1]*75+nums[2]; index01=nums[3]*4500+nums[4]*75+nums[5]
    require(audio<index01 and source.stat().st_size%RAW==0 and source.stat().st_size>=index01*RAW, 'tamaño o índices inválidos')
    with source.open('rb') as src:
        pvd=iso_data(src,16); require(pvd[:7]==b'\x01CD001\x01', 'PVD inesperado')
        volume=u32both(pvd,80); files=iso_files(src,volume,audio)
        require('CDDA1' in files and files['CDDA1'][:2]==(index01,(volume-index01)*DATA), 'reserva CDDA1 inesperada')
        extents=sorted((v[0],v[0]+(v[1]+DATA-1)//DATA,k) for k,v in files.items() if k!='CDDA1' and v[1])
        require(extents and all(a[1]==b[0] for a,b in zip(extents,extents[1:])), 'archivos solapados o no contiguos')
        insert=extents[-1][1]; require(insert<audio, 'reserva ausente')
    return source,cue_path,dict(insert=insert,audio=audio,index01=index01,volume=volume)

def build(manifests, name, disc=1):
    SOURCE,CUE,g=geometry(disc)
    INSERT,AUDIO,INDEX01,VOLUME=(g[k] for k in ('insert','audio','index01','volume'))
    require(name.replace('_', '').isalnum(), 'nombre inválido')
    OUT.mkdir(parents=True, exist_ok=True)
    dest, cue_dest, report_dest = (OUT / (name + s) for s in ('.bin', '.cue', '-manifiesto.json'))
    require(not any(p.exists() for p in (dest, cue_dest, report_dest)), 'salida ya existente')
    entries = []
    for manifest in manifests:
        data = json.loads(Path(manifest).read_text(encoding='utf-8-sig'))
        require(isinstance(data, list), 'el manifiesto debe ser una lista JSON')
        entries.extend(data)
    require(all(isinstance(x, dict) and all(k in x for k in ('ruta','sector','bytes','sha256_original','sha256_nuevo','archivo')) for x in entries), 'entrada de manifiesto incompleta')
    require(len({x['ruta'] for x in entries}) == len(entries), 'rutas repetidas')
    cue = CUE.read_text(encoding='utf-8-sig')
    require(cue.count(SOURCE.name) == 1 and 'TRACK 01 MODE1/2352' in cue and 'TRACK 02 AUDIO' in cue and
            'INDEX 00 '+cue_time(AUDIO) in cue and 'INDEX 01 '+cue_time(INDEX01) in cue, 'CUE inesperado')
    with SOURCE.open('rb') as src:
        require(SOURCE.stat().st_size % RAW == 0 and SOURCE.stat().st_size >= INDEX01*RAW, 'tamaño de imagen inválido')
        files = iso_files(src,VOLUME,AUDIO)
        require('CDDA1' in files and files['CDDA1'][:2] == (INDEX01, (VOLUME-INDEX01)*DATA), 'reserva CDDA1 inesperada')
        extents = sorted((v[0], v[0]+(v[1]+DATA-1)//DATA, k) for k,v in files.items() if k != 'CDDA1' and v[1])
        require(extents and extents[-1][1] == INSERT and all(a[1] == b[0] for a,b in zip(extents,extents[1:])), 'archivos solapados o no contiguos')
        for lba in range(INSERT,AUDIO):
            s=get_sector(src,lba)
            require(s[12:15] == msf(lba) and s[16:2064] == bytes(DATA) and repair(s) == s, 'reserva MODE1 inválida')
        payloads = {}
        for item in entries:
            path=item['ruta']; require(path in files and path != 'CDDA1', 'archivo ISO no encontrado')
            lba,size,_,_=files[path]
            require(lba == int(item['sector']) and size == int(item['bytes']), 'ubicación o tamaño original incorrecto')
            p=Path(item['archivo']).resolve()
            try: p.relative_to(WORK.resolve())
            except ValueError: raise ImageError('recurso fuera de trabajo/')
            data=p.read_bytes(); require(data, 'recurso vacío no admitido')
            require(hashlib.sha256(data).hexdigest().upper() == item['sha256_nuevo'].upper(), 'hash nuevo incorrecto')
            require(extract_hash(src,lba,size) == item['sha256_original'].upper(), 'hash original incorrecto')
            payloads[path]=data
        patches={}; layouts={}; n=0
        for path,data in payloads.items():
            lba,size,sector,offset=files[path]
            if len(data)>size:
                new_lba=INSERT+n; n+=(len(data)+DATA-1)//DATA
            else:
                new_lba=lba
                for i in range((len(data)+DATA-1)//DATA):
                    old=get_sector(src,lba+i); require(repair(old)==old, 'EDC/ECC original incorrecto')
                    part=data[i*DATA:(i+1)*DATA]
                    changed=formatted(old,lba+i,part+old[16+len(part):2064])
                    if changed != old: patches[lba+i]=changed
            layouts[path]={'lba_original':lba,'bytes_original':size,'lba_nuevo':new_lba,'bytes_nuevo':len(data),
                           'sha256_original':extract_hash(src,lba,size),'sha256_nuevo':hashlib.sha256(data).hexdigest().upper()}
            if new_lba != lba or len(data) != size:
                base=bytearray(patches.get(sector,get_sector(src,sector)))
                require(repair(base)==base, 'EDC/ECC directorio incorrecto')
                putboth(base,16+offset+2,new_lba); putboth(base,16+offset+10,len(data)); patches[sector]=bytes(repair(base))
        if n:
            _,size,sector,offset=files['CDDA1']; base=bytearray(patches.get(sector,get_sector(src,sector)))
            require(repair(base)==base, 'EDC/ECC directorio incorrecto')
            putboth(base,16+offset+2,INDEX01+n); patches[sector]=bytes(repair(base))
            pvd=bytearray(get_sector(src,16)); require(repair(pvd)==pvd, 'EDC/ECC PVD incorrecto')
            putboth(pvd,16+80,VOLUME+n); patches[16]=bytes(repair(pvd))
        with dest.open('xb') as out:
            for lba in range(INSERT): out.write(patches.get(lba,get_sector(src,lba)))
            template=get_sector(src,INSERT)
            for path,data in payloads.items():
                if layouts[path]['lba_nuevo'] == layouts[path]['lba_original']: continue
                for i in range((len(data)+DATA-1)//DATA):
                    part=data[i*DATA:(i+1)*DATA]; out.write(formatted(template,layouts[path]['lba_nuevo']+i,part.ljust(DATA,b'\0')))
            for i in range(AUDIO-INSERT):
                old=get_sector(src,INSERT+i); out.write(formatted(old,INSERT+n+i,old[16:2064]))
            src.seek(AUDIO*RAW)
            while chunk:=src.read(4*1024*1024): out.write(chunk)
        hashes={}
        for path,(lba,size,_,_) in files.items():
            if path != 'CDDA1':
                old=extract_hash(src,lba,size); hashes[path]={'original':old,'nuevo':layouts[path]['sha256_nuevo'] if path in layouts else old}
    updated=cue.replace(SOURCE.name,dest.name).replace('INDEX 00 '+cue_time(AUDIO),'INDEX 00 '+cue_time(AUDIO+n)).replace('INDEX 01 '+cue_time(INDEX01),'INDEX 01 '+cue_time(INDEX01+n))
    cue_dest.write_text(updated,encoding='utf-8')
    report={'disco':disc,'geometria':g,'imagen':str(dest),'cue':str(cue_dest),'sectores_insertados':n,'recursos':layouts,'archivos':hashes,
            'advertencia':'Referencias VM y ejecución no verificadas'}
    report_dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    from verificar_imagen_recursos_es import verify
    verify(report_dest)
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('manifiestos',nargs='+',type=Path); p.add_argument('--nombre',required=True); p.add_argument('--disco',type=int,choices=(1,2),default=1)
    a=p.parse_args(); r=build(a.manifiestos,a.nombre,a.disco); print(f"Construida y verificada: {r['imagen']} ({r['sectores_insertados']} sectores insertados)")
if __name__=='__main__': main()

