import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from ft_moulinette_runners.base import ExecutionError
from ft_moulinette_runners.limits import Limits
from ft_moulinette_runners.workspace import (archive_digest, build_archive, extract_archive, pack_directory,
                                             read_archive)

from helpers import raw_zip


class WorkspaceCase(unittest.TestCase):
    def temp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def rejected(self, data, code, limits=None):
        with self.assertRaises(ExecutionError) as raised:
            read_archive(data, limits)
        self.assertEqual(raised.exception.category, 'user')
        self.assertEqual(raised.exception.code, code, raised.exception.message)
        return raised.exception


class BuildTests(WorkspaceCase):
    def test_round_trip_preserves_relative_paths(self):
        files = {'Makefile': b'all:\n', 'libft.h': b'h', 'src/ft_a.c': b'a', 'README.md': b'# r'}
        data = build_archive(files)
        self.assertEqual(read_archive(data), files)
        destination = self.temp() / 'out'
        destination.mkdir()
        self.assertEqual(extract_archive(data, destination), sorted(files))
        self.assertEqual((destination / 'src' / 'ft_a.c').read_bytes(), b'a')
        self.assertEqual(stat.S_IMODE((destination / 'libft.h').stat().st_mode), 0o644)

    def test_archive_is_deterministic(self):
        files = {'b.c': b'2', 'a.c': b'1'}
        self.assertEqual(archive_digest(build_archive(files)), archive_digest(build_archive(dict(reversed(files.items())))))

    def test_pasted_code_names_are_validated(self):
        for name in ('../evil.c', '/etc/x.c', 'a\\b.c', 'a/./b.c', 'a//b.c', 'run.sh', 'inner.zip', '.git/x.c', 'x\x00.c'):
            with self.assertRaises(ExecutionError, msg=name):
                build_archive({name: b'x'})

    def test_limits_apply_when_building(self):
        limits = Limits(max_files=2, max_file_bytes=10, max_uncompressed_bytes=15)
        with self.assertRaises(ExecutionError):
            build_archive({'a.c': b'x' * 11}, limits)
        with self.assertRaises(ExecutionError):
            build_archive({'a.c': b'1', 'b.c': b'2', 'c.c': b'3'}, limits)
        with self.assertRaises(ExecutionError):
            build_archive({'a.c': b'x' * 10, 'b.c': b'y' * 10}, limits)
        with self.assertRaises(ExecutionError):
            build_archive({})
        with self.assertRaises(ExecutionError):  # pas d'écrasement silencieux
            build_archive({'caf\u00e9.c': b'1', 'cafe\u0301.c': b'2'})


class PackDirectoryTests(WorkspaceCase):
    def test_skips_links_special_and_build_files(self):
        root = self.temp()
        (root / 'src').mkdir()
        (root / 'src' / 'ft_a.c').write_text('a')
        (root / 'libft.h').write_text('h')
        (root / 'Makefile').write_text('all:\n')
        (root / 'ft_a.o').write_bytes(b'\x7fELF')
        (root / 'libft.a').write_bytes(b'!<arch>')
        (root / '.git').mkdir()
        (root / '.git' / 'config.c').write_text('secret')
        outside = self.temp() / 'secret.c'
        outside.write_text('hors projet')
        (root / 'lien.c').symlink_to(outside)
        (root / 'dossier-lien').symlink_to(outside.parent, target_is_directory=True)
        os.mkfifo(root / 'tube.c')
        data, skipped = pack_directory(root)
        self.assertEqual(sorted(read_archive(data)), ['Makefile', 'libft.h', 'src/ft_a.c'])
        self.assertIn('lien.c', skipped)
        self.assertIn('tube.c', skipped)
        self.assertIn('ft_a.o', skipped)


