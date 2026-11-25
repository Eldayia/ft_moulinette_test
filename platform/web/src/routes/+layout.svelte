<script lang="ts">
	import '../app.css';
	import favicon from '#lib/assets/favicon.svg';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { api } from '#lib/api.ts';
	import { refreshSession, session } from '#lib/session.svelte.ts';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	onMount(async () => {
		await refreshSession();
		if (!session.me && page.url.pathname !== '/login') await goto('/login');
	});

	async function logout() {
		await api.post('/api/auth/logout');
		session.me = null;
		await goto('/login');
	}

	const links = $derived([
		{ href: '/', label: 'Soumettre' },
		{ href: '/tokens', label: 'Jetons' },
		{ href: '/account', label: 'Compte' },
		...(session.me?.is_admin ? [{ href: '/admin', label: 'Administration' }] : [])
	]);
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>ft-moulinette</title>
</svelte:head>

<header class="top">
	<div class="brand">
		<span class="logo" aria-hidden="true">ft</span>
		<div>
			<h1>ft-moulinette</h1>
			<p>Prévalidation Libft 1.3 · Printf 1.1</p>
		</div>
	</div>
	{#if session.me}
		<nav class="nav" aria-label="Navigation principale">
			{#each links as link (link.href)}
				<a href={link.href} aria-current={page.url.pathname === link.href ? 'page' : undefined}>{link.label}</a>
			{/each}
			<span class="muted">{session.me.login}</span>
			<button type="button" onclick={logout}>Déconnexion</button>
		</nav>
	{/if}
</header>

{#if session.me && session.status && !session.status.executions_enabled}
	<div class="page"><div class="banner warn" role="status"><strong>Maintenance.</strong> {session.status.message}</div></div>
{/if}

{#if session.ready}
	{@render children()}
{/if}

<footer class="foot">
	Un rapport sans problème signalé ne certifie pas la conformité au sujet. Le code est compilé et exécuté dans un environnement isolé sur Google Cloud, jamais sur ce serveur.
</footer>
