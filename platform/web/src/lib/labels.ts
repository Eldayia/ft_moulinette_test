// Libellés en français, repris du moteur (cli/ft_moulinette/report.py) et de la mission (§15, §23).

export const STATUS: Record<string, { label: string; plural: string; problem?: boolean }> = {
	fail: { label: 'échec', plural: 'en échec', problem: true },
	missing: { label: 'manquant', plural: 'manquants', problem: true },
	blocked: { label: 'bloqué', plural: 'bloqués', problem: true },
	unavailable: { label: 'indisponible', plural: 'indisponibles', problem: true },
	manual: { label: 'à relire', plural: 'à relire' },
	reviewed: { label: 'relu', plural: 'relus' },
	skip: { label: 'ignoré', plural: 'ignorés' },
	pass: { label: 'réussi', plural: 'réussis' }
};
export const STATUS_ORDER = Object.keys(STATUS);

// Étapes réellement atteintes, positionnées par le worker (aucune progression inventée).
export const STEPS = [
	{ key: 'queued', label: 'En attente' },
	{ key: 'preparing', label: 'Préparation' },
	{ key: 'running', label: 'Exécution distante' },
	{ key: 'analyzing', label: 'Analyse des résultats' },
	{ key: 'done', label: 'Terminé' }
];

export type Tone = 'good' | 'bad' | 'warn' | 'infra' | 'neutral';

// Distinction demandée par la mission : échec de test, compilation, erreur Google Cloud, non pris en charge, limite.
export const OUTCOME: Record<string, { label: string; tone: Tone; kind: string; help: string }> = {
	success: { label: 'Aucun problème signalé', tone: 'good', kind: 'Résultat', help: 'Les contrôles exécutés n’ont rien signalé. Cela ne certifie pas la conformité au sujet.' },
	compilation_error: { label: 'Compilation échouée', tone: 'bad', kind: 'Ton code', help: 'Le projet ne compile pas ou un banc de test n’a pas pu être lié.' },
	test_failure: { label: 'Tests en échec', tone: 'bad', kind: 'Ton code', help: 'Au moins un test fonctionnel, un fichier attendu ou une règle du Makefile pose problème.' },
	memory_error: { label: 'Erreur mémoire', tone: 'bad', kind: 'Ton code', help: 'Valgrind a détecté une fuite ou un accès invalide.' },
	norm_error: { label: 'Norme non respectée', tone: 'warn', kind: 'Ton code', help: 'Seule la Norminette signale des problèmes.' },
	unsupported: { label: 'Non pris en charge', tone: 'warn', kind: 'Fonctionnalité', help: 'Un analyseur demandé était indisponible ou la soumission a été refusée : le résultat n’est pas complet.' },
	timeout: { label: 'Délai dépassé', tone: 'warn', kind: 'Limite atteinte', help: 'L’exécution a dépassé le délai global : boucle infinie ou programme trop lent ?' },
	resource_limit: { label: 'Limite de ressources atteinte', tone: 'warn', kind: 'Limite atteinte', help: 'Sortie trop volumineuse ou limite de l’environnement d’exécution atteinte.' },
	cancelled: { label: 'Annulée', tone: 'neutral', kind: 'Exécution', help: 'L’exécution a été annulée.' },
	infrastructure_error: { label: 'Erreur d’infrastructure', tone: 'infra', kind: 'Google Cloud / plateforme', help: 'L’exécution distante a échoué pour une raison indépendante de ton code. Tu peux relancer la soumission.' },
	sandbox_unavailable: { label: 'Environnement d’exécution indisponible', tone: 'infra', kind: 'Google Cloud', help: 'La sandbox Cloud Run est indisponible : rien n’a été exécuté. Réessaie plus tard.' }
};

const LABELS: Record<string, string> = {
	'memory:tool': 'disponibilité de Valgrind', functional: 'test fonctionnel', memory: 'contrôle mémoire',
	compile: 'compilation', norm: 'norme', readme: 'titres des sections', 'readme:first-line': 'première ligne',
	relink: 'seconde exécution de make', link: 'liaison du programme de test',
	prototype: 'déclaration de la fonction dans le header', symbols: 'variables et fonctions autorisées',
	archive: 'contenu de la bibliothèque', structure: 'emplacement des fichiers',
	allocation: 'simulation d’une panne malloc', 'allocation:baseline': 'allocation témoin',
	flags: 'options de compilation', commands: 'commandes exécutées par make',
	archiver: 'outil de création de la bibliothèque', presence: 'présence du fichier', make: 'contrôles du Makefile'
};
const PREFIXES: Record<string, string> = {
	rebuild: 'reconstruction après modification de', make: 'exécution de make',
	postcondition: 'fichiers présents après make', allocation: 'échec simulé du malloc numéro'
};

export function checkLabel(check: string): string {
	const archive = check.startsWith('archive:');
	const id = archive ? check.slice(8) : check;
	let label = LABELS[id];
	if (!label) {
		const [category, ...rest] = id.split(':');
		const value = rest.join(':');
		if (category === 'functional' || category === 'memory') label = `${LABELS[category]} · ${value}`;
		else label = PREFIXES[category] ? `${PREFIXES[category]} ${value}` : id;
	}
	return archive ? `${label} (archive)` : label;
}

export function formatDate(iso: string | null): string {
	if (!iso) return '—';
	return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
}

export function formatDuration(seconds: number | null | undefined): string {
	if (seconds == null) return '—';
	if (seconds < 60) return `${Math.round(seconds)} s`;
	return `${Math.floor(seconds / 60)} min ${String(Math.round(seconds % 60)).padStart(2, '0')} s`;
}

export function problems(summary: Record<string, number> | null | undefined): number {
	return Object.entries(summary ?? {}).reduce((n, [s, c]) => n + (STATUS[s]?.problem ? c : 0), 0);
}
