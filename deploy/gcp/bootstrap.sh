#!/usr/bin/env bash
# Prépare un projet Google Cloud pour runner-api. Idempotent : chaque ressource existante est conservée.
# Ne crée aucune clé, n'accorde aucun rôle au niveau du projet, ne touche pas à la facturation.
# Chaque création demande une confirmation (ou --yes).
#
# Usage : deploy/gcp/bootstrap.sh [--yes]
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"
parse_common_flags "$@"
require gcloud
load_config

account=$(gcloud config get-value account 2>/dev/null || true)
[ -n "$account" ] || die "aucun compte gcloud actif : gcloud auth login"
info "Compte : $account — projet : $PROJECT_ID — région : $REGION"
gcloud projects describe "$PROJECT_ID" --format='value(projectId)' >/dev/null \
    || die "projet $PROJECT_ID inaccessible avec ce compte."

APIS="run.googleapis.com artifactregistry.googleapis.com iam.googleapis.com iamcredentials.googleapis.com"
confirm "Activer les API ($APIS) sur $PROJECT_ID ? L'activation est gratuite ; l'usage est facturé."
# shellcheck disable=SC2086
gcloud services enable $APIS --project "$PROJECT_ID"

if gcloud artifacts repositories describe "$REPOSITORY" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
    info "Dépôt Artifact Registry $REPOSITORY déjà présent."
else
    confirm "Créer le dépôt Docker Artifact Registry $REPOSITORY ($REGION) ? Le stockage des images est facturé."
    gcloud artifacts repositories create "$REPOSITORY" --repository-format=docker --location="$REGION" \
        --project "$PROJECT_ID" --description="Images ft-moulinette (runner-api, sandbox-c)"
fi

for name in "$RUNTIME_SA_NAME" "$INVOKER_SA_NAME"; do
    email="${name}@${PROJECT_ID}.iam.gserviceaccount.com"
    if gcloud iam service-accounts describe "$email" --project "$PROJECT_ID" >/dev/null 2>&1; then
        info "Compte de service $email déjà présent."
    else
        confirm "Créer le compte de service $email (aucun rôle projet ne lui sera donné) ?"
        gcloud iam service-accounts create "$name" --project "$PROJECT_ID" --display-name="ft-moulinette ${name#ft-moulinette-}"
    fi
done

cat <<EOF

Préparation terminée. Permissions :
- $RUNTIME_SA : identité du service Cloud Run, aucun rôle projet (ni Owner, ni Editor).
- $INVOKER_SA : recevra uniquement roles/run.invoker sur le service, au déploiement (deploy.sh).
- Ton compte doit pouvoir déployer : roles/run.developer sur le service et
  roles/iam.serviceAccountUser sur $RUNTIME_SA (documentation Cloud Run sandboxes).

Authentification du worker OVH, au choix (voir docs/cloudrun.md) :
- Workload Identity Federation (recommandé) : pool, fournisseur OIDC et roles/iam.workloadIdentityUser
  sur $INVOKER_SA, à configurer selon le fournisseur d'identité du VPS.
- Clé JSON (bêta privée) : aucune clé n'est créée automatiquement. Si tu la crées toi-même,
  stocke-la uniquement dans le secret Docker gcp_invoker du worker, jamais dans le dépôt.

Étape suivante : deploy/gcp/build.sh --push
EOF
