# Fonctions communes aux scripts de déploiement GCP. Source : . "$(dirname "$0")/common.sh"
# shellcheck shell=bash

GCP_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(CDPATH='' cd -- "$GCP_DIR/../.." && pwd)
ASSUME_YES=${ASSUME_YES:-0}
export GCP_DIR REPO_ROOT ASSUME_YES

die() { printf 'Erreur : %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*"; }

load_config() {
    if [ -f "$GCP_DIR/config.env" ]; then
        # shellcheck disable=SC1091
        . "$GCP_DIR/config.env"
    fi
    : "${REGION:=europe-west1}" "${REPOSITORY:=ft-moulinette}" "${SERVICE_NAME:=ft-moulinette-runner}"
    : "${RUNTIME_SA_NAME:=ft-moulinette-runtime}" "${INVOKER_SA_NAME:=ft-moulinette-invoker}"
    : "${MIN_INSTANCES:=0}" "${MAX_INSTANCES:=2}" "${CPU:=1}" "${MEMORY:=2Gi}"
    : "${REQUEST_TIMEOUT:=120}" "${SUBMISSION_TIMEOUT:=60}" "${WORKSPACE_SIZE:=256Mi}" "${EXECUTIONS_DISABLED:=}"
    [ -n "${PROJECT_ID:-}" ] || die "PROJECT_ID manquant (deploy/gcp/config.env ou variable d'environnement)."
    RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
    INVOKER_SA="${INVOKER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
    REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}"
    export PROJECT_ID REGION REPOSITORY SERVICE_NAME RUNTIME_SA INVOKER_SA REGISTRY MIN_INSTANCES MAX_INSTANCES \
        CPU MEMORY REQUEST_TIMEOUT SUBMISSION_TIMEOUT WORKSPACE_SIZE EXECUTIONS_DISABLED
}

require() {
    for tool in "$@"; do
        command -v "$tool" >/dev/null 2>&1 || die "outil requis absent : $tool"
    done
}

confirm() {
    # Toute action qui crée ou modifie des ressources GCP demande une confirmation (ou --yes).
    [ "${ASSUME_YES:-0}" = 1 ] && return 0
    printf '%s [o/N] ' "$1"
    read -r answer
    case "$answer" in o|O|oui|y|Y|yes) return 0 ;; *) die "annulé." ;; esac
}

parse_common_flags() {
    for arg in "$@"; do
        case "$arg" in
            --yes) ASSUME_YES=1 ;;
        esac
    done
}
