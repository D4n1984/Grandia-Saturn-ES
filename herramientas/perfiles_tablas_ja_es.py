#!/usr/bin/env python3
"""Perfiles cerrados para los 591 campos JP conservados en TEXT2 D1.

No activa una fuente ni cambia el códec. validate_profile recibe payloads, igual
que perfiles_dialogos_ja_es; el llamador debe validar antes recurso, ID y offset.
validate_source_binding ofrece esa comprobación al verificador independiente.
"""
from pathlib import Path
import csv,hashlib,json,re
from codificacion_es import encode_field,SPANISH_TO_BYTE

ROOT=Path(__file__).resolve().parent.parent
DEFAULT=ROOT/'trabajo/traduccion-en-es/residuales-ja/perfiles-tablas-ja-es.jsonl'
MASTER=ROOT/'trabajo/traduccion-en-es/textos-ingles-espanol.csv'
PARSER_VERSION='tablas-jp-cerradas-v1'
PARSER_SPEC='wide:10-1F-glyph2-including-1000,20-FF-glyph1-including-7F;native8-source:20-FF-glyph1;03:narrow;04:wide;other-01-0F:command1;narrow-target:20-7E,E2-F1-glyph1;native8-target:ASCII20-7E,max9,no-selector'
PARSER_SHA256=hashlib.sha256(PARSER_SPEC.encode('ascii')).hexdigest().upper()
REQUIRED={'id','referencia','disco','ruta','seccion','indice','offset_payload','sha256_source','sha256_payload','payload_original_hex','target_hex','sha256_target','modo_fuente','prefijo_metadata_hex','offsets_selectores_insertados','parser_version','parser_sha256','donantes'}
ALIAS_S3_FORMAT={
 'tablas:D1:BATLE/TEXT2.BIN:3:1:C1A':('106200DD9731FF40593B5CEE1C05BF872CC1CCFAF262DFD57A99D34F9667D8EB','71C304202A6C4238944251C6CE6E34FBA2B870B2AF740629C38EA21A0BF66ECC'),
 'tablas:D1:BATLE/TEXT2.BIN:3:34:CF8':('D1064B3842643A0CF67D694FA0A353D516368181CDE84AACE610A7D110B2133F','829CC4A8BCD5405FDD60A8AA7CF258D4755F872E9081A0D99A9984B7876A57A2'),
 'tablas:D1:BATLE/TEXT2.BIN:3:36:D00':('981469EBD9231D284DFA75308AABFB9A2241C71B6A216F661F8F70FB69A52E23','D1AB593DBC4989C6FCA096D4E2482F1E0E3BAA22A0FFE715C397F2E463B1027B')}
MARKER_IDS={'tablas:D1:BATLE/TEXT2.BIN:3:20:C7E','tablas:D1:BATLE/B001.BBG:2:20:534FE','tablas:D2:BATLE/B039.BBG:2:20:4F8DE'}
MARKER_COPIES={'tablas:D1:BATLE/TEXT2.BIN:3:20:C7E':1,'tablas:D1:BATLE/B001.BBG:2:20:534FE':42,'tablas:D2:BATLE/B039.BBG:2:20:4F8DE':72}

def sha(data):return hashlib.sha256(data).hexdigest().upper()
def _hex(value):
 if not isinstance(value,str) or not re.fullmatch(r'(?:[0-9A-Fa-f]{2})*',value):raise ValueError('Hexadecimal inválido')
 return bytes.fromhex(value)
def _hash(value):return isinstance(value,str) and bool(re.fullmatch(r'[0-9A-Fa-f]{64}',value))

def tokenize(raw,initial_mode='wide'):
 """Parser de tablas, no SCNRL: 1000 es un glifo ancho, no NUL ni argumento."""
 if not isinstance(raw,bytes) or initial_mode not in ('wide','native8'):raise ValueError('Payload o modo inválido')
 result=[];pos=0;mode=initial_mode
 while pos<len(raw):
  start=pos;b=raw[pos]
  if mode=='wide' and 0x10<=b<=0x1f:
   pos+=2;kind='glyph'
  elif b<0x20:
   if b==0:raise ValueError('NUL independiente dentro del payload')
   pos+=1;kind='command'
   if b==3:mode='narrow'
   elif b==4:mode='wide'
  else:pos+=1;kind='glyph'
  if pos>len(raw):raise ValueError('Glifo ancho truncado')
  result.append(dict(tipo=kind,inicio=start,fin=pos,bytes=raw[start:pos],modo=mode))
 return result

