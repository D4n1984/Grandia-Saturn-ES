"""Comprueba CMD real: rutas con espacios, entrada interactiva y estado de error."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'herramientas'))
from crear_parche_es import LAUNCHER_CMD


def main():
    with tempfile.TemporaryDirectory(prefix='cmd con espacios ',dir=ROOT/'trabajo') as tmp:
        package=Path(tmp)
        shutil.copytree(ROOT/'trabajo/python312',package/'python')
        launcher=package/'aplicar.cmd'
        launcher.write_bytes(LAUNCHER_CMD.replace('\n','\r\n').encode('ascii'))
        (package/'aplicar_parche_es.py').write_text(
            "import json,sys\nfrom pathlib import Path\n"
            "p=Path(__file__).parent\n"
            "assert Path(sys.argv[1]).resolve()==p.resolve()\n"
            "(p/'argv.json').write_text(json.dumps(sys.argv[1:]),encoding='utf8')\n"
            "sys.exit(23 if sys.argv[-1].endswith('error') else 0)\n",encoding='utf8')
        source=str(package/'original japones (4M).cue')
        output=str(package/'salida CHD')
        cases=[(f'"{source}" "{output}"',b'\r\n',output,0),
               ('',(source+'\r\n'+output+'\r\n\r\n').encode('ascii'),output,0),
               ('',('"'+source+'"\r\n"'+output+'"\r\n\r\n').encode('ascii'),output,0),
               (f'"{source}" "{output} error"',b'\r\n',output+' error',23)]
        for arguments,stdin,expected,code in cases:
            command=f'cmd.exe /d /c ""{launcher}" {arguments}"'
            input_file=package/'entrada.txt';input_file.write_bytes(stdin)
            with input_file.open('rb') as stream:
                r=subprocess.run(command,stdin=stream,capture_output=True,timeout=20)
            assert r.returncode==code,(r.returncode,r.stdout,r.stderr)
            values=json.loads((package/'argv.json').read_text(encoding='utf8'))
            assert values[1:]==[source,expected],(values,r.stdout,r.stderr)
    print('CMD: rutas con espacios, comillas interactivas y propagacion de error correctas')


if __name__=='__main__':main()
