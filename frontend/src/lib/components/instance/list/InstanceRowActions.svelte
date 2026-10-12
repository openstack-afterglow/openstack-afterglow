<script lang="ts">
	import { t } from '$lib/i18n/ns/instance';
	import type { Instance } from '$lib/types/compute';
	import ActionMenu from '$lib/components/ui/ActionMenu.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import { canWrite } from '$lib/stores/auth';

	let {
		instance,
		onAction,
		acting = $bindable(false),
	}: {
		instance: Instance;
		onAction: (kind: 'console' | 'shelve' | 'unshelve' | 'delete' | 'start' | 'stop', instance: Instance) => Promise<void>;
		acting?: boolean;
	} = $props();

	let open = $state(false);

	async function act(kind: 'console' | 'shelve' | 'unshelve' | 'delete' | 'start' | 'stop') {
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
			<Button onclick={() => act('console')} disabled={acting} variant="ghost" size="sm" class="w-full justify-start">{t('rowActions.console')}</Button>
			{#if $canWrite}
				<Button onclick={() => act('stop')} disabled={acting} variant="ghost" size="sm" class="w-full justify-start">{t('list.stop')}</Button>
			{/if}
		{:else if instance.status === 'SHUTOFF' && $canWrite}
			<Button onclick={() => act('start')} disabled={acting} variant="ghost" size="sm" class="w-full justify-start">{t('list.start')}</Button>
			<Button onclick={() => act('shelve')} disabled={acting} variant="ghost" size="sm" class="w-full justify-start">{t('rowActions.shelve')}</Button>
			<Button onclick={() => act('delete')} disabled={acting} variant="danger-outline" size="sm" class="w-full justify-start">{t('rowActions.delete')}</Button>
		{:else if (instance.status === 'SHELVED_OFFLOADED' || instance.status === 'SHELVED') && $canWrite}
			<Button onclick={() => act('unshelve')} disabled={acting} variant="ghost" size="sm" class="w-full justify-start">{t('rowActions.unshelve')}</Button>
		{/if}
	</ActionMenu>
</td>
