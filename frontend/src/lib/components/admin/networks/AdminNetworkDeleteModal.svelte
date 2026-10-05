<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-network';
	import RichText from '$lib/i18n/RichText.svelte';
	import type { AdminNetwork } from '$lib/types/networks';
	import { dialogFocus } from '$lib/utils/dialogFocus';

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
		use:dialogFocus={{ enabled: true, onEscape: () => onClose() }}
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={(event) => { if (event.target === event.currentTarget) (onClose)(); }}
		role="dialog" aria-modal="true"
		tabindex="-1"
	>
		<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]">
			<h2 class="text-lg font-semibold text-ink-0 mb-3">{t('adminNetworkDeleteModal.title')}</h2>
			{#snippet networkName(text: string)}<span class="text-ink-0">{text}</span>{/snippet}
			<p class="text-sm text-ink-2 mb-4"><RichText segments={t.rich('adminNetworkDeleteModal.confirmation', { name: network.name || network.id.slice(0, 8) })} tags={{ name: networkName }} /></p>
			{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
			<div class="flex justify-end gap-3">
				<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{t('adminNetworkDeleteModal.cancel')}</button>
				<button onclick={confirm} disabled={deleting} class="px-4 py-2 bg-red-600 hover:bg-red-500 text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">
					{deleting ? t('adminNetworkDeleteModal.deleting') : t('adminNetworkDeleteModal.delete')}
				</button>
			</div>
		</div>
	</div>
{/if}
