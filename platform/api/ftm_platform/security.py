"""Mots de passe (scrypt, bibliothèque standard), jetons de session et jetons personnels."""
import hashlib
import hmac
import secrets

SCRYPT = dict(n=2 ** 15, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)
TOKEN_PREFIX = 'ftm_'
MIN_PASSWORD = 12


def hash_password(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise ValueError(f'Mot de passe : {MIN_PASSWORD} caractères au minimum.')
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return f'scrypt${SCRYPT["n"]}${SCRYPT["r"]}${SCRYPT["p"]}${salt.hex()}${digest.hex()}'


def verify_password(password, stored):
    try:
        scheme, n, r, p, salt, digest = stored.split('$')
        if scheme != 'scrypt':
            return False
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                                   maxmem=SCRYPT['maxmem'], dklen=len(bytes.fromhex(digest)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest)


# Empreinte fictive, pour que la vérification d'un identifiant inconnu prenne le même temps.
DUMMY_HASH = hash_password('x' * MIN_PASSWORD)


def new_token(kind):
    """Jeton aléatoire (256 bits) : seule son empreinte SHA-256 est stockée."""
    token = f'{TOKEN_PREFIX}{kind}_{secrets.token_urlsafe(32)}'
    return token, token_hash(token)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def generate_password():
    return secrets.token_urlsafe(18)
