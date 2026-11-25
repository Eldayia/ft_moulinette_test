# Plugin CLion

Le ZIP est compilé contre CLion **2026.3**, installé dans `/opt/clion`.

## Installation pour tester

1. CLion → Settings → Plugins → roue dentée → Install Plugin from Disk.
2. Choisir `build/distributions/ft-moulinette-clion-0.3.0.zip` et redémarrer si demandé.
3. Ouvrir le dossier Libft contenant son Makefile (pas le dossier de la moulinette).
4. Tools → **Moulinette: tester le projet**.
5. Indiquer le chemin absolu du lanceur `bin/ft-moulinette` de ce dépôt. Aucun pip/venv n’est nécessaire avec ce lanceur ; Python 3.10+ doit être accessible.
6. Lire la console **Moulinette** en bas. Pour un seul fichier, l’ouvrir et choisir **Moulinette: tester le fichier**.

Le chemin du lanceur est mémorisé par projet. Les fichiers ouverts sont sauvegardés avant le test. Fermer l’onglet de résultat arrête le processus s’il est encore actif.

## Reconstruire sans Gradle

```sh
python3 integrations/clion/build_local.py --clion /opt/clion
```

Le script utilise le JDK et les JAR du CLion installé, compile les sources Java et génère le ZIP. Pour une autre version de CLion, utiliser son chemin ; le ZIP est marqué compatible à partir de la branche utilisée pour la compilation.

## Test de réception

- Projet incomplet : voir les fichiers manquants et les fonctions disponibles testées.
- Fichier `ft_strlen.c` : seuls ses résultats fonctionnels doivent apparaître.
- Introduire temporairement une erreur de compilation : elle doit apparaître dans la console.
- Corriger, relancer, vérifier le nouveau résultat et l’absence de modifications des objets du projet original.

La compilation du plugin et le contenu du ZIP sont vérifiés automatiquement. Son chargement et ses interactions graphiques sont à valider dans ton CLion.

La configuration Gradle reste disponible pour le développement via `gradle buildPlugin` ou `gradle runIde` (SDK 2025.3, JDK 21, Gradle 9+). Le ZIP livré ici est construit localement contre le SDK 2026.3.

Procédure JetBrains : https://www.jetbrains.com/help/clion/managing-plugins.html.
