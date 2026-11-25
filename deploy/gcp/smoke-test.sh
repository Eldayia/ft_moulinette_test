#!/usr/bin/env bash
# Validation réelle du service déployé (voir smoke_test.py). Retourne 1 si une vérification essentielle échoue.
#
# Usage : deploy/gcp/smoke-test.sh [--key-file CLE.json]
# Par défaut, l'ID token est obtenu avec gcloud en empruntant le compte invoker (rôle
# roles/iam.serviceAccountTokenCreator requis sur ce compte pour ton utilisateur).
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"
require gcloud python3
load_config
url=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')
[ -n "$url" ] || die "service $SERVICE_NAME introuvable."
if [ "${1:-}" = --key-file ]; then
    python3 "$GCP_DIR/smoke_test.py" --url "$url" --key-file "${2:?chemin de la clé}"
else
    python3 "$GCP_DIR/smoke_test.py" --url "$url" --impersonate "$INVOKER_SA"
fi
