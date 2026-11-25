#!/usr/bin/env python3
"""Build against an installed CLion SDK, without downloading Gradle."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

p=argparse.ArgumentParser()
p.add_argument('--clion',type=Path,default=Path('/opt/clion'))
args=p.parse_args()
base=Path(__file__).resolve().parent
info=json.loads((args.clion/'product-info.json').read_text())
with tempfile.TemporaryDirectory() as temp:
    classes=Path(temp)
    jars=list((args.clion/'lib').rglob('*.jar'))
    subprocess.run([str(args.clion/'jbr/bin/javac'),'-encoding','UTF-8','-cp',os.pathsep.join(map(str,jars)),'-d',str(classes),*map(str,(base/'src/main/java').rglob('*.java'))],check=True)
    descriptor=(base/'src/main/resources/META-INF/plugin.xml').read_text()
    descriptor=descriptor.replace('<name>', '<version>0.3.0</version>\n  <idea-version since-build="'+info['buildNumber'].split('.')[0]+'"/>\n  <name>',1)
    jar=classes/'ft-moulinette.jar'
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as output:
        for file in classes.rglob('*.class'): output.write(file,file.relative_to(classes))
        output.writestr('META-INF/plugin.xml',descriptor)
    destination=base/'build/distributions/ft-moulinette-clion-0.3.0.zip'
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as output:
        output.write(jar,'ft-moulinette/lib/ft-moulinette.jar')
    print(destination)
