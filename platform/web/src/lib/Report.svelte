<script lang="ts">
	import type { Report, Row } from './api';
	import { STATUS, STATUS_ORDER, checkLabel } from './labels';

	let { report }: { report: Report } = $props();

	const summary = $derived(report.summary ?? {});
	const hasProblems = $derived(STATUS_ORDER.some((s) => STATUS[s].problem && summary[s]));
	// Comme le rapport texte compact : les problèmes d'abord, tout si rien n'échoue.
	let filters = $state<Set<string> | null>(null);
	let query = $state('');
	const active = $derived(
		filters ?? new Set(hasProblems ? STATUS_ORDER.filter((s) => STATUS[s].problem || s === 'manual') : STATUS_ORDER)
	);

	function toggle(status: string) {
		const next = new Set(active);
		if (next.has(status)) next.delete(status);
		else next.add(status);
		filters = next;
	}

	function matches(row: Row): boolean {
		if (!query.trim()) return true;
		const text = [row.file, row.check, checkLabel(row.check), row.message, row.raw_message ?? ''].join('\n').toLowerCase();
		return query.toLowerCase().split(/\s+/).filter(Boolean).every((word) => text.includes(word));
	}

	const rank = (row: Row) => STATUS_ORDER.indexOf(row.status);
	const groups = $derived.by(() => {
		const map = new Map<string, Row[]>();
		for (const row of report.results) {
			if (!active.has(row.status) || !matches(row)) continue;
			if (!map.has(row.file)) map.set(row.file, []);
			map.get(row.file)!.push(row);
		}
		return [...map.entries()]
			.map(([file, rows]) => [file, rows.sort((a, b) => rank(a) - rank(b) || a.line - b.line)] as const)
			.sort(([a, ra], [b, rb]) => Math.min(...ra.map(rank)) - Math.min(...rb.map(rank)) || a.localeCompare(b));
	});
</script>

<div class="toolbar">
	<div class="chips" role="group" aria-label="Filtrer par statut">
		{#each STATUS_ORDER.filter((s) => summary[s]) as status (status)}
			<button type="button" class="chip status-{status}" aria-pressed={active.has(status)} onclick={() => toggle(status)}>
				<span class="count">{summary[status]}</span>
				{summary[status] > 1 ? STATUS[status].plural : STATUS[status].label}
			</button>
		{/each}
		<button type="button" class="link" onclick={() => (filters = new Set(STATUS_ORDER))}>Tout afficher</button>
	</div>
	<input type="search" class="search" placeholder="Filtrer par fichier, contrôle ou message…" bind:value={query} aria-label="Rechercher dans les résultats" />
</div>

<div class="rows">
	{#each groups as [file, rows] (file)}
		<section class="file">
			<h3><span class="path">{file}</span><span class="muted">{rows.length} résultat{rows.length > 1 ? 's' : ''}</span></h3>
			{#each rows as row, index (index)}
				<article class="row status-{row.status}">
					<div class="row-head">
						<span class="badge status-{row.status}">{STATUS[row.status]?.label ?? row.status}</span>
						<span class="row-label">{checkLabel(row.check)}</span>
						<code class="muted">{row.check}</code>
						{#if row.line > 1 || row.column > 1}
							<span class="muted location">ligne {row.line}, col. {row.column}</span>
						{/if}
					</div>
					<pre class="message">{row.message}</pre>
					{#if row.raw_message || (row.diagnostics && row.diagnostics.length > 1)}
						<details>
							<summary>Détails</summary>
							{#if row.raw_message}
								<p class="sub">Diagnostic brut</p>
								<pre>{row.raw_message}</pre>
							{/if}
							{#if row.diagnostics && row.diagnostics.length > 1}
								<p class="sub">Emplacements</p>
								<ul class="locations">
									{#each row.diagnostics as d, i (i)}
										<li class="mono">{d.file}:{d.line}:{d.column}</li>
									{/each}
								</ul>
							{/if}
						</details>
					{/if}
				</article>
			{/each}
		</section>
	{:else}
		<p class="empty">Aucun résultat ne correspond aux filtres.</p>
	{/each}
</div>
