<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '#lib/api.ts';
	import { OUTCOME, formatDate, formatDuration } from '#lib/labels.ts';
	import { refreshSession, session } from '#lib/session.svelte.ts';

	type Overview = {
		executions: { enabled: boolean; env_disabled: boolean; disabled_by: { by: string; at: number } | null };
		runner: { checked_at: number; backend: string | null; available: boolean; detail: string; latency_seconds: number; capabilities: Record<string, any> | null } | null;
		queue: { waiting: number; in_flight: number; global_today: number; policy: Record<string, number> };
		submissions: { today: number; last_7_days: number; per_day: Record<string, number>; outcomes: Record<string, number>; average_seconds: number | null; failure_rate: number | null; in_progress: number };
		consumption: { seconds_7_days: number; estimated_cost_7_days: number | null; note: string };
	};
	type User = { id: number; login: string; is_admin: boolean; disabled: boolean; created_at: string };

	let overview = $state<Overview | null>(null);
	let users = $state<User[]>([]);
	let error = $state('');
	let newLogin = $state('');
	let newAdmin = $state(false);
	let created = $state<{ login: string; password: string } | null>(null);
	let checking = $state(false);

	onMount(load);
	async function load() {
		try {
			overview = await api.get<Overview>('/api/admin/overview');
			users = await api.get<User[]>('/api/admin/users');
			error = '';
		} catch (exc) {
			error = exc instanceof ApiError ? exc.message : 'Chargement impossible.';
		}
	}

	async function toggleExecutions() {
		if (!overview) return;
		const enable = !overview.executions.enabled;
		if (!enable && !confirm('Suspendre immédiatement toutes les exécutions distantes ?')) return;
		await api.post('/api/admin/executions', { enabled: enable });
		await refreshSession();
		await load();
	}

	async function checkRunner() {
		checking = true;
		await api.post('/api/admin/runner-check');
		// Le worker effectue la vérification (lui seul détient l'identité Google).
		setTimeout(async () => {
			await load();
			checking = false;
		}, 4000);
	}

	async function createUser(event: SubmitEvent) {
		event.preventDefault();
		try {
			created = await api.post<{ login: string; password: string }>('/api/admin/users', { login: newLogin, is_admin: newAdmin });
			newLogin = '';
			newAdmin = false;
			await load();
		} catch (exc) {
			error = exc instanceof ApiError ? exc.message : 'Création impossible.';
		}
	}

	async function disable(user: User) {
		if (!confirm(`Désactiver ${user.login} ? Ses sessions seront fermées.`)) return;
		await api.post(`/api/admin/users/${user.id}/disable`);
		await load();
	}
</script>

