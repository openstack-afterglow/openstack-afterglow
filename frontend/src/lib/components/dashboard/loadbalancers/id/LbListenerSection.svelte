<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import { t as tc } from '$lib/i18n/ns/common';
	import type { Listener, Pool } from '$lib/types/loadbalancer';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { createPendingAction } from '$lib/components/network/pendingAction.svelte';
	import { CompactResourceCard, Button, StatusChip } from '$lib/components/ui';

	let {
		listeners,
		pools,
		saving,
		error,
		onAdd,
		onDelete,
	}: {
		listeners: Listener[];
		pools: Pool[];
		saving: boolean;
		error: string;
		onAdd: (form: { protocol: string; protocol_port: number; name: string }) => Promise<boolean>;
		onDelete: (id: string) => Promise<void>;
	} = $props();

	let showAddListener = $state(false);
	let listenerForm = $state({ protocol: 'HTTP', protocol_port: 80, name: '' });
	const pending = createPendingAction();
	const creatingListener = $derived(pending.isActive('create', saving));

	async function handleAdd() {
		const ok = await pending.run('create', () => onAdd(listenerForm));
		if (ok) {
			showAddListener = false;
			listenerForm = { protocol: 'HTTP', protocol_port: 80, name: '' };
		}
	}
</script>

<section class="bg-surface-base border border-line rounded-lg p-5 mb-4">
	<div class="flex items-center justify-between mb-4">
		<h2 class="font-semibold text-ink-0">{t('lb.listeners.title', { count: listeners.length })}</h2>
		<button onclick={() => showAddListener = !showAddListener} class="text-warm-text hover:text-warm-text-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors">{t('lb.actions.addWithPlus')}</button>
	</div>

	{#if showAddListener}
		<div class="motion-enter mb-4 p-4 bg-surface-sunken/60 border border-line-2 rounded-lg grid grid-cols-1 sm:grid-cols-3 gap-2">
			<input bind:value={listenerForm.name} placeholder={t('lb.form.optionalName')} class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1" />
			<select bind:value={listenerForm.protocol} class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1">
				{#each ['HTTP', 'HTTPS', 'TCP', 'UDP'] as p}
					<option value={p}>{p}</option>
				{/each}
			</select>
			<input bind:value={listenerForm.protocol_port} type="number" min="1" max="65535" placeholder={t('lb.form.port')} class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1" />
			<button onclick={handleAdd} disabled={saving} aria-busy={creatingListener} class="sm:col-span-2 inline-flex items-center justify-center gap-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected text-ink-0 text-sm px-3 py-2 rounded">{#if creatingListener}<ActivityIndicator size="xs" tone="ink" />{/if}{creatingListener ? tc('state.processing') : t('lb.actions.create')}</button>
			<button onclick={() => showAddListener = false} class="text-ink-2 hover:text-ink-1 text-sm px-2 text-center">{t('lb.actions.cancel')}</button>
		</div>
	{/if}

	{#if listeners.length === 0}
		<p class="text-sm text-ink-2">{t('lb.listeners.empty')}</p>
	{:else}
		<div class="space-y-2">
			{#each listeners as l}
				{@const deletingListener = pending.isActive(`delete:${l.id}`, saving)}
				<CompactResourceCard>
					<div class="flex items-center gap-2"><strong class="min-w-0 flex-1 break-all">{l.name || l.id.slice(0, 10)}</strong><StatusChip status={l.status} /></div>
					<p class="font-mono text-xs text-ink-2">{l.protocol}:{l.protocol_port}</p>
					{#snippet details()}<p class="font-mono break-all">ID: {l.id}</p>{/snippet}
					{#snippet actions()}<Button variant="danger-outline" size="sm" onclick={() => pending.run(`delete:${l.id}`, () => onDelete(l.id))} disabled={saving} ariaBusy={deletingListener}>{#if deletingListener}<ActivityIndicator size="xs" tone="danger" />{/if}{deletingListener ? t('network.actions.deleting') : t('lb.actions.delete')}</Button>{/snippet}
				</CompactResourceCard>
			{/each}
		</div>
	{/if}
</section>
