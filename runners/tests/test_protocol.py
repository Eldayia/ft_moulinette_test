import copy
import unittest

from ft_moulinette_runners.base import ExecutionError, ExecutionResult, Options, Submission
from ft_moulinette_runners.limits import Limits
from ft_moulinette_runners.protocol import (analyzers, build_metadata, build_response, classify, parse_metadata,
                                            parse_response, relativize_report, validate_report)

from helpers import report, row

ID = 'a' * 32


def metadata(**changes):
    data = dict(protocol=1, submission_id=ID, project='libft', functions=[], target=None, tests_version='0.3.0',
                options=dict(norm=True, memory=False, build=True, iterations=10, seed=1))
    data.update(changes)
    return data


class MetadataTests(unittest.TestCase):
    def test_round_trip(self):
        submission = Submission('libft', archive=b'x', submission_id=ID, options=Options(memory=False, iterations=10, seed=1),
                                tests_version='0.3.0')
        fields, limits = parse_metadata(build_metadata(submission), Limits())
        self.assertEqual(fields['options'], submission.options)
        self.assertEqual(limits, Limits())

    def test_rejections(self):
        cases = {
            'unknown field': metadata(command='rm -rf /'),
            'bad id': metadata(submission_id='../x'),
            'bad project': metadata(project='minishell'),
            'unknown function': metadata(functions=['system']),
            'bad option': metadata(options=dict(norm='yes')),
            'unknown option': metadata(options=dict(cflags='-O0')),
            'seed range': metadata(options=dict(seed=-1)),
            'bad target': metadata(target='../etc/passwd'),
            'target not source': metadata(target='Makefile'),
            'bad tests_version': metadata(tests_version='1.0; rm'),
            'unknown limit': metadata(limits=dict(max_cpu=1)),
            'not an object': [],
        }
        for name, data in cases.items():
            with self.assertRaises(ExecutionError, msg=name) as raised:
                parse_metadata(data, Limits())
            self.assertEqual(raised.exception.category, 'user', name)

    def test_protocol_version_and_unsupported_selection(self):
        with self.assertRaises(ExecutionError) as raised:
            parse_metadata(metadata(protocol=2), Limits())
        self.assertEqual(raised.exception.code, 'unsupported_protocol')
        with self.assertRaises(ExecutionError) as raised:
            parse_metadata(metadata(functions=['strlen']), Limits())
        self.assertEqual(raised.exception.code, 'unsupported')

    def test_requested_limits_never_exceed_service_maxima(self):
        _, limits = parse_metadata(metadata(limits=dict(max_files=10, submission_timeout=10_000)), Limits())
        self.assertEqual(limits.max_files, 10)
        self.assertEqual(limits.submission_timeout, Limits().submission_timeout)


class ReportValidationTests(unittest.TestCase):
    def test_valid_report(self):
        data = report([row('functional:strlen', 'pass'), row('norm', 'fail')])
        self.assertIs(validate_report(data, 'libft'), data)

    def test_forged_or_malformed_reports(self):
        good = report([row('functional:strlen', 'fail')])
        broken = []
        for mutate in (
            lambda r: r['summary'].update(fail=0),               # résumé incohérent
            lambda r: r['summary'].update(pass_=3),
            lambda r: r.update(module='printf-1.1'),             # autre projet
            lambda r: r.update(schema_version=2),
            lambda r: r.update(extra=1),
            lambda r: r['results'][0].update(status='ok'),
            lambda r: r['results'][0].update(line=-1),
            lambda r: r['results'][0].update(line=True),
            lambda r: r['results'][0].update(script='<script>'),
            lambda r: r['results'][0].pop('message'),
            lambda r: r['results'][0].update(check='a\nb'),
            lambda r: r['results'][0].update(diagnostics=[dict(file='x', line=1)]),
            lambda r: r['results'][0].update(message='x' * 200_000),
        ):
            candidate = copy.deepcopy(good)
            mutate(candidate)
            broken.append(candidate)
        for candidate in broken:
            with self.assertRaises(ValueError, msg=candidate):
                validate_report(candidate, 'libft')

    def test_engine_diagnostics_with_message(self):
        data = report([dict(row('compile', 'fail'), raw_message='brut', diagnostics=[
            dict(file='/submission/ft_strlen.c', line=2, column=45, message='Le compilateur attend…')])])
        self.assertIs(validate_report(data, 'libft'), data)
        data['results'][0]['diagnostics'][0]['message'] = 'x' * 200_000
        with self.assertRaises(ValueError):
            validate_report(data, 'libft')

    def test_size_limit(self):
        data = report([row(f'functional:f{i}', 'pass', message='x' * 1000) for i in range(50)])
        with self.assertRaises(ValueError):
            validate_report(data, 'libft', Limits(max_report_bytes=10_000))

    def test_relativize(self):
        data = report([dict(row('compile', 'fail'), diagnostics=[dict(file='/submission/src/a.c', line=2, column=3)]),
                       row('norm', 'pass', file='/usr/include/stdio.h')])
        relativize_report(data, '/submission')
        self.assertEqual(data['results'][0]['file'], 'ft_strlen.c')
        self.assertEqual(data['results'][0]['diagnostics'][0]['file'], 'src/a.c')
        self.assertEqual(data['results'][1]['file'], '/usr/include/stdio.h')


