#!/usr/bin/env python3
"""Verifica una imagen multirrecurso frente a D1 o D2 inglés y su informe JSON."""
import argparse, hashlib, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from construir_imagen_recursos_es import geometry, iso_files
from construir_imagen_reubicada_es import (RAW, DATA,
    require, putboth, formatted, get_sector, extract_hash, cue_time, repair)

def verify(report_path):
    report=json.loads(Path(report_path).read_text(encoding='utf-8-sig'))
    SOURCE,CUE,g=geometry(report.get('disco',1))
    require(report.get('geometria',g)==g, 'geometría del informe incorrecta')
    INSERT,AUDIO,INDEX01,VOLUME=(g[k] for k in ('insert','audio','index01','volume'))
    image=Path(report['imagen']); n=report['sectores_insertados']; resources=report['recursos']
    require(isinstance(n,int) and n>=0, 'número de sectores inválido')
    with SOURCE.open('rb') as src, image.open('rb') as built:
        require(image.stat().st_size == SOURCE.stat().st_size+n*RAW, 'tamaño de imagen incorrecto')
        files=iso_files(src,VOLUME,AUDIO)
        newfiles=iso_files(built,VOLUME+n,AUDIO+n)
        require(set(files)==set(newfiles), 'inventario ISO distinto')
        require(set(report['archivos']) == set(files)-{'CDDA1'}, 'informe de archivos incompleto')
        require(set(resources) <= set(files)-{'CDDA1'}, 'recurso desconocido')
        patches={}; next_lba=INSERT
        for path,info in resources.items():
            lba,size,sector,offset=files[path]; nl,ns=info['lba_nuevo'],info['bytes_nuevo']
            require((info['lba_original'],info['bytes_original'])==(lba,size) and ns>0, 'datos originales incorrectos')
            if ns>size:
                require(nl==next_lba, 'reubicaciones solapadas o desordenadas'); next_lba+=(ns+DATA-1)//DATA
            else: require(nl==lba, 'archivo sin crecimiento reubicado')
            require(newfiles[path][:2]==(nl,ns), 'directorio no coincide con informe')
            require(extract_hash(src,lba,size)==info['sha256_original'] and extract_hash(built,nl,ns)==info['sha256_nuevo'], 'hash de recurso incorrecto')
            if nl==lba:
                for i in range((ns+DATA-1)//DATA):
                    old=get_sector(src,lba+i); actual=get_sector(built,lba+i)
                    part=actual[16:16+min(DATA,ns-i*DATA)]
                    changed=formatted(old,lba+i,part+old[16+len(part):2064])
                    if changed!=old: patches[lba+i]=changed
            else:
                template=get_sector(src,INSERT)
                for i in range((ns+DATA-1)//DATA):
                    actual=get_sector(built,nl+i); count=min(DATA,ns-i*DATA)
                    require(actual==formatted(template,nl+i,actual[16:16+count].ljust(DATA,b'\0')), 'sector reubicado inválido')
            if nl!=lba or ns!=size:
                b=bytearray(patches.get(sector,get_sector(src,sector))); putboth(b,16+offset+2,nl); putboth(b,16+offset+10,ns); patches[sector]=bytes(repair(b))
        require(next_lba==INSERT+n, 'tamaño de reubicaciones incorrecto')
        if n:
            _,_,sector,offset=files['CDDA1']; b=bytearray(patches.get(sector,get_sector(src,sector)))
            putboth(b,16+offset+2,INDEX01+n); patches[sector]=bytes(repair(b))
            b=bytearray(get_sector(src,16)); putboth(b,16+80,VOLUME+n); patches[16]=bytes(repair(b))
        require(newfiles['CDDA1'][:2]==(INDEX01+n,files['CDDA1'][1]), 'CDDA1 incorrecto')
        for path,(lba,size,_,_) in files.items():
            if path=='CDDA1': continue
            nl,ns=newfiles[path][:2]; h=report['archivos'][path]
            require(extract_hash(src,lba,size)==h['original'] and extract_hash(built,nl,ns)==h['nuevo'], 'hash incorrecto: '+path)
            if path not in resources: require((nl,ns)==(lba,size) and h['original']==h['nuevo'], 'archivo no solicitado modificado: '+path)
        for lba in range(INSERT):
            require(get_sector(built,lba)==patches.get(lba,get_sector(src,lba)), 'sector inesperado: '+str(lba))
        for i in range(AUDIO-INSERT):
            old=get_sector(src,INSERT+i)
            require(get_sector(built,INSERT+n+i)==formatted(old,INSERT+n+i,old[16:2064]), 'reserva incorrecta')
        src.seek(AUDIO*RAW); built.seek((AUDIO+n)*RAW); audio=hashlib.sha256()
        while chunk:=src.read(4*1024*1024):
            require(built.read(len(chunk))==chunk, 'audio incorrecto'); audio.update(chunk)
        require(not built.read(1), 'audio con bytes adicionales')
    cue=CUE.read_text(encoding='utf-8-sig').replace(SOURCE.name,image.name).replace('INDEX 00 '+cue_time(AUDIO),'INDEX 00 '+cue_time(AUDIO+n)).replace('INDEX 01 '+cue_time(INDEX01),'INDEX 01 '+cue_time(INDEX01+n))
    require(Path(report['cue']).read_text(encoding='utf-8-sig')==cue, 'CUE incorrecto')
    print('Verificación completa; SHA-256 audio:',audio.hexdigest().upper())

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('informe',type=Path); verify(p.parse_args().informe)

