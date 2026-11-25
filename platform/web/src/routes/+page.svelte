<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { api, ApiError, type Submission } from '#lib/api.ts';
	import { OUTCOME, formatDate, formatDuration, problems } from '#lib/labels.ts';
	import { session } from '#lib/session.svelte.ts';

	const ACCEPTED = /(\.c|\.h|\.md|\.mk|^Makefile|^makefile|^GNUmakefile)$/;
	const SKIPPED_DIRS = ['.git', '.venv', '__pycache__', 'node_modules'];
	const STATE_LABEL: Record<string, string> = {
		queued: 'En attente', preparing: 'Préparation', running: 'Exécution distante', analyzing: 'Analyse', done: 'Terminé', failed: 'Erreur'
	};

	let project = $state('libft');
	let source = $state<'archive' | 'files' | 'pasted'>('files');
	let target = $state('');
	let norm = $state(true);
	let memory = $state(true);
	let build = $state(true);
	let iterations = $state(500);
	let seed = $state(42);
	let archive = $state<File | null>(null);
	let picked = $state<{ path: string; file: File }[]>([]);
	let ignored = $state(0);
	let pasted = $state([{ name: 'ft_strlen.c', content: '' }]);
	let error = $state('');
	let busy = $state(false);
	let history = $state<Submission[]>([]);

	onMount(loadHistory);

	async function loadHistory() {
		try {
			history = await api.get<Submission[]>('/api/submissions?limit=50');
		} catch {
			history = [];
		}
	}

	function pick(event: Event) {
		const files = [...((event.target as HTMLInputElement).files ?? [])];
		// Dossier : chemins relatifs (webkitRelativePath), sans le dossier racine choisi.
		const entries = files.map((file) => {
			const relative = file.webkitRelativePath || file.name;
			const parts = relative.split('/');
			return { path: file.webkitRelativePath ? parts.slice(1).join('/') : relative, file };
		});
		const kept = entries.filter(({ path }) => {
			const parts = path.split('/');
			return ACCEPTED.test(parts[parts.length - 1]) && !parts.some((p) => SKIPPED_DIRS.includes(p));
		});
		ignored = entries.length - kept.length;
		picked = kept;
	}

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		const form = new FormData();
		form.set('project', project);
		form.set('source', source);
		form.set('options', JSON.stringify({ norm, memory, build, iterations: Number(iterations), seed: Number(seed) }));
		if (target.trim()) form.set('target', target.trim());
		if (source === 'archive') {
			if (!archive) return (error = 'Choisis une archive ZIP.');
			form.set('archive', archive);
		} else if (source === 'files') {
			if (!picked.length) return (error = 'Choisis un dossier ou des fichiers (.c, .h, Makefile…).');
			for (const { file } of picked) form.append('files', file);
			form.set('paths', JSON.stringify(picked.map(({ path }) => path)));
		} else {
			const files = Object.fromEntries(pasted.filter((p) => p.name.trim()).map((p) => [p.name.trim(), p.content]));
			if (!Object.keys(files).length) return (error = 'Ajoute au moins un fichier.');
			form.set('pasted', JSON.stringify(files));
		}
		busy = true;
		try {
			const created = await api.post<Submission>('/api/submissions', form);
			await goto(`/submissions/${created.id}`);
		} catch (exc) {
			error = exc instanceof ApiError ? exc.message : 'Envoi impossible.';
		} finally {
			busy = false;
		}
	}

	const disabled = $derived(busy || (session.status ? !session.status.executions_enabled : false));
</script>

