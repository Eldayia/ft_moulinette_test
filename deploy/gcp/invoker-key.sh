#!/usr/bin/env bash
# Clé JSON du compte ft-moulinette-invoker, pour le worker du VPS (mode GCP_AUTH_MODE=key, bêta privée).
# Une clé est un secret permanent : ce script ne s'exécute que sur demande explicite et confirmation.
# Préférer Workload Identity Federation dès qu'une identité externe compatible est disponible.
#
# Usage :
#   deploy/gcp/invoker-key.sh create [--yes]   crée une clé et l'écrit dans deploy/ovh/secrets/gcp_invoker.json (0400)
#   deploy/gcp/invoker-key.sh list             liste les clés du compte (rotation)
#   deploy/gcp/invoker-key.sh delete KEY_ID    supprime une ancienne clé, après mise en service de la nouvelle
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"
parse_common_flags "$@"
require gcloud
load_config
target="$REPO_ROOT/deploy/ovh/secrets/gcp_invoker.json"
case "${1:-}" in
    create)
        [ -e "$target" ] && die "$target existe déjà : rotation = list, create vers un autre fichier, puis delete."
        confirm "Créer une clé permanente pour $INVOKER_SA (rôle roles/run.invoker sur le service uniquement) ?"
        install -d -m 700 "$(dirname "$target")"
        umask 077
        gcloud iam service-accounts keys create "$target" --iam-account="$INVOKER_SA" --project "$PROJECT_ID"
        chmod 400 "$target"
        info "Clé écrite dans $target (0400). Sur le VPS : sudo chown 10001:10001 $target"
        info "Ne jamais la versionner, la copier dans le frontend ou l'API publique, ni la journaliser."
        ;;
    list)
        gcloud iam service-accounts keys list --iam-account="$INVOKER_SA" --project "$PROJECT_ID" --managed-by=user
        ;;
    delete)
        [ -n "${2:-}" ] || die "identifiant de clé requis (voir list)."
        confirm "Supprimer la clé $2 de $INVOKER_SA ? Les workers qui l'utilisent perdront l'accès."
        gcloud iam service-accounts keys delete "$2" --iam-account="$INVOKER_SA" --project "$PROJECT_ID" --quiet
        ;;
    *) die "usage : invoker-key.sh create|list|delete KEY_ID" ;;
esac
