<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import { createDbCreateStore, provideDbCreate, DB_TABS } from '$lib/stores/dbCreateStore.svelte';
	import DbCreateStep1Details from './wizard/DbCreateStep1Details.svelte';
	import DbCreateStep2Networking from './wizard/DbCreateStep2Networking.svelte';
	import DbCreateStep3Access from './wizard/DbCreateStep3Access.svelte';
	import DbCreateStep4Init from './wizard/DbCreateStep4Init.svelte';
	import DbCreateStep5Advanced from './wizard/DbCreateStep5Advanced.svelte';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { ActivityIndicator, Alert, Button, ProgressTrack } from '$lib/components/ui';

	let {
		open = $bindable(false),
		onCreated,
		initialNetworkId = null,
	}: {
		open: boolean;
		onCreated: () => void;
		initialNetworkId?: string | null;
	} = $props();

	const s = createDbCreateStore({
		open: () => open,
		setOpen: (v) => { open = v; },
		onCreated: () => onCreated(),
		initialNics: () => (initialNetworkId ? [initialNetworkId] : []),
	});
	provideDbCreate(s);
</script>

{#if open}
	<!-- 오버레이 -->
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => (open = false) }}
		class="motion-fade fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={(event) => {
			if (event.target === event.currentTarget) open = false;
		}}
		tabindex="-1"
		role="dialog"
		aria-modal="true"
		aria-label={tr('wizard.title')}
	>
		<div
			class="motion-pop bg-surface-base border border-line-2 rounded-xl w-full max-w-2xl mx-4 shadow-[var(--shadow-restraint)] flex flex-col max-h-[90vh]"
		>
			<!-- 헤더 -->
			<div class="flex items-center justify-between px-6 py-4 border-b border-line">
				<h2 class="text-base font-semibold text-ink-0">{tr('wizard.title')}</h2>
				<button
					onclick={() => (open = false)}
					class="text-ink-2 hover:text-ink-0 text-xl leading-none">&times;</button
				>
			</div>

			<!-- 탭 네비게이션 -->
			<div class="flex border-b border-line px-6 gap-0 overflow-x-auto">
				{#each DB_TABS as tab, i}
					<button
						onclick={() => (s.activeTab = i)}
						class="text-xs py-3 px-4 border-b-2 whitespace-nowrap transition-colors
							{s.activeTab === i
							? 'border-action-warm text-warm-text font-medium'
							: 'border-transparent text-ink-2 hover:text-ink-2'}"
					>
						{tab}
						{#if i === 0 && s.step1Error && s.name}
							<span class="ml-1 text-red-400">*</span>
						{/if}
					</button>
				{/each}
			</div>

			<!-- 탭 콘텐츠 -->
			<div class="flex-1 overflow-y-auto px-6 py-5">
				{#if s.loading}
					<ActivityIndicator label={tr('wizard.loading')} />
				{:else if s.error}
					<Alert tone="danger">{s.error}</Alert>
				{:else if s.activeTab === 0}
					<DbCreateStep1Details />
				{:else if s.activeTab === 1}
					<DbCreateStep2Networking />
				{:else if s.activeTab === 2}
					<DbCreateStep3Access />
				{:else if s.activeTab === 3}
					<DbCreateStep4Init />
				{:else}
					<DbCreateStep5Advanced />
				{/if}
			</div>

			<!-- 에러 + 액션 -->
			<div class="px-6 py-4 border-t border-line space-y-3">
				{#if s.creating}<ProgressTrack value={null} active label={tr('wizard.title')} />{/if}
				{#if s.createError}
					<Alert tone="danger" class="whitespace-pre-wrap break-all">{s.createError}</Alert>
				{:else if s.step1Error && s.activeTab !== 0}
					<div class="text-warm-text text-xs">{s.step1Error}</div>
				{/if}
				<div class="flex items-center justify-between">
					<div class="flex gap-2">
						{#if s.activeTab > 0}
							<button
								onclick={() => (s.activeTab -= 1)}
								class="text-xs text-ink-2 hover:text-ink-0 px-3 py-1.5 border border-line-2 rounded-lg"
							>
								{tr('actions.previous')}
							</button>
						{/if}
						{#if s.activeTab < DB_TABS.length - 1}
							<button
								onclick={() => (s.activeTab += 1)}
								class="text-xs text-warm-text hover:text-warm-text-hover px-3 py-1.5 border border-action-warm rounded-lg"
							>
								{tr('actions.next')}
							</button>
						{/if}
					</div>
					<div class="flex gap-2">
						<button
							onclick={() => (open = false)}
							class="text-xs text-ink-2 hover:text-ink-0 px-4 py-1.5 border border-line-2 rounded-lg"
						>
							{tr('actions.cancel')}
						</button>
						<Button
							size="sm"
							onclick={s.createInstance}
							disabled={s.creating || !s.canCreate}
							ariaBusy={s.creating}
							title={s.step1Error || ''}
						>
							{#if s.creating}<ActivityIndicator size="xs" tone="ink" />{tr('state.creating')}{:else}{tr('actions.create')}{/if}
						</Button>
					</div>
				</div>
			</div>
		</div>
	</div>
{/if}
