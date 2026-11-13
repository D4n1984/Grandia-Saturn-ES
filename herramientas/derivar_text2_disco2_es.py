"""Deriva TEXT2 D2 por secciones cuya identidad JP está comprobada, sin mezclar textos."""
from preparar_puente_text2_es import bounds, chunks, pack, loadjp
from comparar_text2_discos import original


def derive(source_d2, translated_d1, wdata_d2):
    jp1, jp2 = original(1), original(2)
    if source_d2 != jp2:
        raise ValueError('TEXT2 D2 no corresponde al original JP acreditado')
    first = chunks(jp1, bounds(jp1, 11))
    second = chunks(jp2, bounds(jp2, 11))
    jp_wdata = loadjp(2, 'FIELD/WDATA.DAT')
    jp_wparts = chunks(jp_wdata, bounds(jp_wdata, 13))
    if any(first[i] != second[i] for i in range(11) if i != 9):
        raise ValueError('Secciones compartidas TEXT2 JP distintas')
    if second[9] != jp_wparts[4]:
        raise ValueError('TEXT2 D2 sección 9 no coincide con WDATA JP sección 4')
    result = chunks(translated_d1, bounds(translated_d1, 11))
    spanish_wparts = chunks(wdata_d2, bounds(wdata_d2, 13))
    result[9] = spanish_wparts[4]
    built = pack(result)
    check = chunks(built, bounds(built, 11))
    if check != result:
        raise ValueError('Derivación TEXT2 no conserva las secciones traducidas')
    return built
