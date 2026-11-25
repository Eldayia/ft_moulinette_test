import io
import stat
import warnings
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / 'cli'
if str(CLI) not in sys.path:  # liste des fonctions Libft pour le protocole
    sys.path.append(str(CLI))

HEADER = '#include <stddef.h>\nsize_t ft_strlen(const char *s);\n'
STRLEN_OK = '#include "libft.h"\nsize_t ft_strlen(const char *s)\n{\n\tsize_t i = 0;\n\n\twhile (s[i])\n\t\ti++;\n\treturn (i);\n}\n'
STRLEN_WRONG = '#include "libft.h"\nsize_t ft_strlen(const char *s){size_t i=0;while(s[i])i++;return i+1;}\n'
STRLEN_BROKEN = '#include "libft.h"\nsize_t ft_strlen(const char *s){ return s + ; }\n'


def raw_zip(entries):
    """Archive construite à la main, pour fabriquer des entrées hostiles. entries : [(nom, octets, mode)]."""
    buffer = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        warnings.simplefilter('ignore', UserWarning)  # doublons volontaires
        for name, content, mode in entries:
            info = zipfile.ZipInfo(name, (2000, 1, 1, 0, 0, 0))
            info.external_attr = (mode if mode is not None else (stat.S_IFREG | 0o644)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return buffer.getvalue()


def report(rows, module='libft-1.3'):
    from collections import Counter
    return dict(schema_version=1, module=module, summary=dict(Counter(r['status'] for r in rows)), results=rows)


def row(check, status, file='/submission/ft_strlen.c', message='m'):
    return dict(file=file, line=1, column=1, check=check, status=status, message=message)
