"""Journaux structurés JSON sur stdout (lus par Cloud Logging).

Champs autorisés uniquement : jamais de code source, de contenu de rapport, de jeton ni de donnée
personnelle. Les messages libres sont tronqués pour limiter le volume de Cloud Logging.
"""
import json
import sys
import time

ALLOWED = {'submission_id', 'backend', 'duration_seconds', 'outcome', 'tests_version', 'image_version',
           'error_category', 'error_code', 'sandbox_status', 'project', 'files', 'archive_bytes', 'detail'}


def log(severity, message, **fields):
    entry = dict(severity=severity, message=message[:200], time=round(time.time(), 3))
    for key, value in fields.items():
        if key not in ALLOWED:
            raise ValueError(f'champ de journal non autorisé : {key}')
        entry[key] = value[:500] if isinstance(value, str) else value
    sys.stdout.write(json.dumps(entry, ensure_ascii=False) + '\n')
    sys.stdout.flush()
