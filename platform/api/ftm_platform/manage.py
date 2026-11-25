"""Commandes d'administration : migrations, comptes, maintenance.

  python -m ftm_platform.manage migrate
  python -m ftm_platform.manage create-user LOGIN [--admin]     (mot de passe généré, affiché une fois)
  python -m ftm_platform.manage set-password LOGIN              (lu sur l'entrée standard)
  python -m ftm_platform.manage disable-user LOGIN
  python -m ftm_platform.manage reap                            (soumissions bloquées → échec, jamais relancées)
"""
import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import delete, select

from .db import session_factory, transaction
from .models import Session, User
from .security import generate_password, hash_password

MIGRATIONS = Path(__file__).resolve().parent / 'migrations'


def alembic_config(url):
    from alembic.config import Config
    config = Config()
    config.set_main_option('script_location', str(MIGRATIONS))
    config.set_main_option('sqlalchemy.url', url.replace('%', '%%'))
    return config


def migrate(url, revision='head'):
    from alembic import command
    command.upgrade(alembic_config(url), revision)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='ftm_platform.manage')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('migrate')
    create = commands.add_parser('create-user')
    create.add_argument('login')
    create.add_argument('--admin', action='store_true')
    commands.add_parser('set-password').add_argument('login')
    commands.add_parser('disable-user').add_argument('login')
    commands.add_parser('reap')
    args = parser.parse_args(argv)
    from .settings import database_url
    url = database_url()
    if not url:
        parser.error('DATABASE_URL manquante')
    if args.command == 'migrate':
        migrate(url)
        print('Base à jour.')
        return 0
    if args.command == 'reap':
        from .tasks import reap_stale
        print('Soumissions marquées en échec :', ', '.join(reap_stale()) or 'aucune')
        return 0
    factory = session_factory(url)
    with transaction(factory) as session:
        user = session.scalar(select(User).where(User.login == args.login))
        if args.command == 'create-user':
            if user is not None:
                parser.error('identifiant déjà utilisé')
            password = generate_password()
            session.add(User(login=args.login, password_hash=hash_password(password), is_admin=args.admin))
            print(f'Compte {args.login} créé{" (administrateur)" if args.admin else ""}.')
            print(f'Mot de passe initial (affiché une seule fois) : {password}')
            return 0
        if user is None:
            parser.error('identifiant inconnu')
        if args.command == 'set-password':
            password = sys.stdin.readline().rstrip('\n')
            try:
                user.password_hash = hash_password(password)
            except ValueError as exc:
                parser.error(str(exc))
        else:
            user.disabled = True
        session.execute(delete(Session).where(Session.user_id == user.id))
        print('Fait ; sessions existantes fermées.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
