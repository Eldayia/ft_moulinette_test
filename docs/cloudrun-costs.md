# Coûts de l’exécution distante

**Aucun tarif n’est reproduit ici.** La page officielle (<https://cloud.google.com/run/pricing>) n’a pas pu être lue automatiquement le 25 novembre 2026 (contenu rendu côté navigateur). Les montants sont à relever à la main sur cette page et sur le simulateur <https://cloud.google.com/products/calculator>, puis à reporter dans le tableau du §2. Les plafonds applicatifs et les alertes budgétaires **réduisent** le risque de dépense, ils **ne garantissent pas** l’absence de frais.

## 1. Postes de coût

| Service | Ce qui est facturé | Leviers dans ce dépôt |
| --- | --- | --- |
| Cloud Run (runner-api) | CPU et mémoire pendant le traitement des requêtes (facturation à la requête : annotation `cpu-throttling: "true"`), nombre de requêtes | 0 instance minimum, 2 maximum, 1 vCPU, 2 Gio, concurrence 1, délai HTTP 120 s, délai de soumission 60 s |
| Sandboxes Cloud Run | Pas de tarif distinct trouvé dans la documentation lue ; elles partagent les ressources de l’instance | Une sandbox par soumission, supprimée à la fin |
| Artifact Registry | Stockage des images (environ 1,2 Go pour runner-api, 1,0 Go pour sandbox-c, compressées à la publication), transfert vers Cloud Run | Politique de nettoyage `deploy/gcp/cleanup-policy.json` |
| Cloud Build | Seulement si les images y sont construites (sinon construction locale, gratuite) | `build.sh` construit localement |
| Cloud Logging | Volume des journaux ingérés au-delà de l’allocation gratuite | Une ligne JSON par soumission, champs bornés, pas de journal d’accès uvicorn |
| Réseau | Sortie de Cloud Run vers le VPS (rapports ≤ 1 Mio) et entrée (archives ≤ 5 Mio) | Limites de taille |

## 2. Estimation (à compléter avec les tarifs officiels)

Pour une soumission : coût ≈ durée facturée × (vCPU × prix vCPU-s + Gio × prix Gio-s) + prix par requête. Avec 1 vCPU et 2 Gio, une soumission complète Libft prend environ 55 s en local. Sur Cloud Run, le temps réel, démarrage à froid compris, sera mesuré par `smoke-test.sh`.

| Hypothèse | Valeur |
| --- | --- |
| Utilisateurs de la bêta | 15 |
| Soumissions par utilisateur et par jour (quota) | 20 au maximum |
| Plafond global quotidien (`FTM_QUOTA_GLOBAL_DAILY`) | 300 |
| Durée facturée par soumission | à mesurer (≤ 60 s par construction, plus le démarrage) |
| Prix vCPU-s, Gio-s, requête (niveau de europe-west1) | à relever sur la page officielle |
| Niveau gratuit mensuel | à relever sur la page officielle |

Pire cas borné par l’application : 300 soumissions × 120 s × (1 vCPU + 2 Gio) par jour. Le délai HTTP de 120 s est la borne haute par requête, et le délai de soumission de 60 s la borne habituelle.

## 3. Garde-fous

- **Quotas applicatifs** (`workers/dispatcher/ftm_dispatcher/quotas.py`, configurables) : 20 soumissions par utilisateur et par jour, 1 en cours par utilisateur, 20 en file ou en cours au total, 10 s entre deux soumissions d’un même utilisateur, plafond global quotidien de 300. La concurrence d’exécution vaut 2 (`MAX_CONCURRENT_JOBS`, nombre de workers RQ).
- **Interrupteurs** : `FTM_EXECUTIONS_DISABLED=1` sur le worker (refus à la mise en file et à l’exécution) et sur le service Cloud Run (`/readyz` en 503, exécutions refusées). `rq suspend` arrête aussi la consommation de la file.
- **Arrêt d’urgence côté Google** : redéployer avec `EXECUTIONS_DISABLED=1`, ou retirer `roles/run.invoker` au compte invoker, ou supprimer le service (voir `deploy/gcp/README.md`).
- **Alertes budgétaires** : à créer dans la console (Facturation, puis Budgets et alertes) sur le projet dédié, avec des seuils à 50 %, 90 % et 100 % d’un budget mensuel modeste. Une alerte **n’arrête pas** la facturation. Un arrêt automatique demande une Cloud Function abonnée au sujet Pub/Sub du budget, non fournie ici.
- **Projet dédié** : utiliser un projet GCP réservé à ft-moulinette, pour lire la facture sans ambiguïté et pouvoir tout supprimer d’un coup.

## 4. Nettoyage des images

`deploy/gcp/cleanup-policy.json` conserve les 10 versions les plus récentes et supprime les versions de plus de 30 jours. L’application passe par `gcloud artifacts repositories set-cleanup-policies`, d’abord en simulation. Vérifier la syntaxe exacte de la commande dans la documentation Artifact Registry avant de l’appliquer : elle n’a pas été exécutée pendant le développement.
