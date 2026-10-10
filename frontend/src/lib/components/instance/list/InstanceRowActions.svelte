<script lang="ts">
	import { t } from '$lib/i18n/ns/instance';
	import type { Instance } from '$lib/types/compute';
	import ActionMenu from '$lib/components/ui/ActionMenu.svelte';

	let {
		instance,
		onAction,
		acting = $bindable(false),
	}: {
		instance: Instance;
		onAction: (kind: 'console' | 'shelve' | 'unshelve' | 'delete', instance: Instance) => Promise<void>;
		acting?: boolean;
	} = $props();

	let open = $state(false);

	async function act(kind: 'console' | 'shelve' | 'unshelve' | 'delete') {
		open = false;
		acting = true;
		try {
			await onAction(kind, instance);
		} finally {
			acting = false;
		}
	}
</script>

<td class="text-right">
	<ActionMenu
		{open}
		ariaLabel={t('rowActions.instanceActions', { name: instance.name || instance.id })}
		onopen={() => { open = true; }}
		onclose={() => { open = false; }}
	>
		{#if instance.status === 'ACTIVE'}
			<button onclick={() => act('console')} class="w-full text-left px-3 py-1.5 text-xs text-ink-2 hover:bg-surface-sunken hover:text-ink-0 transition-colors">{t('rowActions.console')}</button>
		{/if}
		{#if instance.status === 'ACTIVE' || instance.status === 'SHUTOFF'}
			<button onclick={() => act('shelve')} class="w-full text-left px-3 py-1.5 text-xs text-purple-400 hover:bg-surface-sunken hover:text-purple-300 transition-colors">{t('rowActions.shelve')}</button>
		{/if}
		{#if instance.status === 'SHELVED_OFFLOADED' || instance.status === 'SHELVED'}
			<button onclick={() => act('unshelve')} class="w-full text-left px-3 py-1.5 text-xs text-green-400 hover:bg-surface-sunken hover:text-green-300 transition-colors">{t('rowActions.unshelve')}</button>
		{/if}
		<button onclick={() => act('delete')} disabled={acting} class="w-full text-left px-3 py-1.5 text-xs text-red-400 hover:bg-surface-sunken hover:text-red-300 disabled:text-ink-3 transition-colors">
			{acting ? t('rowActions.processing') : t('rowActions.delete')}
		</button>
	</ActionMenu>
</td>
