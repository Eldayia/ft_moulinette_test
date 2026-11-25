import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from render import render  # noqa: E402

DIGEST = 'europe-west1-docker.pkg.dev/projet/ft-moulinette/runner-api@sha256:' + 'a' * 64
BASE = dict(SERVICE_NAME='ft-moulinette-runner', MIN_INSTANCES='0', MAX_INSTANCES='2', RUNTIME_SA='rt@p.iam.gserviceaccount.com',
            REQUEST_TIMEOUT='120', RUNNER_IMAGE=DIGEST, CPU='1', MEMORY='2Gi', SUBMISSION_TIMEOUT='60',
            EXECUTIONS_DISABLED='', WORKSPACE_SIZE='256Mi')


class RenderTests(unittest.TestCase):
    template = (HERE / 'service.yaml.template').read_text()

    def test_complete_rendering(self):
        text = render(self.template, BASE)
        self.assertNotIn('${', text)
        self.assertIn('sandboxLauncher: true', text)
        self.assertIn(f'image: {DIGEST}', text)
        self.assertIn('containerConcurrency: 1', text)
        manifest = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))
        self.assertNotIn('allUsers', manifest)
        self.assertNotIn('allow-unauthenticated', manifest)

    def test_missing_and_unsafe_values(self):
        for name in ('SERVICE_NAME', 'RUNNER_IMAGE', 'MAX_INSTANCES'):
            with self.assertRaises(ValueError, msg=name):
                render(self.template, {k: v for k, v in BASE.items() if k != name})
        for value in ('2\n    sandboxLauncher: false', 'x: y', '"quoted"', '${OTHER}'):
            with self.assertRaises(ValueError, msg=value):
                render(self.template, dict(BASE, MAX_INSTANCES=value))

    def test_image_must_be_pinned_by_digest(self):
        with self.assertRaises(ValueError):
            render(self.template, dict(BASE, RUNNER_IMAGE='europe-west1-docker.pkg.dev/p/r/runner-api:latest'))
        self.assertIn(':latest', render(self.template, dict(BASE, RUNNER_IMAGE='registry/runner-api:latest'), allow_tag=True))


if __name__ == '__main__':
    unittest.main()
