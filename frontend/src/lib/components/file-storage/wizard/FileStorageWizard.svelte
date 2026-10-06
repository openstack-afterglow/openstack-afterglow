<script lang="ts">
	import { createFileStorageWizardStore, provideFsWizard } from '$lib/stores/fileStorageWizardStore.svelte';
	import FileStorageWizardStep1 from './FileStorageWizardStep1.svelte';
	import FileStorageWizardStep2 from './FileStorageWizardStep2.svelte';
	import FileStorageWizardStep3 from './FileStorageWizardStep3.svelte';
	import { betaFeatures } from '$lib/stores/betaFeatures';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/file-storage';
	import { t as tc } from '$lib/i18n/ns/common';

	let {
		open = $bindable(false),
		onCreated,
	}: {
		open: boolean;
		onCreated: () => void;
	} = $props();

	const s = createFileStorageWizardStore({
		open: () => open,
		setOpen: (v) => { open = v; },
		onCreated: () => onCreated(),
		fileStorageShareNetworksEnabled: () => $betaFeatures.fileStorageShareNetworks,
	});
	provideFsWizard(s);
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => s.closeWizard() }}
		class="motion-fade fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={s.closeWizard}
		role="dialog" aria-modal="true" tabindex="-1"
	>
		<div
			class="motion-pop bg-surface-base border border-line-2 rounded-xl w-full max-w-xl mx-4 shadow-[var(--shadow-restraint)] max-h-[90vh] overflow-y-auto"
			onclick={(e) => e.stopPropagation()}
			role="none"
		>
			<!-- 스텝 인디케이터: DHSS=False이거나 Share Network 베타가 꺼져 있으면 네트워크 단계를 숨겨 2단계로 표시 -->
			<div class="flex items-center gap-0 px-6 pt-6 pb-4 border-b border-line">
				{#each (s.dhssEnabled && s.shareNetworksEnabled
					? [{ step: 1, label: t('wizard.steps.basic') }, { step: 2, label: t('wizard.steps.network') }, { step: 3, label: t('wizard.steps.access') }]
					: [{ step: 1, label: t('wizard.steps.basic') }, { step: 3, label: t('wizard.steps.access') }]
				) as item, idx (item.step)}
					{@const isLast = idx === (s.dhssEnabled && s.shareNetworksEnabled ? 2 : 1)}
					<div class="flex items-center {!isLast ? 'flex-1' : ''}">
						<div class="flex flex-col items-center">
							<div class="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-colors
								{s.step === item.step ? 'border-action-warm bg-surface-selected/40 text-warm-text' :
								 s.step > item.step ? 'border-[var(--color-state-success)] bg-[color-mix(in_oklab,var(--color-state-success)_14%,transparent)] text-[var(--color-state-success-text)]' :
								 'border-line-2 bg-surface-sunken text-ink-2'}">
								{#if s.step > item.step}
									<svg class="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
										<path class="motion-draw" pathLength="1" d="M3.5 8.5l3 3 6-7" />
									</svg>
									<span class="sr-only">{tc('stepProgress.done')}</span>
								{:else}
									{idx + 1}
								{/if}
							</div>
							<span class="text-xs mt-1 {s.step === item.step ? 'text-warm-text' : s.step > item.step ? 'text-[var(--color-state-success-text)]' : 'text-ink-2'}">{item.label}</span>
						</div>
						{#if !isLast}
							<div class="flex-1 h-px mx-3 mt-[-14px] {s.step > item.step ? 'bg-[var(--color-state-success)]' : 'bg-surface-selected'}"></div>
						{/if}
					</div>
				{/each}
			</div>

			<div class="p-6">
				{#if s.step === 1}
					<FileStorageWizardStep1 />
				{:else if s.step === 2}
					<FileStorageWizardStep2 />
				{:else if s.step === 3 && s.createdFs}
					<FileStorageWizardStep3 />
				{/if}
			</div>
		</div>
	</div>
{/if}