def _check_profile(p):
 if not isinstance(p,dict) or not REQUIRED<=p.keys():raise ValueError('Perfil incompleto')
 if p['parser_version']!=PARSER_VERSION or p['parser_sha256'].upper()!=PARSER_SHA256:raise ValueError('Parser distinto')
 marker=p.get('tipo')=='marcador_ascii'
 if marker:
  if p['id'] not in MARKER_IDS or _hex(p['payload_original_hex'])!=b'\xec'*9 or _hex(p['target_hex'])!=b'\x03'+b'?'*9:raise ValueError('Conversión de marcador fuera de tres IDs/bytes autorizados')
 elif p['disco']!=1 or p['ruta']!='BATLE/TEXT2.BIN' or p['seccion'] not in (2,3,5,10):raise ValueError('Familia fuera del alcance sellado')
 if not isinstance(p['indice'],int) or isinstance(p['indice'],bool) or p['indice']<0:raise ValueError('Índice inválido')
 if not isinstance(p['offset_payload'],int) or isinstance(p['offset_payload'],bool) or p['offset_payload']<0:raise ValueError('Offset inválido')
 if p['id']!='tablas:'+p['referencia']:raise ValueError('ID y referencia distintos')
 prefix=f"D{p['disco']}:{p['ruta']}:{p['seccion']}:{p['indice']}:"
 if not p['referencia'].startswith(prefix) or p['referencia'].split(':')[-1].upper()!=f"{p['offset_payload']:X}":raise ValueError('Identidad y ubicación distintas')
 if not all(_hash(p[k]) for k in ('sha256_source','sha256_payload','sha256_target','parser_sha256')):raise ValueError('Hash inválido')
 old=_hex(p['payload_original_hex']);target=_hex(p['target_hex']);meta=_hex(p['prefijo_metadata_hex'])
 if sha(old)!=p['sha256_payload'].upper() or sha(target)!=p['sha256_target'].upper():raise ValueError('Hashes internos distintos')
 mode='native8' if p['seccion']==2 and not marker else 'wide'
 if p['modo_fuente']!=mode:raise ValueError('Modo no autorizado para esta sección')
 if meta and (p['seccion']!=10 or p['indice']!=0 or len(meta)!=19):raise ValueError('Prefijo de metadatos fuera de su único campo')
 if p['seccion']==10 and p['indice']==0 and len(meta)!=19:raise ValueError('Faltan los 19 bytes de metadatos S10')
 offsets=p['offsets_selectores_insertados']
 if not isinstance(offsets,list) or any(not isinstance(x,int) or isinstance(x,bool) or x<0 for x in offsets) or offsets!=sorted(set(offsets)):raise ValueError('Selectores inválidos')
 if not isinstance(p['donantes'],list):raise ValueError('Vínculos de donantes inválidos')
 for d in p['donantes']:
  if not {'id','ingles','es_hex','sha256_es','tipo'}<=d.keys() or not _hash(d['sha256_es']) or sha(_hex(d['es_hex']))!=d['sha256_es'].upper():raise ValueError('Vínculo de donante incompleto')
 copies=p.get('copias_fuente',[])
 if not isinstance(copies,list) or (marker and len(copies)!=MARKER_COPIES[p['id']]) or (not marker and copies):raise ValueError('Lista de copias fuera del alcance sellado')
 seen=set()
 for b in copies:
  if not isinstance(b,dict) or not {'disco','ruta','offset_payload','sha256_source','sha256_payload'}<=b.keys() or b['disco'] not in (1,2) or isinstance(b['disco'],bool) or not isinstance(b['ruta'],str) or not isinstance(b['offset_payload'],int) or isinstance(b['offset_payload'],bool) or b['offset_payload']<0 or not _hash(b['sha256_source']) or b['sha256_payload']!=p['sha256_payload']:raise ValueError('Binding de copia inválido')
  identity=(b['disco'],b['ruta'],b['offset_payload'])
  if identity in seen:raise ValueError('Binding de copia duplicado')
  seen.add(identity)
 if marker and (p['disco'],p['ruta'],p['offset_payload']) not in seen:raise ValueError('Binding canónico ausente')
 if p.get('transformacion_formato')=='alias_S3_ES_exacto':
  expected=ALIAS_S3_FORMAT.get(p['id'])
  if expected!=(p['sha256_payload'].upper(),p['sha256_target'].upper()) or p['seccion']!=3 or not p['donantes'] or any(d['tipo']!='exacto' for d in p['donantes']):raise ValueError('Excepción de formato S3 fuera de ID/hashes/donante sellados')
 elif p.get('transformacion_formato')!='conservar_comandos':raise ValueError('Política de formato desconocida')

