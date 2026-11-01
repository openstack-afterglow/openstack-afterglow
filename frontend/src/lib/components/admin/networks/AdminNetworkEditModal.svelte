<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/admin-network';
	import { Alert, Button, Field, TextInput } from '$lib/components/ui';
	import type { AdminNetwork } from '$lib/types/networks';
	import { dialogFocus } from '$lib/utils/dialogFocus';

	let {
		network,
		onClose,
		onSave,
	}: {
		network: AdminNetwork | null;
		onClose: () => void;
		onSave: (id: string, form: { name: string; is_shared: boolean }) => Promise<string | true>;
	} = $props();

	let editName = $state('');
	let editShared = $state(false);
	let saving = $state(false);
	let error = $state('');

	$effect(() => {
		if (network) {
			editName = network.name;
			editShared = network.is_shared;
			error = '';
			saving = false;
		}
	});

	async function save() {
		if (!network) return;
		saving = true;
		error = '';
		const result = await onSave(network.id, { name: editName, is_shared: editShared });
		if (result === true) {
			onClose();
		} else {
			error = result;
		}
		saving = false;
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
		<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
			<h2 class="text-lg font-semibold text-ink-0 mb-5">{t('adminNetworkEditModal.title')}</h2>
			{#if error}<Alert tone="danger">{error}</Alert>{/if}
			<div class="space-y-4">
				<Field label={t('adminNetworkEditModal.name')} for="field-adminnetworkeditmodal-55"><TextInput id="field-adminnetworkeditmodal-55" bind:value={editName} disabled={saving} /></Field>
				<label class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer">
					<input type="checkbox" bind:checked={editShared} class="rounded" /> {t('adminNetworkEditModal.shared')}
				</label>
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<Button variant="secondary" disabled={saving} onclick={onClose}>{t('adminNetworkEditModal.cancel')}</Button>
				<Button variant="primary" ariaBusy={saving} onclick={save} disabled={saving}>{#if saving}<LoadingState variant="control" label="" aria-hidden="true" />{/if}{saving ? t('adminNetworkEditModal.saving') : t('adminNetworkEditModal.save')}</Button>
			</div>
		</div>
	</div>
{/if}
