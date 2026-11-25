<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onDestroy } from 'svelte';
	import { api, ApiError, type Submission } from '#lib/api.ts';
	import Report from '#lib/Report.svelte';
	import { OUTCOME, STEPS, formatDate, formatDuration } from '#lib/labels.ts';

	let submission = $state<Submission | null>(null);
	let error = $state('');
	let timer: ReturnType<typeof setTimeout> | undefined;

	async function load() {
		clearTimeout(timer);
		try {
			submission = await api.get<Submission>(`/api/submissions/${page.params.id}`);
			error = '';
			if (!['done', 'failed'].includes(submission.status)) timer = setTimeout(load, 2000);
		} catch (exc) {
			error = exc instanceof ApiError ? exc.message : 'Soumission introuvable.';
		}
	}

	$effect(() => {
		page.params.id;
		submission = null;
		load();
	});
	onDestroy(() => clearTimeout(timer));

	const finished = $derived(submission ? ['done', 'failed'].includes(submission.status) : false);
	const stepIndex = $derived(submission ? STEPS.findIndex((s) => s.key === submission!.status) : -1);
	const outcome = $derived(submission?.outcome ? OUTCOME[submission.outcome] : null);

	async function remove() {
		if (!submission || !confirm('Supprimer cette soumission et son rapport ?')) return;
		await api.del(`/api/submissions/${submission.id}`);
		await goto('/');
	}
</script>

<main class="page">
	{#if error}
		<div class="banner bad" role="alert">{error}</div>
	{:else if !submission}
		<p class="muted">Chargement…</p>
	{:else}
		<div class="result-head">
			<div class="result-title">
				<h2>{submission.project === 'libft' ? 'Libft 1.3' : 'Printf 1.1'}{submission.target ? ` · ${submission.target}` : ''}</h2>
				<div class="result-meta">
					<span class="muted">Envoyée le {formatDate(submission.created_at)} · {submission.files} fichier(s)</span>
					{#if submission.duration_seconds}<span class="muted">· durée {formatDuration(submission.duration_seconds)}</span>{/if}
					{#if submission.metadata?.backend}<span class="tag">{submission.metadata.backend}</span>{/if}
				</div>
			</div>
			<div class="actions">
				<a class="secondary" href="/">Nouvelle soumission</a>
				{#if finished}<button type="button" class="secondary danger" onclick={remove}>Supprimer</button>{/if}
			</div>
		</div>

		<ol class="steps" aria-label="Étapes">
			{#each STEPS as step, index (step.key)}
				{#if submission.status === 'failed' && index === STEPS.length - 1}
					<li class="failed">Erreur</li>
				{:else}
					<li class:done={index < stepIndex || submission.status === 'done'} class:current={index === stepIndex && !finished}>{step.label}</li>
				{/if}
			{/each}
		</ol>

		{#if !finished}
			<div class="banner neutral waiting">
				<span class="spinner" aria-hidden="true"></span>
				{#if submission.status === 'queued'}
					En attente d’un emplacement d’exécution{submission.queue_position ? ` (position ${submission.queue_position})` : ''}.
				{:else}
					Compilation et tests dans l’environnement isolé… Un projet complet prend souvent plus d’une minute.
				{/if}
			</div>
		{:else if outcome}
			<div class="banner {outcome.tone === 'good' ? 'good' : outcome.tone === 'bad' ? 'bad' : outcome.tone}">
				<div class="kind">{outcome.kind}</div>
				<strong>{outcome.label}.</strong> {outcome.help}
				{#if submission.error}<p class="pre">{submission.error.message}</p>{/if}
			</div>
		{/if}

		{#if submission.report}
			<Report report={submission.report} />
		{/if}
	{/if}
</main>
