import unittest

from ft_moulinette_runners.cloudrun import CloudRunRunner
from ft_moulinette_runners.config import ConfigurationError, backend_from_env, executions_enabled, limits_from_env
from ft_moulinette_runners.local import LocalRunner
from ft_moulinette_runners.mock import MockRunner

CLOUDRUN = dict(EXECUTION_BACKEND='cloudrun', CLOUD_RUN_URL='https://runner-abc-ew.a.run.app',
                GOOGLE_APPLICATION_CREDENTIALS='/run/secrets/gcp_invoker')


class SelectionTests(unittest.TestCase):
    def test_explicit_selection(self):
        self.assertIsInstance(backend_from_env(dict(EXECUTION_BACKEND='local')), LocalRunner)
        self.assertIsInstance(backend_from_env(dict(EXECUTION_BACKEND='mock')), MockRunner)
        backend = backend_from_env(CLOUDRUN)
        self.assertIsInstance(backend, CloudRunRunner)
        self.assertEqual(backend.tokens.audience, CLOUDRUN['CLOUD_RUN_URL'])
        self.assertEqual(backend.tokens.mode, 'key')

    def test_no_implicit_default(self):
        for value in ('', 'auto', 'LOCAL'):
            with self.assertRaises(ConfigurationError):
                backend_from_env(dict(EXECUTION_BACKEND=value))

    def test_production_refuses_unisolated_backends(self):
        for name in ('local', 'mock', 'docker'):
            with self.assertRaises(ConfigurationError, msg=name):
                backend_from_env(dict(EXECUTION_BACKEND=name, FTM_ENVIRONMENT='production'))
        self.assertTrue(backend_from_env(dict(CLOUDRUN, FTM_ENVIRONMENT='production')).isolated)

    def test_cloudrun_requires_complete_configuration(self):
        for broken in (dict(CLOUDRUN, CLOUD_RUN_URL=''), dict(CLOUDRUN, CLOUD_RUN_URL='http://runner'),
                       dict(CLOUDRUN, GOOGLE_APPLICATION_CREDENTIALS=''),
                       dict(CLOUDRUN, GCP_AUTH_MODE='wif'), dict(CLOUDRUN, GCP_AUTH_MODE='oauth')):
            with self.assertRaises(ConfigurationError, msg=broken):
                backend_from_env(broken)
        wif = backend_from_env(dict(CLOUDRUN, GCP_AUTH_MODE='wif', GOOGLE_APPLICATION_CREDENTIALS='',
                                    GCP_INVOKER_SERVICE_ACCOUNT='inv@p.iam.gserviceaccount.com',
                                    CLOUD_RUN_AUDIENCE='https://audience.example'))
        self.assertEqual((wif.tokens.mode, wif.tokens.audience), ('wif', 'https://audience.example'))

    def test_docker_is_development_only(self):
        from ft_moulinette_runners.docker import DockerRunner
        backend = backend_from_env(dict(EXECUTION_BACKEND='docker', FTM_DOCKER_IMAGE='sandbox-c:test'))
        self.assertIsInstance(backend, DockerRunner)
        self.assertFalse(backend.isolated)
        self.assertEqual(backend.image, 'sandbox-c:test')


class SettingsTests(unittest.TestCase):
    def test_kill_switch(self):
        self.assertTrue(executions_enabled({}))
        for value in ('1', 'true', 'YES', 'on'):
            self.assertFalse(executions_enabled(dict(FTM_EXECUTIONS_DISABLED=value)))

    def test_limits(self):
        self.assertEqual(limits_from_env(dict(EXECUTION_TIMEOUT='45')).submission_timeout, 45)
        self.assertEqual(limits_from_env(dict(FTM_LIMIT_MAX_FILES='50')).max_files, 50)
        for broken in (dict(FTM_LIMIT_MAX_FILES='beaucoup'), dict(FTM_LIMIT_MAX_FILES='0'),
                       dict(EXECUTION_TIMEOUT='500')):
            with self.assertRaises(ConfigurationError, msg=broken):
                limits_from_env(broken)


if __name__ == '__main__':
    unittest.main()
