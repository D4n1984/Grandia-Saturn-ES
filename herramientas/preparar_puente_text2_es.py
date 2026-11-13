#!/usr/bin/env python3
"""Crea candidatos TEXT2 a partir de donantes ES y correspondencias JP verificadas.

No modifica catalogos ni fuentes. El resultado es estructural y no esta probado en juego.
"""
import argparse,csv,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'herramientas'))
from comparar_text2_discos import original
from inventariar_videos_bloques import read_movie
from reinsertar_tablas_menus_es import bbg_parent,entry_end
from codificacion_es import encode_field

def sha(b):return hashlib.sha256(b).hexdigest().upper()
def rows(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def js(p):
 with p.open(encoding='utf8') as f:return [json.loads(x) for x in f]
def bounds(data,n,base=0,end=None):
 end=len(data) if end is None else end
 a=[int.from_bytes(data[base+4*i:base+4*i+4],'big') for i in range(n)]
 if a[0]!=4*n or any(x%4 for x in a) or any(x>=y for x,y in zip(a,a[1:])) or base+a[-1]>=end:raise ValueError('Cabecera invalida')
 return [base+x for x in a]+[end]
def chunks(data,b):return [data[a:z] for a,z in zip(b,b[1:])]
def pack(parts):
 pos=44; offsets=[]; out=[]
 for i,p in enumerate(parts):
  offsets.append(pos);p=bytes(p)
  if i<10:p+=bytes(-len(p)%4)
  out.append(p);pos+=len(p)
 return b''.join(x.to_bytes(4,'big') for x in offsets)+b''.join(out)
def fields(section,n,start=0):
 p=start;out=[]
 for _ in range(n):
  end=entry_end(section,p,len(section));out.append((p,section[p:end]));p=end+1
 return out,p

def loadjp(d,path):
 rec=next(r for r in rows(ROOT/f'inventario/archivos-disco{d}.csv') if r['ruta']==path)
 images=list((ROOT/f'trabajo/originales/disco{d}').glob('*Track 1*.bin'))
 if len(images)!=1:raise ValueError('Imagen japonesa ambigua')
 with images[0].open('rb') as f: result=read_movie(f,rec)
 cmp=next(r for r in rows(ROOT/'inventario/comparacion-archivos-jp-en.csv') if r['disco']==str(d) and r['ruta']==path)
 if sha(result)!=cmp['sha256_japones'].upper():raise ValueError('Hash fuente JP distinto')
 return result

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('recursos',type=Path);parser.add_argument('salida',type=Path);a=parser.parse_args()
 root=a.recursos.resolve();out=a.salida.resolve();out.relative_to((ROOT/'trabajo').resolve())
 if out.exists():raise ValueError('Salida existente')
 result=json.loads((root/'resultado.json').read_text(encoding='utf8'));master_path=ROOT/'trabajo/traduccion-en-es/textos-ingles-espanol.csv'
 if sha(master_path.read_bytes())!=result['sha256_hoja']:raise ValueError('Hoja distinta de recursos preparados')
 entries={(x['disco'],x['ruta']):x for x in result['recursos']};master={x['referencia']:x for x in rows(master_path)}
 backups=js(ROOT/'trabajo/traduccion-en-es/tablas/tablas-respaldo.jsonl');helpback=js(ROOT/'trabajo/traduccion-en-es/tablas/bbg-ayuda-respaldo.jsonl')
 rev=[r for r in rows(ROOT/'trabajo/revision-text2-secciones-adicionales.csv') if r['disco']=='1' and r['seccion'] in ('3','10')]
 outputs=[];mapping=[]
 for d,name,jbase,ebase,jhash in [(1,'B001',339976,339856,'EC30E9B157EC29E7E0BD3B35E270F847B5350A5324CBDD3BB0A4104E78781AF9'),(2,'B039',324584,324464,'163C06EBD705E4614B641A66BEE36D52A8FE7BA8F43EA8CC0B516CA680318C51')]:
  path=f'BATLE/{name}.BBG';jbb=(ROOT/f'trabajo/bbg-hud/jp-d{d}-{name}.bin').read_bytes()
  if sha(jbb)!=jhash:raise ValueError('BBG japones distinto')
  jt=original(d);jw=loadjp(d,'FIELD/WDATA.DAT'); tparts=chunks(jt,bounds(jt,11));jpbb=chunks(jbb,bounds(jbb,9,jbase));jwp=chunks(jw,bounds(jw,13))
  for ti,bi in ((0,0),(1,1),(3,2),(4,3),(6,4),(7,5),(8,6),(9,7)):
   if tparts[ti]!=jpbb[bi]:raise ValueError(f'Correspondencia JP fallida {d}/{ti}')
  if not jpbb[8].startswith(tparts[10]) or tparts[9]!=jwp[4]:raise ValueError('Ayuda o WDATA JP distinta')
  def prepared(path):
   item=entries[d,path];data=(root/f'D{d}'/path).read_bytes()
   if sha(data)!=item['sha256_nuevo'] or len(data)!=item['bytes_nuevos']:raise ValueError('Donante ES alterado: '+path)
   with (ROOT/f'trabajo/ingles/salida/Grandia_EN_D{d}.bin').open('rb') as source:
    idx=next(r for r in rows(ROOT/f'trabajo/ingles/analisis/archivos-disco{d}.csv') if r['ruta']==path)
    before=read_movie(source,idx)
   if sha(before)!=item['sha256_original'] or len(before)!=item['bytes']:raise ValueError('Fuente EN original distinta: '+path)
   return data
  bb=prepared(path);wd=prepared('FIELD/WDATA.DAT');parent,siblings=bbg_parent(bb,ebase);bend=parent+siblings[2]; bp=chunks(bb,bounds(bb,9,ebase,bend));wp=chunks(wd,bounds(wd,13))
  # Fuente inglesa integra verificada contra comparacion y secciones japonesas comprobadas.
  with (ROOT/f'trabajo/ingles/salida/Grandia_EN_D{d}.bin').open('rb') as f:
   idx=next(r for r in rows(ROOT/f'trabajo/ingles/analisis/archivos-disco{d}.csv') if r['ruta']=='BATLE/TEXT2.BIN'); en=read_movie(f,idx)
  cmp=next(r for r in rows(ROOT/'inventario/comparacion-archivos-jp-en.csv') if r['disco']==str(d) and r['ruta']=='BATLE/TEXT2.BIN')
  if sha(en)!=cmp['sha256_ingles'].upper():raise ValueError('TEXT2 ingles alterado')
  ep=chunks(en,bounds(en,11))
  for i in (2,5,10):
   if ep[i]!=tparts[i]:raise ValueError('Seccion original JP/EN distinta')
  parts=list(ep)
  for ti,bi in ((0,0),(1,1),(3,2),(4,3),(6,4),(7,5),(8,6),(9,7)):parts[ti]=bp[bi]
  if d==2:parts[9]=wp[4]
  old_help,old_end=fields(tparts[10],9,19);new_help,new_end=fields(bp[8],9,19)
  if tparts[10][:19]!=bp[8][:19]:raise ValueError('Prefijo ayuda distinto')
  parts[10]=tparts[10][:19]+bp[8][19:new_end]+tparts[10][old_end:]
  rebuilt=pack(parts); outparts=chunks(rebuilt,bounds(rebuilt,11))
  if outparts[2]!=ep[2] or outparts[5]!=ep[5] or outparts[10]!=parts[10]:raise ValueError('Secciones preservadas alteradas')
  if pack(chunks(en,bounds(en,11)))!=en:raise ValueError('Prueba neutra TEXT2 fallo')
  for i,part in enumerate(parts):
   if not outparts[i].startswith(part) or (i==10 and outparts[i]!=part):raise ValueError('Reconstruccion inconsistente')
  if d==1:
   tnew=fields(outparts[3],71)[0];helpnew=fields(outparts[10],9,19)[0]
   for section,records,fieldlist,src,donsec in [(3,backups,tnew,'B001',2),(10,helpback,helpnew,'B001',8)]:
    srcrows={int(x['indice']):x for x in records if x['disco']==1 and x['ruta']==f'BATLE/{src}.BBG' and int(x['seccion'])==donsec}
    originals={int(x['indice']):x for x in rev if int(x['seccion'])==section}
    if set(srcrows)!=set(range(len(fieldlist))) or set(originals)!=set(range(len(fieldlist))):raise ValueError('Ordinales incompletos')
    for idx,(rel,newraw) in enumerate(fieldlist):
     donor=srcrows[idx];jr=originals[idx];jraw=bytes.fromhex(jr['bytes_hex']);jpos=int(jr['offset_japones'])
     if jt[jpos:jpos+len(jraw)]!=jraw or sha(jraw)!=jr['sha256_campo']:raise ValueError('Campo japones distinto')
     key=donor['id'];m=master.get(key); expected=encode_field(m['espanol']) if m and m['espanol'].strip() else bytes.fromhex(donor['bytes_hex'])
     if expected!=newraw:raise ValueError(f'Traduccion donante distinta {key}')
     mapping.append(dict(seccion_text2=section,indice_jp=idx,offset_jp=jpos,sha256_jp=sha(jraw),donante_id=key,hoja_id=m['id'] if m else None,offset_text2_nuevo=bounds(rebuilt,11)[section]+rel,longitud_nueva=len(newraw),sha256_nuevo=sha(newraw),estado='identidad_jp_y_ordinal_no_valida_semantica'))
  outputs.append((d,rebuilt,dict(disco=d,sha256_base=sha(en),sha256_jp=sha(jt),sha256_nuevo=sha(rebuilt),bytes=len(rebuilt),sha256_donante_bbg=sha(bb),sha256_donante_wdata=sha(wd),estado='estructura_verificada_render_pendiente')))
 out.mkdir(parents=True)
 for d,b,meta in outputs:(out/f'TEXT2_D{d}_candidato.bin').write_bytes(b)
 (out/'mapeo-campos-D1.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in mapping),encoding='utf8')
 (out/'resultado.json').write_text(json.dumps([x[2] for x in outputs],ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print(json.dumps([x[2] for x in outputs],indent=2));print('Campos D1:',len(mapping))
if __name__=='__main__':main()
