#!/usr/bin/env python3
"""Comprobar un paquete aplicándolo y verificando el BIN resultante."""
import argparse
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
from aplicar_parche_es import apply, Error
import subprocess

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('paquete', type=Path)
    p.add_argument('cue_japones', type=Path)
    a = p.parse_args()
    try:
        with tempfile.TemporaryDirectory(prefix='grandia-verificar-') as t:
            apply(a.paquete, a.cue_japones, Path(t) / 'salida')
    except (Error, OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as e:
        print(f'Error: {e}', file=sys.stderr); return 1
    return 0
if __name__ == '__main__': sys.exit(main())
