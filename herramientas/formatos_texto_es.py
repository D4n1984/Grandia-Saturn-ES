"""Validación independiente de formatos printf en textos del juego."""
import re

PRINTF = re.compile(r"%(?:\d+\$)?[-+ #0']*(?:\d+|\*(?:\d+\$)?)?(?:\.(?:\d+|\*(?:\d+\$)?))?(?:hh|ll|[hljztL])?[diouxXfFeEgGaAcspn%]")


def printf_tokens(text):
    return [m.group() for m in PRINTF.finditer(text)]


def validar_printf(ingles, espanol):
    """Conserva los formatos y %% e impide introducir nuevos argumentos."""
    original = printf_tokens(ingles)
    if original != printf_tokens(espanol):
        raise ValueError('Marcadores printf modificados o introducidos')
    if original and '%' in PRINTF.sub('', espanol):
        raise ValueError('Marcadores printf modificados o porcentaje sin escapar')
