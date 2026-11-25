"""Extract actionable source locations without confusing harness assertions."""
import re
from pathlib import Path

COMPILER = re.compile(r'^(.*?):(\d+):(\d+):\s*(?:fatal error|error|warning):\s*(.*)$', re.M)
NORM = re.compile(r'Error:\s*(\w+)\s*\(line:\s*(\d+),\s*col:\s*(\d+)\):\s*(.*)')


def locations(message, check, file, root, project):
    if check == 'norm':
        return [dict(file=str(root/file), line=int(line), column=int(col), message=f'{kind}: {text}')
                for kind,line,col,text in NORM.findall(message)]
    if check != 'compile':
        return []
    found=[]
    for path,line,col,text in COMPILER.findall(message):
        try:
            relative=Path(path).relative_to(project)
        except ValueError:
            continue
        found.append(dict(file=str(root/relative),line=int(line),column=int(col),message=text))
    return found
