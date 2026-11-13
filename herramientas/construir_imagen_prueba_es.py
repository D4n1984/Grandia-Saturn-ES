#!/usr/bin/env python3
"""Copia la imagen inglesa y aplica recursos del mismo tamaño con EDC/ECC MODE1."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
WORK=ROOT/'trabajo/prueba-es'
SOURCE=ROOT/'trabajo/ingles/salida/Grandia_EN_D1.bin'


def sha(raw):return hashlib.sha256(raw).hexdigest().upper()


EDC=[];FORWARD=[];BACKWARD=[0]*256
for i in range(256):
    edc=i
    for _ in range(8):edc=(edc>>1)^(0xD8018001 if edc&1 else 0)
    EDC.append(edc)
    j=i<<1
    if j&256:j^=0x11D
    FORWARD.append(j);BACKWARD[i^j]=i


def ecc(raw,major_count,minor_count,major_mult,minor_inc):
    size=major_count*minor_count;out=bytearray(major_count*2)
    for major in range(major_count):
        index=(major>>1)*major_mult+(major&1);a=b=0
        for _ in range(minor_count):
            value=raw[index];index=(index+minor_inc)%size
            a^=value;b^=value;a=FORWARD[a]
        a=BACKWARD[FORWARD[a]^b];out[major]=a;out[major+major_count]=a^b
    return out


def repair(sector):
    assert len(sector)==2352 and sector[:12]==bytes.fromhex('00FFFFFFFFFFFFFFFFFFFF00') and sector[15]==1
    result=bytearray(sector);edc=0
    for byte in result[:2064]:edc=(edc>>8)^EDC[(edc^byte)&255]
    result[2064:2068]=edc.to_bytes(4,'little');result[2068:2076]=b'\0'*8
    result[2076:2248]=ecc(result[12:2076],86,24,2,86)
    result[2248:2352]=ecc(result[12:2248],52,43,86,88)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifiestos',nargs='+',type=Path)
    parser.add_argument('--nombre',default='Grandia_ES_Prueba_D1')
    args=parser.parse_args()
    if not args.nombre.replace('_','').isalnum():parser.error('Nombre de salida inválido')
    entries=[item for path in args.manifiestos for item in json.loads(path.read_text(encoding='utf-8-sig'))]
    assert len({r['ruta'] for r in entries})==len(entries)
    output=WORK/'imagen';output.mkdir(parents=True,exist_ok=True)
    dest=output/(args.nombre+'.bin')
    if dest.exists():raise ValueError('La imagen de prueba ya existe; usar otro nombre para preservarla')
    patches={};stats=[]
    with SOURCE.open('rb') as track:
        for item in entries:
            path=Path(item['archivo']);path.resolve().relative_to(WORK.resolve())
            payload=path.read_bytes();assert len(payload)==int(item['bytes']) and sha(payload)==item['sha256_nuevo']
            original=bytearray();sectors=[]
            for pos in range(0,len(payload),2048):
                lba=int(item['sector'])+pos//2048;track.seek(lba*2352);sector=track.read(2352)
                # Independientemente comprobar la fórmula contra sectores originales.
                if repair(sector)!=sector:raise ValueError(f'EDC/ECC original no válido: {lba}')
                count=min(2048,len(payload)-pos);original.extend(sector[16:16+count])
                block=bytearray(sector);block[16:16+count]=payload[pos:pos+count]
                if block!=sector:
                    assert lba not in patches
                    patches[lba]=(sector,bytes(repair(block)));sectors.append(lba)
            assert sha(original)==item['sha256_original']
            stats.append(dict(ruta=item['ruta'],sha256_original=sha(original),sha256_nuevo=sha(payload),sectores_modificados=sectors))
    shutil.copyfile(SOURCE,dest)
    with dest.open('r+b') as image:
        for lba,(original,changed) in sorted(patches.items()):
            image.seek(lba*2352);assert image.read(2352)==original
            image.seek(lba*2352);image.write(changed)
    with SOURCE.open('rb') as original,dest.open('rb') as changed:
        lba=0;source_hash=hashlib.sha256();target_hash=hashlib.sha256()
        while block:=original.read(2352*2048):
            target=changed.read(len(block));assert len(target)==len(block)
            source_hash.update(block);target_hash.update(target)
            for pos in range(0,len(block),2352):
                a=block[pos:pos+2352];b=target[pos:pos+2352]
                assert a==b or lba in patches and (a,b)==patches[lba]
                lba+=1
        assert not changed.read(1)
    cue=(ROOT/'trabajo/ingles/salida/Grandia_EN_D1.cue').read_text(encoding='utf-8-sig')
    assert 'Grandia_EN_D1.bin' in cue
    (output/(args.nombre+'.cue')).write_text(cue.replace('Grandia_EN_D1.bin',dest.name),encoding='utf-8')
    report=dict(imagen_original=str(SOURCE),imagen_prueba=str(dest),sha256_original=source_hash.hexdigest().upper(),
                sha256_prueba=target_hash.hexdigest().upper(),archivos=stats,sectores_modificados=len(patches),
                verificacion='Todo sector no declarado es idéntico; EDC/ECC verificados; tamaños y posiciones conservados.')
    (output/(args.nombre+'-manifiesto.json')).write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f'Imagen construida y verificada: {dest}; {len(patches)} sectores modificados.')


if __name__=='__main__':main()