<main class="page">
	{#if !session.me?.is_admin}
		<div class="banner bad">Réservé aux administrateurs.</div>
	{:else}
		{#if error}<div class="banner bad" role="alert">{error}</div>{/if}
		{#if overview}
			<div class="cards">
				<section class="card">
					<h2>Exécutions</h2>
					<p class="metric">{overview.executions.enabled ? 'Actives' : 'Suspendues'}</p>
					{#if overview.executions.env_disabled}<p class="hint">Désactivées par la configuration du serveur (FTM_EXECUTIONS_DISABLED).</p>{/if}
					{#if overview.executions.disabled_by}<p class="hint">Par {overview.executions.disabled_by.by}, {formatDate(new Date(overview.executions.disabled_by.at * 1000).toISOString())}</p>{/if}
					<button type="button" class="secondary {overview.executions.enabled ? 'danger' : ''}" onclick={toggleExecutions}>
						{overview.executions.enabled ? 'Suspendre' : 'Réactiver'}
					</button>
				</section>
				<section class="card">
					<h2>Runner</h2>
					{#if overview.runner}
						<p class="metric">{overview.runner.available ? 'Disponible' : 'Indisponible'}</p>
						<p class="hint">{overview.runner.backend ?? '—'} · vérifié le {formatDate(new Date(overview.runner.checked_at * 1000).toISOString())} · {overview.runner.latency_seconds} s</p>
						{#if overview.runner.detail}<p class="hint">{overview.runner.detail}</p>{/if}
						{#if overview.runner.capabilities?.image_version}<p class="hint mono">{overview.runner.capabilities.image_version}</p>{/if}
					{:else}
						<p class="metric">Inconnu</p><p class="hint">Aucune vérification enregistrée.</p>
					{/if}
					<button type="button" class="secondary" onclick={checkRunner} disabled={checking}>{checking ? 'Vérification…' : 'Vérifier maintenant'}</button>
				</section>
				<section class="card">
					<h2>File d’attente</h2>
					<p class="metric">{overview.queue.waiting}</p>
					<p class="hint">{overview.queue.in_flight} en file ou en cours · {overview.queue.global_today} aujourd’hui / plafond {overview.queue.policy.global_daily}</p>
				</section>
				<section class="card">
					<h2>Soumissions (7 jours)</h2>
					<p class="metric">{overview.submissions.last_7_days}</p>
					<p class="hint">
						{overview.submissions.today} aujourd’hui · durée moyenne {formatDuration(overview.submissions.average_seconds)} ·
						échecs d’infrastructure {overview.submissions.failure_rate == null ? '—' : `${Math.round(overview.submissions.failure_rate * 100)} %`}
					</p>
				</section>
				<section class="card">
					<h2>Consommation estimée</h2>
					<p class="metric">{overview.consumption.estimated_cost_7_days == null ? '—' : overview.consumption.estimated_cost_7_days.toFixed(2)}</p>
					<p class="hint">{Math.round(overview.consumption.seconds_7_days)} s facturables estimées sur 7 jours. {overview.consumption.note}</p>
				</section>
			</div>

			<section class="card">
				<h2>Résultats (7 jours)</h2>
				<table>
					<thead><tr><th>Résultat</th><th>Nombre</th></tr></thead>
					<tbody>
						{#each Object.entries(overview.submissions.outcomes) as [key, count] (key)}
							<tr><td>{OUTCOME[key]?.label ?? key}</td><td>{count}</td></tr>
						{/each}
					</tbody>
				</table>
				<h2>Par jour</h2>
				<table>
					<tbody>
						{#each Object.entries(overview.submissions.per_day) as [day, count] (day)}
							<tr><td>{day}</td><td>{count}</td></tr>
						{/each}
					</tbody>
				</table>
				<p class="hint">Quotas : {overview.queue.policy.per_user_daily} par utilisateur et par jour, {overview.queue.policy.per_user_concurrent} à la fois, {overview.queue.policy.max_in_flight} en file au total.</p>
			</section>
		{/if}

		<section class="card">
			<h2>Utilisateurs</h2>
			<form class="row-actions" onsubmit={createUser}>
				<input bind:value={newLogin} placeholder="Identifiant" required aria-label="Identifiant" />
				<label><input type="checkbox" bind:checked={newAdmin} /> administrateur</label>
				<button class="secondary" type="submit">Créer</button>
			</form>
			{#if created}
				<div class="banner good">
					<strong>Compte {created.login} créé. Transmets ce mot de passe initial par un canal sûr ; il ne sera plus affiché.</strong>
					<p class="secret">{created.password}</p>
				</div>
			{/if}
			<table>
				<thead><tr><th>Identifiant</th><th>Rôle</th><th>État</th><th>Créé</th><th></th></tr></thead>
				<tbody>
					{#each users as user (user.id)}
						<tr>
							<td>{user.login}</td><td>{user.is_admin ? 'administrateur' : 'étudiant'}</td>
							<td>{user.disabled ? 'désactivé' : 'actif'}</td><td>{formatDate(user.created_at)}</td>
							<td>{#if !user.disabled && user.login !== session.me?.login}<button type="button" class="link danger" onclick={() => disable(user)}>Désactiver</button>{/if}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</section>
	{/if}
</main>
