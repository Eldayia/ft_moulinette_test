<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '#lib/api.ts';
	import { formatDate } from '#lib/labels.ts';

	type Token = { id: number; name: string; prefix: string; created_at: string; last_used_at: string | null };
	let tokens = $state<Token[]>([]);
	let name = $state('');
	let created = $state<string | null>(null);
	let error = $state('');

	onMount(load);
	async function load() {
		tokens = await api.get<Token[]>('/api/tokens');
	}
	async function create(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		try {
			created = (await api.post<{ token: string }>('/api/tokens', { name })).token;
			name = '';
			await load();
		} catch (exc) {
			error = exc instanceof ApiError ? exc.message : 'Création impossible.';
		}
	}
	async function revoke(id: number) {
		if (!confirm('Révoquer ce jeton ? Les outils qui l’utilisent seront déconnectés.')) return;
		await api.del(`/api/tokens/${id}`);
		await load();
	}
</script>

<main class="page">
	<section class="card">
		<h2>Jetons personnels</h2>
		<p class="hint">Pour la CLI et les extensions d’éditeur en mode distant : ils parlent à cette plateforme, jamais directement à Google Cloud. Un jeton donne accès à ton compte : garde-le secret.</p>
		<form class="row-actions" onsubmit={create}>
			<input bind:value={name} placeholder="Nom (ex. vscode-maison)" maxlength="64" required aria-label="Nom du jeton" />
			<button class="secondary" type="submit">Créer</button>
		</form>
		{#if error}<p class="form-error" role="alert">{error}</p>{/if}
		{#if created}
			<div class="banner good">
				<strong>Copie ce jeton maintenant : il ne sera plus affiché.</strong>
				<p class="secret">{created}</p>
			</div>
		{/if}
	</section>
	<section class="card">
		{#if tokens.length}
			<table>
				<thead><tr><th>Nom</th><th>Préfixe</th><th>Créé</th><th>Dernière utilisation</th><th></th></tr></thead>
				<tbody>
					{#each tokens as token (token.id)}
						<tr>
							<td>{token.name}</td><td class="mono">{token.prefix}…</td><td>{formatDate(token.created_at)}</td>
							<td>{formatDate(token.last_used_at)}</td>
							<td><button type="button" class="link danger" onclick={() => revoke(token.id)}>Révoquer</button></td>
						</tr>
					{/each}
				</tbody>
			</table>
		{:else}
			<p class="empty">Aucun jeton actif.</p>
		{/if}
	</section>
</main>
