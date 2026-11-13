#!/usr/bin/env python3
"""Integra propuestas locales EN->ES sin sobrescribir traducciones previas."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codificacion_es import encode_field
from preparar_recursos_traducidos_es import dialogue_controls, protected
from reinsertar_tablas_menus_es import controls
from formatos_texto_es import validar_printf
from perfiles_residuales_es import ResidualProfiles

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / 'trabajo/traduccion-en-es'
MASTER = WORK / 'textos-ingles-espanol.csv'
STATES = {'traducido_pendiente_revision', 'revisado_editorial'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def combine(master, proposals):
    """Valida todo en memoria. Una propuesta nunca borra una edición previa."""
    text = master.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text, newline=''))
    fields = reader.fieldnames
    required = {'id', 'ingles', 'espanol', 'revision', 'notas', 'categoria'}
    if not fields or not required <= set(fields):
        raise ValueError('Cabecera de maestra incompleta')
    rows = list(reader)
    by_id = {r['id']: r for r in rows}
    if len(by_id) != len(rows) or any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError('Maestra con IDs o columnas incorrectos')
    seen = {}; changes = []; existing = []
    residuals = ResidualProfiles(check_donors=False)
    for proposal in proposals:
        if not isinstance(proposal, dict) or not {'id', 'ingles', 'espanol', 'revision', 'notas'} <= proposal.keys():
            raise ValueError('Propuesta incompleta')
        ident = proposal['id']
        if ident not in by_id:
            raise ValueError('ID desconocido: ' + str(ident))
        if ident in seen:
            if proposal != seen[ident]:
                raise ValueError('Propuestas contradictorias: ' + ident)
            continue
        seen[ident] = proposal
        row = by_id[ident]
        if proposal['ingles'] != row['ingles']:
            raise ValueError('Inglés distinto de maestra: ' + ident)
        new = proposal['espanol']
        if not isinstance(new, str) or not new.strip() or proposal['revision'] not in STATES:
            raise ValueError('Texto vacío o estado no autorizado: ' + ident)
        if new == row['ingles'] and not proposal['notas'].startswith('conservar_nombre:') and not proposal['notas'].startswith('sin_cambio_justificado:'):
            raise ValueError('Texto idéntico sin justificación explícita: ' + ident)
        try:
            old_raw, new_raw = encode_field(row['ingles']), encode_field(new)
        except ValueError as e:
            raise ValueError(f'{ident}: {e}') from e
        if residuals.has(ident):
            residuals.validate(ident, old_raw, new_raw, row=row)
        elif protected(row['ingles']) != protected(new):
            raise ValueError('Marcadores alterados: ' + ident)
        if residuals.has(ident):
            pass
        elif row['categoria'] == 'dialogos':
            if dialogue_controls(old_raw) != dialogue_controls(new_raw):
                raise ValueError('Parámetros binarios alterados: ' + ident)
        else:
            if controls(old_raw) != controls(new_raw):
                raise ValueError('Controles de tabla alterados: ' + ident)
            validar_printf(row['ingles'], new)
        if row['espanol'].strip():
            if row['espanol'] != new:
                if (proposal.get('espanol_anterior') != row['espanol'] or
                    proposal['revision'] != 'revisado_editorial' or
                    row['revision'] not in STATES):
                    raise ValueError('Ya existe traducción; resolver manualmente: ' + ident)
                row.update(espanol=new, revision=proposal['revision'], notas=proposal['notas'])
                changes.append(ident)
                continue
            if (proposal['revision'] == 'revisado_editorial' and row['revision'] in
                    {'traducido_pendiente_revision', 'prueba_pantalla_inicial_comprobada_emulador'}):
                row.update(revision='revisado_editorial', notas=proposal['notas'])
                changes.append(ident)
                continue
            existing.append(ident)
            continue
        row.update(espanol=new, revision=proposal['revision'], notas=proposal['notas'])
        changes.append(ident)
    residuals.validate_donors(rows)
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader(); writer.writerows(rows)
    return buffer.getvalue().encode('utf-8-sig'), changes, existing


def integrate(paths, master=MASTER, *, apply=False, structural=False, repairs=()):
    master = Path(master).resolve(); master.relative_to(WORK.resolve())
    data = master.read_bytes(); proposals = []; inputs = []
    for path in paths:
        path = Path(path).resolve(); path.relative_to(WORK.resolve())
        raw = path.read_bytes()
        proposals.extend(json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip())
        inputs.append({'ruta': str(path), 'sha256': digest(raw)})
    result, changes, existing = combine(data, proposals)
    previous = {r['id'] for r in csv.DictReader(io.StringIO(data.decode('utf-8-sig'))) if r['espanol'].strip()}
    if structural:
        from comprobar_traduccion_es import audit
        with tempfile.NamedTemporaryFile(dir=master.parent, suffix='.csv', delete=False) as f:
            candidate = Path(f.name); f.write(result)
        try:
            quality = audit(candidate, structural=True, repairs=repairs)
            errors = [i for i in quality['incidencias'] if i['nivel'] == 'ERROR']
            if errors:
                raise ValueError('Lote rechazado antes de escribir: ' + '; '.join(i['mensaje'] for i in errors))
        finally:
            candidate.unlink(missing_ok=True)
    report = dict(sha256_antes=digest(data), sha256_despues=digest(result),
                  nuevas=sum(i not in previous for i in changes), actualizadas=sum(i in previous for i in changes),
                  ya_existentes=len(existing), ids_nuevos=changes, propuestas=inputs,
                  reparaciones_estructurales=list(repairs), aplicado=False)
    if apply and changes:
        archive = WORK / 'historial-integracion'; archive.mkdir(parents=True, exist_ok=True)
        backup = archive / (digest(data) + '.csv')
        if backup.exists() and backup.read_bytes() != data:
            raise ValueError('Respaldo existente distinto')
        backup.write_bytes(data)
        with tempfile.NamedTemporaryFile(dir=master.parent, suffix='.tmp', delete=False) as f:
            pending = Path(f.name); f.write(result)
        try:
            if master.read_bytes() != data:
                raise ValueError('La maestra cambió durante la integración')
            os.replace(pending, master)
        finally:
            pending.unlink(missing_ok=True)
        report['aplicado'] = True
        (archive / (digest(result) + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('lotes', nargs='+', type=Path)
    p.add_argument('--maestra', type=Path, default=MASTER)
    p.add_argument('--aplicar', action='store_true')
    p.add_argument('--estructural', action='store_true', help='Reconstruir la candidata antes de modificar la maestra')
    p.add_argument('--reparar', action='append', choices=('2404', 'E414', 'B108'), default=[])
    a = p.parse_args()
    r = integrate(a.lotes, a.maestra, apply=a.aplicar, structural=a.estructural, repairs=a.reparar)
    print(f"{r['nuevas']} nuevas; {r['actualizadas']} revisadas; {r['ya_existentes']} existentes; aplicado={r['aplicado']}")


if __name__ == '__main__':
    main()
