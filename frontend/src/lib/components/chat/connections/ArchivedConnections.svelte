<script lang="ts">
	import { onDestroy, tick } from 'svelte';
	import { api } from '$lib/api/client';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { chatDomainScope } from '$lib/stores/chatDomainScope';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t } from '$lib/i18n/ns/mcp-gallery';
	import Button from '$lib/components/ui/Button.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';

	let { domainId, onRestored }: { domainId?: string; onRestored: () => Promise<void> } = $props();
	interface ArchivedConnection {
		id: number;
		kind: 'mcp' | 'tool';
		original_id: number;
		name: string;
		archived_at: string;
	}
	const base = $derived(domainId
		? `/api/v1/chat/domains/${encodeURIComponent(domainId)}/archived-connections`
		: '/api/v1/chat/archived-connections');
	const ready = $derived($authReady && !$projectSwitching && !!$auth.token && !!$auth.projectId);
	let items = $state<ArchivedConnection[] | null>(null);
	const pageSize = 100;
	let beforeId = $state<number | null>(null);
	let loading = $state(false);
	let restoring = $state<number | null>(null);
	let error = $state('');
	let restoredName = $state('');
	let summary = $state<HTMLElement>();
	let pending: AbortController | null = null;
	onDestroy(() => pending?.abort());

	async function load(cursor: number | null = null) {
		if (!ready || pending) return;
		const owner = $chatDomainScope;
		const controller = new AbortController();
		pending = controller;
		const current = () => owner === $chatDomainScope && !controller.signal.aborted;
		loading = true;
		error = '';
		try {
			const path = cursor === null ? base : `${base}?before_id=${cursor}`;
			const result = await api.get<{ items: ArchivedConnection[] }>(path, $auth.token!, $auth.projectId!, { refresh: true, signal: controller.signal });
			if (!current()) return;
			items = cursor === null ? result.items : [...(items ?? []), ...result.items];
			beforeId = result.items.length === pageSize ? result.items.at(-1)!.id : null;
		} catch {
			if (current()) error = t('archive.loadFailed');
		} finally {
			if (pending === controller) pending = null;
			if (current()) loading = false;
		}
	}

	async function restore(item: ArchivedConnection) {
		if (!ready || pending) return;
		const owner = $chatDomainScope;
		const controller = new AbortController();
		const current = () => owner === $chatDomainScope && !controller.signal.aborted;
		pending = controller;
		restoring = item.id;
		error = '';
		restoredName = '';
		try {
			await api.post(`${base}/${item.id}/restore`, undefined, $auth.token!, $auth.projectId!, { signal: controller.signal });
			if (!current()) return;
			items = items?.filter(({ id }) => id !== item.id) ?? null;
			restoredName = item.name;
			summary?.focus();
		} catch {
			if (current()) error = t('archive.restoreFailed');
			return;
		} finally {
			if (pending === controller) pending = null;
			if (current()) restoring = null;
		}
		await tick();
		if (current()) await onRestored();
	}
</script>

<details class="archive" ontoggle={(event) => { if (event.currentTarget.open && items === null && !error) void load(); }}>
	<summary bind:this={summary}>{t(domainId ? 'archive.organization' : 'archive.personal')}</summary>
	<p>{t('archive.description')}</p>
	{#if loading}<LoadingState variant="inline" label={t('loading')} />{/if}
	<p role="status">{error || (restoredName ? t('archive.restored', { name: restoredName }) : '')}</p>
	{#if error && items === null}
		<Button variant="outline" size="sm" disabled={!ready || loading} onclick={() => load()}>{t('refresh')}</Button>
	{:else if items?.length}
		<ul role="list">
			{#each items as item (item.id)}
				<li>
					<div>
						<strong>{item.name}</strong>
						<p>{t(item.kind === 'mcp' ? 'archive.mcp' : 'archive.tool')} #{item.original_id} · <time datetime={item.archived_at}>{new Date(item.archived_at).toLocaleString(intlLocale())}</time></p>
					</div>
					<Button variant="outline" size="sm" disabled={!ready || loading || restoring !== null} ariaLabel={t('archive.restoreNamed', { name: `${item.name} #${item.original_id}` })}
						onclick={() => restore(item)}>{t('archive.restore')}</Button>
				</li>
			{/each}
		</ul>
	{:else if items}
		<p>{t('archive.empty')}</p>
	{/if}
	{#if beforeId !== null}
		<Button variant="outline" size="sm" disabled={!ready || loading || restoring !== null} onclick={() => load(beforeId)}>{t('workspace.more')}</Button>
	{/if}
</details>

<style>
	.archive { border-top: 1px solid var(--color-line); padding-block: 0.75rem; }
	summary { cursor: pointer; font-weight: 600; }
	p { margin: 0.25rem 0; color: var(--color-ink-2); font-size: var(--type-support); }
	p:empty { margin: 0; }
	[role='status']:not(:empty) { color: var(--color-ink-1); }
	ul { list-style: none; padding-inline-start: 0; }
	li { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem; padding-block: 0.5rem; }
	li + li { border-top: 1px solid var(--color-line); }
	li > div { min-width: 0; overflow-wrap: anywhere; }
</style>
