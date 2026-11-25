#!/usr/bin/env bash
# Construit et vérifie les images sandbox-c et runner-api ; les publie sur Artifact Registry avec --push.
#
# Usage : deploy/gcp/build.sh [--push] [--skip-tests] [--tag TAG] [--yes]
# Sans --push, rien ne quitte la machine. Avec --push, les digests sont écrits dans deploy/gcp/images.env.
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"
PUSH=0 SKIP_TESTS=0 TAG=""
while [ $# -gt 0 ]; do
    case "$1" in
        --push) PUSH=1 ;;
        --skip-tests) SKIP_TESTS=1 ;;
        --tag) shift; TAG="${1:-}" ;;
        --yes) ASSUME_YES=1 ;;
        *) die "option inconnue : $1" ;;
    esac
    shift
done
require docker python3 curl
cd "$REPO_ROOT"

if [ -z "$TAG" ]; then
    TAG=$(git rev-parse --short=12 HEAD 2>/dev/null || date +%Y%m%d%H%M%S)
    git diff --quiet 2>/dev/null || TAG="${TAG}-dirty"
fi
[[ "$TAG" =~ ^[A-Za-z0-9._-]+$ ]] || die "tag invalide : $TAG"
[ "$PUSH" = 1 ] && [[ "$TAG" == *-dirty ]] && die "refus de publier des modifications non commitées (tag $TAG)."

# Les Dockerfiles n'exigent pas BuildKit : constructeur classique si buildx est absent.
if docker buildx version >/dev/null 2>&1; then export DOCKER_BUILDKIT=1; else export DOCKER_BUILDKIT=0; fi

if [ "$SKIP_TESTS" = 0 ]; then
    info "Tests du paquet runners"
    (cd runners && python3 -m unittest discover -s tests)
    if [ -x workers/cloudrun/.venv/bin/python ]; then
        info "Tests du service runner-api"
        (cd workers/cloudrun && .venv/bin/python -m unittest discover -s tests >/dev/null)
    else
        info "Tests runner-api ignorés : créer workers/cloudrun/.venv (voir workers/cloudrun/README.md)."
    fi
fi

SANDBOX_LOCAL="ft-moulinette/sandbox-c:$TAG"
RUNNER_LOCAL="ft-moulinette/runner-api:$TAG"
info "Construction de $SANDBOX_LOCAL"
docker build -f docker/cloudrun/Dockerfile.sandbox -t "$SANDBOX_LOCAL" .
if [ "$SKIP_TESTS" = 0 ]; then
    info "Tests du moteur dans sandbox-c (sans réseau, utilisateur non root)"
    docker run --rm --network none -v "$REPO_ROOT/cli/tests:/opt/ft-moulinette/tests:ro" -w /opt/ft-moulinette \
        --entrypoint python3 "$SANDBOX_LOCAL" -B -m unittest discover -s tests -p 'test_[!i]*.py'
fi
info "Construction de $RUNNER_LOCAL"
docker build -f docker/cloudrun/Dockerfile.runner --build-arg SANDBOX_IMAGE="$SANDBOX_LOCAL" -t "$RUNNER_LOCAL" .

info "Vérification de l'échec fermé du runner sans CLI sandbox"
container=$(docker run -d --rm -p 127.0.0.1::8080 "$RUNNER_LOCAL")
trap 'docker stop "$container" >/dev/null 2>&1 || true' EXIT
port=$(docker port "$container" 8080/tcp | head -1 | sed 's/.*://')
for _ in $(seq 60); do curl -fs "http://127.0.0.1:$port/healthz" >/dev/null && break; sleep 0.5; done
status=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/readyz")
[ "$status" = 503 ] || die "/readyz aurait dû répondre 503 sans CLI sandbox (reçu : $status)."
docker stop "$container" >/dev/null; trap - EXIT

if [ "$PUSH" = 0 ]; then
    info "Images locales prêtes : $SANDBOX_LOCAL, $RUNNER_LOCAL (rien n'a été publié)."
    exit 0
fi

load_config
confirm "Publier les images sur $REGISTRY (stockage facturé) ?"
docker tag "$SANDBOX_LOCAL" "$REGISTRY/sandbox-c:$TAG"
docker tag "$RUNNER_LOCAL" "$REGISTRY/runner-api:$TAG"
info "Si l'envoi est refusé : gcloud auth configure-docker ${REGION}-docker.pkg.dev"
docker push "$REGISTRY/sandbox-c:$TAG"
docker push "$REGISTRY/runner-api:$TAG"
sandbox_digest=$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$REGISTRY/sandbox-c:$TAG" | grep "^$REGISTRY/sandbox-c@" | head -1)
runner_digest=$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$REGISTRY/runner-api:$TAG" | grep "^$REGISTRY/runner-api@" | head -1)
[ -n "$runner_digest" ] || die "digest de runner-api introuvable après publication."
cat > "$GCP_DIR/images.env" <<EOF
# Généré par build.sh le $(date -u +%Y-%m-%dT%H:%M:%SZ) — tag $TAG
SANDBOX_IMAGE=$sandbox_digest
RUNNER_IMAGE=$runner_digest
EOF
info "Digests enregistrés dans deploy/gcp/images.env :"
cat "$GCP_DIR/images.env"
info "Étape suivante : deploy/gcp/deploy.sh"
