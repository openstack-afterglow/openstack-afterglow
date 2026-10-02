<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import { formatNumber } from '$lib/utils/format';
	import { dialogFocus } from '$lib/utils/dialogFocus';

	let {
		open = $bindable(),
		currentSize,
		extending,
		onExtend,
	}: {
		open: boolean;
		currentSize: number;
		extending: boolean;
		onExtend: (newSize: number) => Promise<boolean>;
	} = $props();

	let newSize = $state(0);

	$effect(() => {
		if (open) {
			newSize = currentSize + 10;
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
			<h2 class="text-lg font-semibold text-ink-0 mb-4">{t('volumeDetail.extendTitle')}</h2>
			<p class="text-sm text-ink-2 mb-4">{t('volumeDetail.currentSize', { size: formatNumber(currentSize) })}</p>
			<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminvolumeextendmodal-36">{t('volumeDetail.newSize')}</label>
			<input id="field-adminvolumeextendmodal-36" bind:value={newSize} type="number" min={currentSize + 1} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mb-4" />
			<div class="flex gap-3 justify-end">
				<button onclick={() => { open = false; }} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0">{t('volumeDetail.cancel')}</button>
				<button
					onclick={async () => {
						const ok = await onExtend(newSize);
						if (ok) open = false;
					}}
					disabled={extending}
					class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm rounded-lg disabled:opacity-30"
				>
					{extending ? t('volumeDetail.extending') : t('volumeDetail.extend')}
				</button>
			</div>
		</div>
	</div>
{/if}
