"""Excepciones cerradas para remanentes JP; los demás campos usan sus guardas normales."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT/'trabajo/traduccion-en-es'


class ResidualProfiles:
    def __init__(self, master_path=WORK/'textos-ingles-espanol.csv', *, check_donors=True):
        self.entries = {}
        self.sources = {}
        self.locations = None
        self.profiles = []
        self.master_path = master_path
        specs = [
            ('perfiles-dialogos-ja-es.jsonl', 'perfiles_dialogos_ja_es'),
            ('perfiles-tablas-ja-es.jsonl', 'perfiles_tablas_ja_es'),
            ('perfiles-tablas-marcadores-ja-es.jsonl', 'perfiles_tablas_ja_es'),
        ]
        for filename, module_name in specs:
            path = WORK/'residuales-ja'/filename
            if not path.exists():
                continue
            module = __import__(module_name)
            loaded = module.load_profiles(path, check_donors=False) if module_name == 'perfiles_tablas_ja_es' else module.load_profiles(path)
            for p in loaded:
                self.profiles.append(p)
                for key in (p['id'], p['referencia']):
                    if key in self.entries:
                        raise ValueError('Perfil residual repetido: '+key)
                    self.entries[key] = (p, module.validate_profile)
        if check_donors:
            self.validate_donors()

    def validate_donors(self, rows=None):
        from codificacion_es import encode_field
        if rows is None:
            with Path(self.master_path).open(encoding='utf-8-sig', newline='') as f:
                rows = list(csv.DictReader(f))
        # Small diagnostic sheets may omit donors. Resolve those against the
        # canonical sheet, while every row supplied by the candidate overrides
        # it; a changed donor can never be hidden by consulting MASTER alone.
        with (WORK/'textos-ingles-espanol.csv').open(encoding='utf-8-sig', newline='') as f:
            by_id = {r['id']: r for r in csv.DictReader(f)}
        by_id.update({r['id']: r for r in rows})
        for p in self.profiles:
            for d in p.get('donantes', []):
                r = by_id.get(d['id'])
                if r is None or r['ingles'] != d['ingles'] or encode_field(r['espanol']).hex().upper() != d['es_hex'].upper():
                    raise ValueError('Donante ES stale en hoja candidata: '+d['id'])

    def has(self, identifier):
        return identifier in self.entries

    def _locations(self):
        if self.locations is not None:
            return
        from reinsertar_tablas_menus_es import records
        self.locations = {}
        for r in records():
            self.locations.setdefault(r['id'], []).append((r['key'], r['offset'], r['source']))
        path = WORK/'dialogos-verificados/dialogos-respaldo.jsonl'
        with path.open(encoding='utf8') as f:
            for line in f:
                r = json.loads(line)
                self.locations[r['id']] = [((int(r['disco']), r['ruta']), int(r['offset_payload']), r['sha256_mdt'])]

    def _source(self, key):
        if key not in self.sources:
            from inventariar_videos_bloques import read_movie
            d, path = key
            with (ROOT/f'trabajo/ingles/analisis/archivos-disco{d}.csv').open(encoding='utf-8-sig', newline='') as f:
                record = next(r for r in csv.DictReader(f) if r['ruta'] == path)
            with (ROOT/f'trabajo/ingles/salida/Grandia_EN_D{d}.bin').open('rb') as image:
                self.sources[key] = read_movie(image, record)
        return self.sources[key]

    def validate(self, identifier, original, target, *, row=None, record=None):
        p, validator = self.entries[identifier]
        canonical_key = (int(p['disco']), p['ruta'])
        if row is not None and (row['id'] != p['id'] or row['referencia'] != p['referencia'] or
                                (int(row['disco']), row['ruta']) != canonical_key):
            raise ValueError('Identidad de perfil distinta de la hoja: '+identifier)
        binding = p
        if record is not None:
            matches = [b for b in [p]+p.get('copias_fuente', []) if
                       (int(b['disco']), b['ruta']) == record['key'] and
                       int(b['offset_payload']) == record['offset'] and
                       (b.get('sha256_source') or b.get('sha256_mdt')).upper() == record['source'].upper()]
            if not matches:
                raise ValueError('Perfil no corresponde a esta copia: '+identifier)
            binding = matches[0]
        key = (int(binding['disco']), binding['ruta'])
        offset = int(binding['offset_payload'])
        digest = (binding.get('sha256_source') or binding.get('sha256_mdt')).upper()
        self._locations()
        if (key, offset, digest) not in self.locations.get(p['referencia'], []):
            raise ValueError('Perfil sin ubicación y hash acreditados en respaldo: '+identifier)
        source = self._source(key)
        if hashlib.sha256(source).hexdigest().upper() != digest or source[offset:offset+len(original)] != original:
            raise ValueError('Recurso o posición distintos del perfil residual: '+identifier)
        return validator(original, target, p)