def validate_profile(original,target,profile):
 _check_profile(profile)
 if not isinstance(original,bytes) or not isinstance(target,bytes):raise ValueError('Se requieren bytes')
 if original.hex().upper()!=profile['payload_original_hex'].upper() or sha(original)!=profile['sha256_payload'].upper():raise ValueError('Payload fuente distinto del perfil')
 if target.hex().upper()!=profile['target_hex'].upper() or sha(target)!=profile['sha256_target'].upper():raise ValueError('Destino distinto del perfil cerrado')
 meta=_hex(profile['prefijo_metadata_hex']);prefix=len(meta)
 if original[:prefix]!=meta or target[:prefix]!=meta:raise ValueError('Metadatos S10 alterados')
 if profile['modo_fuente']=='native8':
  if profile['offsets_selectores_insertados'] or len(target)>9 or any(x<32 or x>126 for x in target):raise ValueError('Corta fuera de ASCII nativo, nueve bytes o sin selector')
 else:
  if not target[prefix:].startswith(b'\x03') or profile['offsets_selectores_insertados']!=[prefix]:raise ValueError('Falta selector estrecho inicial independiente')
 old=tokenize(original[prefix:],profile['modo_fuente']);new=tokenize(target[prefix:],profile['modo_fuente'])
 inserted={x-prefix for x in profile['offsets_selectores_insertados']}
 actual={t['inicio'] for t in new if t['tipo']=='command' and t['bytes']==b'\x03'}
 if not inserted<=actual:raise ValueError('Selector declarado no es comando independiente')
 allowed=set(range(32,127))|set(SPANISH_TO_BYTE.values())
 for t in new:
  if t['tipo']=='glyph' and (len(t['bytes'])!=1 or t['bytes'][0] not in allowed or t['modo'] not in ('narrow','native8')):raise ValueError('Texto destino fuera de fuente ES acreditada para perfil')
 signature=lambda ts,skip:[t['bytes'] for t in ts if t['tipo']=='command' and t['inicio'] not in skip]
 if signature(old,set())!=signature(new,inserted) and profile['transformacion_formato']!='alias_S3_ES_exacto':raise ValueError('Comandos originales 03/04 u otros alterados')
 for d in profile['donantes']:
  if d['tipo']=='exacto' and target[prefix:]!=_hex(d['es_hex']):raise ValueError('Destino no conserva exactamente el ES del donante')
 return True

def validate_source_binding(resource,profile,*,identifier=None,disco=None,ruta=None,offset=None):
 _check_profile(profile)
 if identifier is not None and identifier!=profile['id']:raise ValueError('ID del llamador distinto')
 binding={k:profile[k] for k in ('disco','ruta','offset_payload','sha256_source','sha256_payload')}
 context={'disco':profile['disco'] if disco is None else disco,'ruta':profile['ruta'] if ruta is None else ruta,'offset_payload':profile['offset_payload'] if offset is None else offset}
 candidates=[b for b in [binding]+profile.get('copias_fuente',[]) if all(b[k]==v for k,v in context.items())]
 if not candidates:raise ValueError('Disco, ruta u offset del llamador distinto')
 if not isinstance(resource,bytes) or not any(sha(resource)==b['sha256_source'].upper() for b in candidates):raise ValueError('SHA del recurso completo distinto')
 start=context['offset_payload'];raw=_hex(profile['payload_original_hex'])
 if resource[start:start+len(raw)]!=raw or resource[start+len(raw):start+len(raw)+1]!=b'\0':raise ValueError('Payload o terminador distinto en la ubicación sellada')
 return True

def validate_donors(profiles,master_path=MASTER):
 with Path(master_path).open(encoding='utf-8-sig',newline='') as f: rows={r['id']:r for r in csv.DictReader(f)}
 for p in profiles:
  for d in p['donantes']:
   r=rows.get(d['id'])
   if r is None or r['ingles']!=d['ingles'] or encode_field(r['espanol']).hex().upper()!=d['es_hex'].upper():raise ValueError(f"Donante ES stale para {p['id']}: {d['id']}")
 return True

def load_profiles(path=DEFAULT,*,check_donors=True,master_path=MASTER):
 with Path(path).open(encoding='utf-8') as f:profiles=[json.loads(l) for l in f if l.strip()]
 seen=set()
 for p in profiles:
  _check_profile(p)
  if p['id'] in seen:raise ValueError('ID duplicado')
  seen.add(p['id']);validate_profile(_hex(p['payload_original_hex']),_hex(p['target_hex']),p)
 if check_donors:validate_donors(profiles,master_path)
 return profiles
