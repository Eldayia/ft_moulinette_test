#!/usr/bin/env bash
# Déploie runner-api sur Cloud Run à partir du digest produit par build.sh --push, puis vérifie :
# accès anonyme absent, seul l'invoker autorisé, sandbox launcher activé.
# N'utilise jamais --allow-unauthenticated.
#
# Usage : deploy/gcp/deploy.sh [--yes]
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"
parse_common_flags "$@"
require gcloud python3
load_config
[ -f "$GCP_DIR/images.env" ] || die "deploy/gcp/images.env absent : lancer build.sh --push."
# shellcheck disable=SC1091
. "$GCP_DIR/images.env"
export RUNNER_IMAGE RUNTIME_SA

mkdir -p "$GCP_DIR/.rendered"
manifest="$GCP_DIR/.rendered/service.yaml"
python3 "$GCP_DIR/render.py" "$GCP_DIR/service.yaml.template" > "$manifest"
info "Manifeste rendu : $manifest"
grep -q 'sandboxLauncher: true' "$manifest" || die "sandboxLauncher absent du manifeste."

confirm "Déployer $SERVICE_NAME ($REGION, max $MAX_INSTANCES instances, $CPU vCPU, $MEMORY) sur $PROJECT_ID ?"
gcloud beta run services replace "$manifest" --region "$REGION" --project "$PROJECT_ID"

info "Autorisation du seul compte invoker (roles/run.invoker sur ce service)"
gcloud run services add-iam-policy-binding "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" \
    --member="serviceAccount:$INVOKER_SA" --role='roles/run.invoker' >/dev/null

info "Vérification de la politique IAM du service"
gcloud run services get-iam-policy "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format=json \
    | python3 -c '
import json, sys
policy = json.load(sys.stdin)
members = [(b.get("role"), m) for b in policy.get("bindings", []) for m in b.get("members", [])]
public = [m for _, m in members if m in ("allUsers", "allAuthenticatedUsers")]
if public:
    sys.exit("ERREUR : accès public détecté (" + ", ".join(public) + ") ; retirer ces membres immédiatement.")
invokers = [m for r, m in members if r == "roles/run.invoker"]
expected = "serviceAccount:" + sys.argv[1]
if expected not in invokers:
    sys.exit("ERREUR : " + expected + " n est pas invoker.")
extra = [m for m in invokers if m != expected]
print("Invokers :", ", ".join(invokers))
if extra:
    print("ATTENTION : autres invokers que le worker :", ", ".join(extra))
' "$INVOKER_SA"

info "Vérification de l'activation des sandboxes"
gcloud beta run services describe "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format=export \
    | grep -q 'sandboxLauncher: true' || die "sandboxLauncher: true absent de la révision déployée."

url=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')
[ -n "$url" ] || die "URL du service introuvable."
cat <<EOF

Service déployé : $url
Image : $RUNNER_IMAGE

Configuration du worker sur le VPS OVH (voir docs/docker-deployment.md) :
  EXECUTION_BACKEND=cloudrun
  FTM_ENVIRONMENT=production
  GCP_PROJECT_ID=$PROJECT_ID
  GCP_REGION=$REGION
  CLOUD_RUN_URL=$url
  GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp_invoker   # mode key, ou fichier external_account en mode wif
  GCP_AUTH_MODE=key                                         # ou wif + GCP_INVOKER_SERVICE_ACCOUNT=$INVOKER_SA

Étape suivante, obligatoire avant toute ouverture : deploy/gcp/smoke-test.sh
EOF
