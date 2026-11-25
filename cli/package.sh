#!/bin/sh
# Crée une archive autonome à envoyer, sans journaux ni caches locaux.
set -eu
SOURCE_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$SOURCE_DIR/dist"
tar -czf "$SOURCE_DIR/dist/ft-moulinette.tar.gz" \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' \
    -C "$SOURCE_DIR" README.md pyproject.toml install.sh package.sh bin ft_moulinette integrations
printf '%s\n' "Archive prête à partager : $SOURCE_DIR/dist/ft-moulinette.tar.gz"