class ClassifyTests(unittest.TestCase):
    def outcome(self, *rows):
        return classify(report(list(rows)))

    def test_priorities(self):
        self.assertEqual(self.outcome(row('functional:strlen', 'pass')), 'success')
        self.assertEqual(self.outcome(row('compile', 'fail'), row('functional:x', 'fail')), 'compilation_error')
        self.assertEqual(self.outcome(row('functional', 'blocked')), 'compilation_error')
        self.assertEqual(self.outcome(row('archive:link', 'fail')), 'compilation_error')
        self.assertEqual(self.outcome(row('functional:x', 'fail'), row('memory:x', 'fail')), 'test_failure')
        self.assertEqual(self.outcome(row('presence', 'missing')), 'test_failure')
        self.assertEqual(self.outcome(row('memory:x', 'fail'), row('norm', 'fail')), 'memory_error')
        self.assertEqual(self.outcome(row('norm', 'fail')), 'norm_error')

    def test_unavailable_analyzer_is_never_a_success(self):
        self.assertEqual(self.outcome(row('functional:x', 'pass'), row('memory:tool', 'unavailable')), 'unsupported')

    def test_analyzers(self):
        data = report([row('norm', 'pass'), row('memory:tool', 'unavailable'), row('functional:x', 'pass'),
                       row('allocation:1', 'pass'), row('compile', 'pass')])
        used, unavailable = analyzers(data, Options())
        self.assertEqual(used, ['compiler', 'functional', 'malloc-failure', 'norminette'])
        self.assertEqual(unavailable, ['valgrind'])


class ResponseTests(unittest.TestCase):
    def response(self, outcome, data=None, **changes):
        result = ExecutionResult(ID, outcome, data, dict(backend='cloudrun'))
        payload = build_response(result)
        payload.update(changes)
        return payload

    def test_valid_response(self):
        data = report([row('functional:strlen', 'fail', file='ft_strlen.c')])
        result = parse_response(self.response('test_failure', data), ID, 'libft')
        self.assertEqual(result.outcome, 'test_failure')

    def test_outcome_must_match_the_report(self):
        failing = report([row('functional:strlen', 'fail')])
        with self.assertRaises(ValueError):
            parse_response(self.response('success', failing), ID, 'libft')

    def test_identity_and_shape(self):
        data = report([row('functional:strlen', 'pass')])
        with self.assertRaises(ValueError):
            parse_response(self.response('success', data), 'b' * 32, 'libft')
        with self.assertRaises(ValueError):
            parse_response(self.response('success', data, injected=True), ID, 'libft')
        with self.assertRaises(ValueError):
            parse_response(self.response('success', None), ID, 'libft')  # succès sans rapport
        with self.assertRaises(ValueError):
            parse_response(self.response('success', data, error=dict(category='admin', code='x', message='y')), ID, 'libft')

    def test_infrastructure_outcome_without_report(self):
        payload = self.response('sandbox_unavailable', None,
                                error=dict(category='infrastructure', code='sandbox_unavailable', message='m'))
        result = parse_response(payload, ID, 'libft')
        self.assertTrue(result.is_infrastructure_failure)
        self.assertEqual(result.error.category, 'infrastructure')


if __name__ == '__main__':
    unittest.main()