class HostileArchiveTests(WorkspaceCase):
    def test_zip_slip_and_absolute_paths(self):
        self.rejected(raw_zip([('../../etc/evil.c', b'x', None)]), 'invalid_path')
        self.rejected(raw_zip([('/tmp/evil.c', b'x', None)]), 'invalid_path')
        self.rejected(raw_zip([('src/../../evil.c', b'x', None)]), 'invalid_path')
        self.rejected(raw_zip([('C:/evil.c', b'x', None)]), 'invalid_path')

    def test_symlinks_and_special_files(self):
        self.rejected(raw_zip([('lien.c', b'/etc/passwd', stat.S_IFLNK | 0o777)]), 'invalid_archive')
        self.rejected(raw_zip([('tube.c', b'', stat.S_IFIFO | 0o644)]), 'invalid_archive')
        self.rejected(raw_zip([('dev.c', b'', stat.S_IFCHR | 0o644)]), 'invalid_archive')

    def test_unexpected_and_nested_archives(self):
        self.rejected(raw_zip([('inner.zip', b'PK\x03\x04', None)]), 'unexpected_file')
        self.rejected(raw_zip([('exploit.sh', b'#!/bin/sh', None)]), 'unexpected_file')
        self.rejected(raw_zip([('a.out', b'\x7fELF', None)]), 'unexpected_file')

    def test_duplicates_after_normalization(self):
        self.rejected(raw_zip([('caf\u00e9.c', b'1', None), ('cafe\u0301.c', b'2', None)]), 'duplicate_path')
        self.rejected(raw_zip([('Ft_a.c', b'1', None), ('ft_a.c', b'2', None)]), 'duplicate_path')
        self.rejected(raw_zip([('a.c', b'1', None), ('a.c', b'2', None)]), 'duplicate_path')
        self.rejected(raw_zip([('x.h', b'1', None), ('x.h/y.c', b'2', None)]), 'duplicate_path')

    def test_zip_bomb_is_bounded_while_decompressing(self):
        limits = Limits(max_file_bytes=1024 * 1024, max_uncompressed_bytes=2 * 1024 * 1024)
        bomb = raw_zip([(f'f{i}.c', b'\0' * (900 * 1024), None) for i in range(4)])
        self.assertLess(len(bomb), 64 * 1024)
        self.rejected(bomb, 'too_large', limits)
        self.rejected(raw_zip([('big.c', b'\0' * (3 * 1024 * 1024), None)]), 'file_too_large')

    def test_encrypted_entry(self):
        data = bytearray(raw_zip([('a.c', b'x', None)]))
        # Bit 0 des drapeaux généraux = chiffré, dans l'en-tête local et le répertoire central.
        for signature, offset in ((b'PK\x03\x04', 6), (b'PK\x01\x02', 8)):
            position = data.find(signature)
            data[position + offset] |= 1
        self.rejected(bytes(data), 'invalid_archive')

    def test_garbage_and_oversized_uploads(self):
        self.rejected(b'not a zip', 'invalid_archive')
        self.rejected(b'x' * 100, 'too_large', Limits(max_upload_bytes=50, max_file_bytes=10, max_uncompressed_bytes=20))

    def test_too_many_entries_and_depth(self):
        self.rejected(raw_zip([(f'f{i}.c', b'x', None) for i in range(201)]), 'too_many_files')
        self.rejected(raw_zip([('/'.join(['d'] * 20) + '/a.c', b'x', None)]), 'invalid_path')

    def test_directory_entries_are_checked_too(self):
        for name in ('../escape/', 'src/../../escape/', '.git/'):
            self.rejected(raw_zip([('src/a.c', b'x', None), (name, b'', stat.S_IFDIR | 0o755)]), 'invalid_path')


class ExtractionTests(WorkspaceCase):
    def test_destination_must_be_a_fresh_empty_directory(self):
        data = build_archive({'a.c': b'x'})
        busy = self.temp()
        (busy / 'other.c').write_text('autre soumission')
        with self.assertRaises(ValueError):
            extract_archive(data, busy)
        link = self.temp() / 'lien'
        link.symlink_to(self.temp(), target_is_directory=True)
        with self.assertRaises(ValueError):
            extract_archive(data, link)


if __name__ == '__main__':
    unittest.main()
