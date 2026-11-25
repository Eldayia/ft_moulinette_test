<script lang="ts">
	import { goto } from '$app/navigation';
	import { api, ApiError } from '#lib/api.ts';
	import { session } from '#lib/session.svelte.ts';

	let current = $state('');
	let next = $state('');
	let confirmation = $state('');
	let error = $state('');

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		if (next !== confirmation) return (error = 'Les deux nouveaux mots de passe diffèrent.');
		try {
			await api.post('/api/me/password', { current, new: next });
			session.me = null;
			await goto('/login');
		} catch (exc) {
			error = exc instanceof ApiError ? exc.message : 'Modification impossible.';
		}
	}
</script>

<main class="page">
	<form class="card narrow" onsubmit={submit}>
		<h2>Changer de mot de passe</h2>
		<label class="field" for="current">Mot de passe actuel<input id="current" type="password" autocomplete="current-password" bind:value={current} required /></label>
		<label class="field" for="next">Nouveau mot de passe (12 caractères au moins)<input id="next" type="password" autocomplete="new-password" minlength="12" bind:value={next} required /></label>
		<label class="field" for="confirmation">Confirmation<input id="confirmation" type="password" autocomplete="new-password" bind:value={confirmation} required /></label>
		<button class="primary" type="submit">Enregistrer</button>
		{#if error}<p class="form-error" role="alert">{error}</p>{/if}
		<p class="hint">Toutes tes sessions seront fermées ; les jetons personnels restent valides.</p>
	</form>
</main>
