import unittest
from ft_moulinette.explain import explain
from ft_moulinette.cases import CASES, PRELUDE, LSTMAP_FAILURE

class FailureMessageTests(unittest.TestCase):
    def test_no_opaque_harness_assertions(self):
        for name, source in {**CASES, 'helpers': PRELUDE, 'malloc': LSTMAP_FAILURE}.items():
            with self.subTest(name=name):
                self.assertNotRegex(source, r'\bassert\s*\(')

    def test_external_reports(self):
        cases = [
            ('archive:link', "undefined reference to `ft_strlen'", ('libft.a', 'ft_strlen')),
            ('memory', 'Invalid read of size 1\n at 0x1: ft_strlen (ft_strlen.c:6)\n Address is 0 bytes after a block of size 3', ('Lecture','indice 3','ft_strlen.c:6')),
            ('archive:allocation:2','8 bytes in 1 blocks are definitely lost', ('Fuite','8 octet')),
            ('commands','make: *** No rule to make target all', ('make all','No rule')),
            ('prototype','test.c:2: error: conflicting types', ('libft.h','paramètres')),
        ]
        for check, raw, words in cases:
            with self.subTest(check=check):
                message=explain(check,'fail',raw,[])
                for word in words: self.assertIn(word,message)

    def test_allocation_site_is_not_the_invalid_read_site(self):
        raw = ("Invalid read of size 1\n"
               "==1== at 0x1: compare_text (test.c:30)\n"
               "==1== Address 0x123 is 0 bytes after a block of size 3 alloc'd\n"
               "==1== at 0x2: malloc (malloc.c:10)\n"
               "==1== by 0x3: ft_substr (ft_substr.c:23)\n")
        message = explain('memory', 'fail', raw, [])
        self.assertIn('Lecture', message)
        self.assertNotIn('ft_substr.c:23', message)