<main class="page grid2">
	<form class="card" onsubmit={submit}>
		<h2>Nouvelle soumission</h2>
		<label class="field" for="project">Projet
			<select id="project" bind:value={project}>
				<option value="libft">Libft 1.3</option>
				<option value="printf">Printf 1.1</option>
			</select>
		</label>

		<div class="tabs" role="tablist" aria-label="Méthode d’envoi">
			<button type="button" role="tab" aria-selected={source === 'files'} onclick={() => (source = 'files')}>Dossier ou fichiers</button>
			<button type="button" role="tab" aria-selected={source === 'archive'} onclick={() => (source = 'archive')}>Archive ZIP</button>
			<button type="button" role="tab" aria-selected={source === 'pasted'} onclick={() => (source = 'pasted')}>Coller du code</button>
		</div>

		{#if source === 'files'}
			<label class="field" for="folder">Dossier du projet
				<input id="folder" type="file" webkitdirectory multiple onchange={pick} />
			</label>
			<label class="field" for="files">ou fichiers isolés
				<input id="files" type="file" multiple accept=".c,.h,.md,.mk" onchange={pick} />
			</label>
			<p class="hint">{picked.length} fichier(s) retenu(s){ignored ? `, ${ignored} ignoré(s) (objets, binaires, .git…)` : ''}.</p>
		{:else if source === 'archive'}
			<label class="field" for="zip">Archive ZIP
				<input id="zip" type="file" accept=".zip,application/zip" onchange={(e) => (archive = (e.target as HTMLInputElement).files?.[0] ?? null)} />
			</label>
		{:else}
			{#each pasted as entry, index (index)}
				<label class="field" for="name-{index}">Nom du fichier
					<input id="name-{index}" bind:value={entry.name} placeholder="ft_strlen.c" spellcheck="false" />
				</label>
				<textarea bind:value={entry.content} spellcheck="false" aria-label="Contenu de {entry.name}"></textarea>
			{/each}
			<button type="button" class="link" onclick={() => pasted.push({ name: '', content: '' })}>Ajouter un fichier</button>
		{/if}

		<label class="field" for="target">Fichier ciblé (facultatif)
			<input id="target" bind:value={target} placeholder="ft_strlen.c" spellcheck="false" />
		</label>
		<fieldset class="toggles">
			<legend>Contrôles</legend>
			<label><input type="checkbox" bind:checked={norm} /> Norminette</label>
			<label><input type="checkbox" bind:checked={memory} /> Valgrind</label>
			<label><input type="checkbox" bind:checked={build} /> Makefile et archive</label>
		</fieldset>
		<details class="advanced">
			<summary>Réglages avancés</summary>
			<div class="numbers">
				<label class="field" for="iterations">Itérations<input id="iterations" type="number" min="1" max="100000" bind:value={iterations} /></label>
				<label class="field" for="seed">Graine<input id="seed" type="number" min="0" bind:value={seed} /></label>
			</div>
		</details>
		<button class="primary" type="submit" {disabled}>Lancer la moulinette</button>
		{#if error}<p class="form-error" role="alert">{error}</p>{/if}
		{#if session.status}
			<p class="hint">
				{session.status.quotas.per_user_daily} soumissions par jour, {session.status.quotas.per_user_concurrent} à la fois ·
				{Math.round(session.status.limits.max_upload_bytes / 1048576)} Mio et {session.status.limits.max_files} fichiers au maximum.
			</p>
		{/if}
	</form>

	<section class="card">
		<div class="row-actions"><h2>Historique</h2><button type="button" class="link" onclick={loadHistory}>Actualiser</button></div>
		{#if history.length}
			<table>
				<thead><tr><th>Date</th><th>Projet</th><th>État</th><th>Résultat</th><th>Durée</th></tr></thead>
				<tbody>
					{#each history as item (item.id)}
						<tr class="link" onclick={() => goto(`/submissions/${item.id}`)}>
							<td><a href="/submissions/{item.id}">{formatDate(item.created_at)}</a></td>
							<td>{item.project}{item.target ? ` · ${item.target}` : ''}</td>
							<td>{STATE_LABEL[item.status] ?? item.status}</td>
							<td>
								{#if item.outcome}
									<span class="pill state-{OUTCOME[item.outcome]?.tone === 'good' ? 'done' : 'error'}">{OUTCOME[item.outcome]?.label ?? item.outcome}</span>
									{#if problems(item.summary)}<span class="muted"> {problems(item.summary)} problème(s)</span>{/if}
								{:else}—{/if}
							</td>
							<td>{formatDuration(item.duration_seconds)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{:else}
			<p class="empty">Aucune soumission pour l’instant.</p>
		{/if}
	</section>
</main>
