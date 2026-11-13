#!/usr/bin/env python3
"""Perfiles cerrados de diálogos japoneses: validación estática, sin render.

El llamador debe verificar el hash del MDT completo y la ubicación antes de
invocar validate_profile: la API solo recibe los bytes de payload.
"""
import hashlib,json,re
from pathlib import Path
from codificacion_es import SPANISH_TO_BYTE

ROOT=Path(__file__).resolve().parent.parent
DEFAULT=ROOT/'trabajo/traduccion-en-es/residuales-ja/perfiles-dialogos-ja-es.jsonl'
PARSER_VERSION='scnrl-static-v1'
PARSER_SPEC='00-09:command1;0A-0F:command3;wide:10-1F-glyph2,20-FF-glyph1;narrow:10-FF-glyph1;03:narrow;04:wide'
PARSER_SHA256=hashlib.sha256(PARSER_SPEC.encode('ascii')).hexdigest().upper()
CONSUMER_SHA256='CE5C2A84905E4FD3E9AB5B019C8C902A1C3C76F1CCEE34F4BC4D5B0419326B1C'
REQUIRED={'id','referencia','disco','ruta','offset_payload','sha256_mdt','sha256_payload','target_hex','sha256_target','offsets_selectores_insertados','parser_version','parser_sha256','sha256_consumidor','evidencia_consumidor'}
def sha(data):return hashlib.sha256(data).hexdigest().upper()
def tokenize(raw,initial_mode='wide'):
 if not isinstance(raw,bytes) or initial_mode not in ('wide','narrow'):raise ValueError('Entrada o modo inválido')
 tokens=[];pos=0;mode=initial_mode
 while pos<len(raw):
  start=pos;byte=raw[pos]
  if byte<=9:
   pos+=1;kind='command'
   if byte==3:mode='narrow'
   elif byte==4:mode='wide'
  elif byte<=15:
   pos+=3;kind='command'
  else:
   pos+=2 if mode=='wide' and byte<=31 else 1;kind='glyph'
  if pos>len(raw):raise ValueError(f'Token truncado en {start:#x}')
  tokens.append(dict(tipo=kind,inicio=start,fin=pos,bytes=raw[start:pos],modo=mode))
 return tokens

def _hashfield(value):return isinstance(value,str) and bool(re.fullmatch(r'[0-9A-Fa-f]{64}',value))
def _check_profile(p):
 if not isinstance(p,dict) or not REQUIRED<=p.keys():raise ValueError('Perfil incompleto')
 if not all(isinstance(p[k],str) and p[k] for k in ('id','referencia','ruta','evidencia_consumidor')):raise ValueError('Identidad o evidencia ausente')
 if p['disco'] not in (1,2) or isinstance(p['disco'],bool) or not isinstance(p['offset_payload'],int) or isinstance(p['offset_payload'],bool) or p['offset_payload']<0:raise ValueError('Ubicación inválida')
 if not all(_hashfield(p[k]) for k in ('sha256_mdt','sha256_payload','sha256_target','parser_sha256','sha256_consumidor')):raise ValueError('Hash inválido')
 if p['parser_version']!=PARSER_VERSION or p['parser_sha256'].upper()!=PARSER_SHA256 or p['sha256_consumidor'].upper()!=CONSUMER_SHA256:raise ValueError('Parser o consumidor distinto')
 if not isinstance(p['target_hex'],str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2})+',p['target_hex']):raise ValueError('Payload hexadecimal inválido')
 offsets=p['offsets_selectores_insertados']
 if not isinstance(offsets,list) or not offsets or any(not isinstance(x,int) or isinstance(x,bool) or x<0 for x in offsets) or offsets!=sorted(set(offsets)):raise ValueError('Selectores inválidos')

def validate_profile(original,target,profile):
 _check_profile(profile)
 if not isinstance(original,bytes) or not isinstance(target,bytes):raise ValueError('Payload inválido')
 if sha(original)!=profile['sha256_payload'].upper() or target.hex().upper()!=profile['target_hex'].upper() or sha(target)!=profile['sha256_target'].upper():raise ValueError('Fuente o destino no coincide con perfil cerrado')
 if (len(target)-len(original))%2:raise ValueError('Diferencia de longitud impar')
 old=tokenize(original);new=tokenize(target);offsets=set(profile['offsets_selectores_insertados'])
 real={t['inicio'] for t in new if t['tipo']=='command' and t['bytes']==b'\x03'}
 if not offsets<=real:raise ValueError('Selector insertado no es comando independiente 03')
 allowed=set(range(0x20,0x7f))|set(SPANISH_TO_BYTE.values())
 for t in new:
  if t['tipo']=='glyph' and (len(t['bytes'])!=1 or t['bytes'][0] not in allowed or t['modo']!='narrow'):raise ValueError('Texto destino fuera de fuente estrecha ES')
 def signature(tokens,skip):
  return [t['bytes'] for t in tokens if t['tipo']=='command' and t['inicio'] not in skip and t['bytes']!=b'\x01']
 if signature(old,set())!=signature(new,offsets):raise ValueError('Comandos o parámetros alterados')
 return True

def load_profiles(path=DEFAULT):
 with Path(path).open(encoding='utf8') as f: profiles=[json.loads(line) for line in f if line.strip()]
 seen=set()
 for p in profiles:
  _check_profile(p)
  if p['id'] in seen:raise ValueError('Perfil duplicado')
  seen.add(p['id'])
 return profiles
