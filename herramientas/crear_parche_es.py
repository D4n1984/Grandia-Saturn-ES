#!/usr/bin/env python3
"""Crear paquete experimental xdelta JP a ES en trabajo/distribucion."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from aplicar_parche_es import Error, cue, digest, name, apply

ROOT = Path(__file__).resolve().parent.parent
DISTRIBUCION = ROOT / 'trabajo' / 'distribucion'

LAUNCHER_CMD = r'''@echo off
setlocal
if not "%~1"=="" goto argumentos
set /p cue=Ruta completa al CUE japones:
set "cue=%cue:"=%"
set /p destino=Ruta de carpeta NUEVA para el CHD:
set "destino=%destino:"=%"
"%~dp0python\python.exe" "%~dp0aplicar_parche_es.py" "%~dp0." "%cue%" "%destino%"
set "grandia_result=%errorlevel%"
goto fin
:argumentos
"%~dp0python\python.exe" "%~dp0aplicar_parche_es.py" "%~dp0." %*
set "grandia_result=%errorlevel%"
:fin
pause
exit /b %grandia_result%
'''

def build(disc, original, target, xdelta, license_path, chdman, chd_license, runtime, output):
    output = output.resolve()
    if not output.is_relative_to(DISTRIBUCION.resolve()) or output == DISTRIBUCION.resolve():
        raise Error('El paquete debe estar dentro de trabajo/distribucion')
    if output.exists(): raise Error('El paquete ya existe')
    source_text, source_files = cue(original)
    target_text, target_files = cue(target)
    if len(target_files) != 1: raise Error('El destino debe tener un único BIN')
    paths = [original.parent / n for n in source_files]
    target_bin = target.parent / target_files[0]
    if any(p.resolve().parent != original.parent for p in paths) or target_bin.resolve().parent != target.parent:
        raise Error('Una pista apunta fuera de la carpeta de su CUE')
    tracks = [digest(p) for p in paths]
    target_desc = digest(target_bin)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.crear-', dir=output.parent) as t:
        t = Path(t); package = t / 'paquete'; package.mkdir()
        source = t / 'origen.bin'
        with source.open('xb') as w:
            for p in paths:
                with p.open('rb') as r: shutil.copyfileobj(r, w, 1024 * 1024)
        for p, expected in zip(paths, tracks):
            if digest(p) != expected: raise Error('El origen cambió durante la lectura')
        exe = 'xdelta3.exe' if xdelta.suffix.lower() == '.exe' else 'xdelta3'
        shutil.copy2(xdelta, package / exe)
        shutil.copy2(license_path, package / 'LICENCIA-xdelta.txt')
        chdexe = 'chdman.exe' if chdman.suffix.lower() == '.exe' else 'chdman'
        shutil.copy2(chdman, package / chdexe)
        shutil.copy2(chd_license, package / 'LICENCIA-chdman.txt')
        gpl = chd_license.with_name('MAME_GPL-2.0.txt')
        if not gpl.is_file(): raise Error('Falta MAME_GPL-2.0.txt junto a la licencia de chdman')
        shutil.copy2(gpl, package / 'MAME_GPL-2.0.txt')
        shutil.copytree(runtime, package / 'python')
        (package / 'aplicar.cmd').write_bytes(LAUNCHER_CMD.replace('\n', '\r\n').encode('ascii'))
        shutil.copy2(Path(__file__).with_name('aplicar_parche_es.py'), package / 'aplicar_parche_es.py')
        delta = f'{disc}.xdelta'
        subprocess.run([str((package / exe).resolve()), '-e', '-s', str(source), str(target_bin.resolve()), str((package / delta).resolve())], check=True)
        if digest(target_bin) != target_desc: raise Error('El destino cambió durante la lectura')
        outbin, outcue = f'Grandia_ES_{disc}.bin', f'Grandia_ES_{disc}.cue'
        output_cue = target_text.replace('{0}', outbin)
        manifest = {'formato':'grandia-xdelta3-v1', 'disco':disc, 'cue_origen':source_text,
                    'pistas':tracks, 'origen_concatenado':digest(source), 'destino':target_desc,
                    'delta':{'nombre':delta,'identidad':digest(package / delta)},
                    'xdelta':{'nombre':exe,'identidad':digest(package / exe)},
                    'chdman':{'nombre':chdexe,'identidad':digest(package / chdexe)}, 'salida_chd':f'Grandia_ES_{disc}.chd',
                    'salida_bin':outbin,'salida_cue':outcue,'cue_destino':output_cue}
        (package / 'manifiesto.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        # Decode before publishing the package and compare every byte by SHA-256.
        source.unlink()
        apply(package, original, t / 'verificacion')
        package.rename(output)
    print(f'Paquete verificado: {output}')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--disco', choices=['D1','D2'], required=True)
    p.add_argument('--origen', type=Path, required=True, help='CUE japonés')
    p.add_argument('--destino', type=Path, required=True, help='CUE español construido')
    p.add_argument('--xdelta', type=Path, required=True)
    p.add_argument('--licencia', type=Path, required=True)
    p.add_argument('--chdman', type=Path, required=True)
    p.add_argument('--licencia-chdman', type=Path, required=True)
    p.add_argument('--python', type=Path, required=True, help='Directorio de Python portátil para Windows')
    p.add_argument('--salida', type=Path, required=True, help='Carpeta nueva dentro de trabajo/distribucion')
    a = p.parse_args()
    try: build(a.disco, a.origen.resolve(), a.destino.resolve(), a.xdelta.resolve(), a.licencia.resolve(), a.chdman.resolve(), a.licencia_chdman.resolve(), a.python.resolve(), a.salida)
    except (Error, OSError, ValueError, subprocess.CalledProcessError) as e:
        print(f'Error: {e}', file=sys.stderr); return 1
    return 0
if __name__ == '__main__': sys.exit(main())
