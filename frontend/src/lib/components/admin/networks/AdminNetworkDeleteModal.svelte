<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/admin-network';
	import RichText from '$lib/i18n/RichText.svelte';
	import type { AdminNetwork } from '$lib/types/networks';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { Alert, Button, ResourceIdentifier } from '$lib/components/ui';

	let {
		network,
		onClose,
		onDelete,
	}: {
		network: AdminNetwork | null;
		onClose: () => void;
		onDelete: (id: string) => Promise<string | true>;
	} = $props();

	let deleting = $state(false);
	let error = $state('');

	$effect(() => {
		if (network) { error = ''; deleting = false; }
	});

	async function confirm() {
		if (!network) return;
		deleting = true;
		error = '';
		const result = await onDelete(network.id);
		if (result === true) {
			onClose();
		} else {
			error = result;
		}
		deleting = false;
	}
</script>

{#if network}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => { if (!deleting) onClose(); } }}
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={(event) => { if (!deleting && event.target === event.currentTarget) onClose(); }}
		role="dialog" aria-modal="true"
		tabindex="-1"
	>
		<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]">
			<h2 class="text-lg font-semibold text-ink-0 mb-3">{t('adminNetworkDeleteModal.title')}</h2>
			{#snippet networkName(text: string)}<span class="text-ink-0">{text}</span>{/snippet}
			<p class="text-sm text-ink-2 mb-4"><RichText segments={t.rich('adminNetworkDeleteModal.confirmation', { name: network.name || network.id.slice(0, 8) })} tags={{ name: networkName }} /></p>
			<ResourceIdentifier id={network.id} compact={false} />
			<p class="mt-3 mb-4 text-sm text-ink-2">{t('list.deleteImpact')}</p>
			{#if error}<Alert tone="danger">{error}</Alert>{/if}
			<div class="flex justify-end gap-3">
				<Button variant="secondary" disabled={deleting} onclick={onClose}>{t('adminNetworkDeleteModal.cancel')}</Button>
				<Button variant="danger" ariaBusy={deleting} onclick={confirm} disabled={deleting} dataTour="admin-networks-delete-confirm">{#if deleting}<LoadingState variant="control" label="" aria-hidden="true" />{/if}{deleting ? t('adminNetworkDeleteModal.deleting') : t('adminNetworkDeleteModal.delete')}</Button>
			</div>
		</div>
	</div>
{/if}
