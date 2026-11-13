"""Codificación española de prueba para la fuente FDATA ampliada, con controles."""
import re

SPANISH_TO_BYTE={char:0xE2+i for i,char in enumerate('ñáéíóúü¿¡ÑÁÉÍÓÚÜ')}
BYTE_TO_SPANISH={value:key for key,value in SPANISH_TO_BYTE.items()}


def encode_field(text):
    result=bytearray();pos=0
    text=text.replace('\r\n','\n')
    while pos<len(text):
        char=text[pos]
        if char=='<':
            token=text[pos:pos+4]
            if not re.fullmatch(r'<[0-9A-F]{2}>',token):raise ValueError('Marcador inválido; usar <3C> para un ángulo literal')
            result.append(int(token[1:3],16));pos+=4;continue
        if char=='\n':result.append(1)
        elif char in SPANISH_TO_BYTE:result.append(SPANISH_TO_BYTE[char])
        elif 32<=ord(char)<=126 and char!='>':result.append(ord(char))
        else:raise ValueError(f'Carácter no soportado: U+{ord(char):04X}')
        pos+=1
    return bytes(result)


def decode_field(raw):
    parts=[];pos=0
    while pos<len(raw):
        b=raw[pos];size=0
        if b==15 and pos+6<=len(raw) and raw[pos+1] in (3,18,33) and raw[pos+2]==10:size=6
        elif b==9 and pos+4<=len(raw) and raw[pos+1] in (11,12,15):size=4
        elif b==14 and pos+3<=len(raw) and raw[pos+1]==0:size=3
        elif b==16 and pos+2<=len(raw):size=2
        if size:
            parts.extend(f'<{n:02X}>' for n in raw[pos:pos+size]);pos+=size;continue
        parts.append(BYTE_TO_SPANISH[b] if b in BYTE_TO_SPANISH else chr(b) if 32<=b<=126 and b not in (60,62) else f'<{b:02X}>')
        pos+=1
    return ''.join(parts)
