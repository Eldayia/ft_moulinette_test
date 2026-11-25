<script lang="ts">
	import { goto } from '$app/navigation';
	import { api, ApiError, type Me } from '#lib/api.ts';
	import { refreshSession, session } from '#lib/session.svelte.ts';

	let login = $state('');
	let password = $state('');
	let error = $state('');
	let busy = $state(false);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = '';
		try {
			await api.post<Me>('/api/auth/login', { login, password });
			await refreshSession();
			await goto('/');
		} catch (exc) {
			error = exc instanceof ApiError ? exc.message : 'Connexion impossible.';
		} finally {
			busy = false;
			password = '';
		}
	}

	$effect(() => {
		if (session.me) goto('/');
	});
</script>

<main class="page">
	<form class="card narrow" onsubmit={submit}>
		<h2>Connexion</h2>
		<label class="field" for="login">Identifiant
			<input id="login" autocomplete="username" bind:value={login} required />
		</label>
		<label class="field" for="password">Mot de passe
			<input id="password" type="password" autocomplete="current-password" bind:value={password} required />
		</label>
		<button class="primary" type="submit" disabled={busy}>Se connecter</button>
		{#if error}<p class="form-error" role="alert">{error}</p>{/if}
		<p class="hint">Bêta privée : les comptes sont créés par un administrateur.</p>
	</form>
</main>
