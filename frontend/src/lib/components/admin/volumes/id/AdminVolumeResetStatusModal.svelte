<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
		import { dialogFocus } from '$lib/utils/dialogFocus';

	let {
		open = $bindable(),
		resetting,
		onReset,
	}: {
		open: boolean;
		resetting: boolean;
		onReset: (status: string) => Promise<boolean>;
	} = $props();

	let resetStatus = $state('available');

	$effect(() => {
		if (!open) {
			resetStatus = 'available';
		}
	});
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => (open = false) }}
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={(event) => { if (event.target === event.currentTarget) (() => { open = false; })(); }}
		role="dialog" aria-modal="true"
		tabindex="-1"
	>
		<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]">
			<h2 class="text-lg font-semibold text-ink-0 mb-4">{t('volumeDetail.resetStatus')}</h2>
			<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminvolumeresetstatusmodal-31">{t('volumeDetail.targetStatus')}</label>
			<select id="field-adminvolumeresetstatusmodal-31" bind:value={resetStatus} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mb-4">
				<option value="available">{t('volumeDetail.statusAvailable')}</option>
				<option value="error">{t('volumeDetail.statusError')}</option>
				<option value="in-use">{t('volumeDetail.statusInUse')}</option>
			</select>
			<div class="flex gap-3 justify-end">
				<button onclick={() => { open = false; }} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0">{t('volumeDetail.cancel')}</button>
				<button
					onclick={async () => {
						const ok = await onReset(resetStatus);
						if (ok) open = false;
					}}
					disabled={resetting}
					class="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 text-ink-0 text-sm rounded-lg disabled:opacity-30"
				>
					{#if resetting}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{t('volumeDetail.processing')}</span></span>{:else}{t('volumeDetail.reset')}{/if}
				</button>
			</div>
		</div>
	</div>
{/if}
