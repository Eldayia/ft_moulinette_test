"""MockRunner : résultats programmés, pour les tests et le développement d'interfaces.

N'exécute jamais rien. Interdit en production (config.py). Ses résultats ne valident rien.
"""
import time

from .base import ExecutionBackend, ExecutionResult, Health

DEFAULT_REPORT = dict(schema_version=1, module='libft-1.3', summary={'pass': 1}, results=[
    dict(file='ft_strlen.c', line=1, column=1, check='functional:strlen', status='pass', message='Mock')])


class MockRunner(ExecutionBackend):
    name = 'mock'
    isolated = False

    def __init__(self, outcome='success', report=None, error=None, delay=0.0, available=True, events=()):
        self.outcome = outcome
        self.report = DEFAULT_REPORT if report is None and outcome == 'success' else report
        self.error = error
        self.delay = delay
        self.available = available
        self.events = list(events)
        self.submissions = []
        self.cancelled = set()

    def capabilities(self):
        return dict(backend=self.name, isolated=False, projects=['libft', 'printf'], analyzers=[],
                    sources=['archive', 'local_path'], function_selection=False, cancel=True)

    def check(self):
        return Health(self.available, 'Mock' if self.available else 'Mock indisponible')

    def execute(self, submission, on_event=None):
        self.submissions.append(submission)
        for event in self.events:
            if on_event:
                on_event(event)
        if self.delay:
            time.sleep(self.delay)
        if submission.submission_id in self.cancelled:
            return ExecutionResult(submission.submission_id, 'cancelled', None, dict(backend=self.name))
        return ExecutionResult(submission.submission_id, self.outcome, self.report,
                               dict(backend=self.name, mock=True), self.error)

    def cancel(self, submission_id):
        self.cancelled.add(submission_id)
        return True
