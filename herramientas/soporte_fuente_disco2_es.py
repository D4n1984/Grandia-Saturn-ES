"""Traslada a FDATA D2 exclusivamente los cambios de la fuente ES verificada D1.

La identidad de los tres archivos completos se comprueba antes de aplicar nada.
La validación visual y de carga del resultado D2 sigue pendiente.
"""
import hashlib

D1_ORIGINAL_SHA = '26DD216A9409DDE00E37E248B8E0B31958BE025EEF8C42081D32606FC69E339A'
D2_ORIGINAL_SHA = '965FBD0ADC6C6DB8D03CE54BC6413EB2F8F206C77C10A8960BC0F377F1A04E9E'
D1_COMBINADA_SHA = '66A86226951D0A9D7100F3F84CE9F4F14B700E923F9F8BD7DC445D8D4EBE2C36'
RANGOS = ((0xC4, 0x100), (0x800, 0x8A0), (0xC840, 0xCA40))


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def build(source_d2, original_d1, combinado_d1):
    """Devuelve bytes D2 con exactamente los 592 cambios observados en D1."""
    if (sha(source_d2), sha(original_d1), sha(combinado_d1)) != (D2_ORIGINAL_SHA, D1_ORIGINAL_SHA, D1_COMBINADA_SHA):
        raise ValueError('FDATA fuente o combinada no coincide con los hashes comprobados')
    if len(source_d2) != 64608 or len(original_d1) != 65008 or len(combinado_d1) != len(original_d1):
        raise ValueError('Longitud FDATA inesperada')
    if source_d2[:0xA00] != original_d1[:0xA00] or source_d2[0xAC00:0xCC00] != original_d1[0xAC00:0xCC00]:
        raise ValueError('Prefijo o atlas 8x8 diferentes')
    cambios = [i for i, (a, b) in enumerate(zip(original_d1, combinado_d1)) if a != b]
    if len(cambios) != 592 or any(not any(a <= i < b for a, b in RANGOS) for i in cambios):
        raise ValueError('Los cambios de la fuente combinada exceden los rangos verificados')
    if any(source_d2[i] != original_d1[i] for i in cambios):
        raise ValueError('Los bytes originales en las posiciones modificadas no coinciden')
    salida = bytearray(source_d2)
    for i in cambios:
        salida[i] = combinado_d1[i]
    if len(salida) != len(source_d2) or sum(a != b for a, b in zip(salida, source_d2)) != 592:
        raise AssertionError('No se conservaron el tamaño o los bytes ajenos a los cambios')
    return bytes(salida)
