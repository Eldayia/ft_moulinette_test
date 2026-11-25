import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ftm_platform.settings import Settings, SettingsError, database_url  # noqa: E402
from ftm_platform.security import hash_password, verify_password, new_token, token_hash  # noqa: E402

BASE = dict(DATABASE_URL='postgresql+psycopg://ftm:x@db/ftm', REDIS_URL='redis://redis:6379/0',
            FTM_PUBLIC_ORIGIN='https://moulinette.example')


class SettingsTests(unittest.TestCase):
    def test_password_from_docker_secret(self):
        with tempfile.NamedTemporaryFile('w', delete=False) as handle:
            handle.write('p@ss/w:rd%\n')
        url = database_url(dict(DATABASE_URL='postgresql+psycopg://ftm:{password}@db/ftm', DATABASE_PASSWORD_FILE=handle.name))
        self.assertEqual(url, 'postgresql+psycopg://ftm:p%40ss%2Fw%3Ard%25@db/ftm')
        with self.assertRaises(SettingsError):
            database_url(dict(DATABASE_URL='postgresql+psycopg://ftm:x@db/ftm', DATABASE_PASSWORD_FILE=handle.name))
        Path(handle.name).unlink()

    def test_production_requirements(self):
        self.assertTrue(Settings.from_env(BASE).cookie_secure)
        self.assertTrue(Settings.from_env(dict(BASE, FTM_COOKIE_SECURE='0')).cookie_secure)  # forcé en production
        for broken in (dict(BASE, FTM_PUBLIC_ORIGIN='http://moulinette.example'), dict(BASE, DATABASE_URL='sqlite://'),
                       dict(BASE, REDIS_URL=''), dict(BASE, FTM_SESSION_HOURS='0')):
            with self.assertRaises(SettingsError, msg=broken):
                Settings.from_env(broken)


class SecurityTests(unittest.TestCase):
    def test_passwords_and_tokens(self):
        stored = hash_password('un mot de passe solide')
        self.assertTrue(stored.startswith('scrypt$'))
        self.assertTrue(verify_password('un mot de passe solide', stored))
        self.assertFalse(verify_password('autre chose', stored))
        self.assertFalse(verify_password('x', 'corrompu'))
        with self.assertRaises(ValueError):
            hash_password('court')
        token, digest = new_token('pat')
        self.assertTrue(token.startswith('ftm_pat_'))
        self.assertEqual(token_hash(token), digest)
        self.assertNotEqual(new_token('pat')[0], token)


if __name__ == '__main__':
    unittest.main()
