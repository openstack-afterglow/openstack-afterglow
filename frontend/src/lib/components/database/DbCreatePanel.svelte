<script lang="ts">
	import { createDbCreateStore, provideDbCreate, DB_TABS } from '$lib/stores/dbCreateStore.svelte';
	import DbCreateStep1Details from './wizard/DbCreateStep1Details.svelte';
	import DbCreateStep2Networking from './wizard/DbCreateStep2Networking.svelte';
	import DbCreateStep3Access from './wizard/DbCreateStep3Access.svelte';
	import DbCreateStep4Init from './wizard/DbCreateStep4Init.svelte';
	import DbCreateStep5Advanced from './wizard/DbCreateStep5Advanced.svelte';
	import { betaFeatures } from '$lib/stores/betaFeatures';

	let {
		open = $bindable(false),
		onCreated,
	}: {
		open: boolean;
		onCreated: () => void;
	} = $props();

	const s = createDbCreateStore({
		open: () => open,
		setOpen: (v) => { open = v; },
		onCreated: () => onCreated(),
		databaseBackupsEnabled: () => $betaFeatures.databaseBackups,
	});
	provideDbCreate(s);
</script>

{#if open}
	<!-- 오버레이 -->
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={(event) => {
			if (event.target === event.currentTarget) open = false;
		}}
		onkeydown={(event) => event.key === 'Escape' && (open = false)}
		tabindex="-1"
		role="dialog"
		aria-modal="true"
		aria-label="DB 인스턴스 생성"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl w-full max-w-2xl mx-4 shadow-[var(--shadow-restraint)] flex flex-col max-h-[90vh]"
		>
			<!-- 헤더 -->
			<div class="flex items-center justify-between px-6 py-4 border-b border-line">
				<h2 class="text-base font-semibold text-ink-0">DB 인스턴스 생성</h2>
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
							? 'border-action-warm text-action-warm font-medium'
							: 'border-transparent text-ink-3 hover:text-ink-2'}"
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
					<p class="text-ink-2 text-sm">메타데이터 불러오는 중...</p>
				{:else if s.error}
					<div class="bg-red-900/20 border border-red-800 rounded-lg px-3 py-2 text-red-400 text-xs">
						{s.error}
					</div>
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
				{#if s.createError}
					<div class="bg-red-900/20 border border-red-800 rounded-lg px-3 py-2 text-red-400 text-xs whitespace-pre-wrap break-all">
						{s.createError}
					</div>
				{:else if s.step1Error && s.activeTab !== 0}
					<div class="text-action-warm text-xs">{s.step1Error}</div>
				{/if}
				<div class="flex items-center justify-between">
					<div class="flex gap-2">
						{#if s.activeTab > 0}
							<button
								onclick={() => (s.activeTab -= 1)}
								class="text-xs text-ink-2 hover:text-ink-0 px-3 py-1.5 border border-line-2 rounded-lg"
							>
								← 이전
							</button>
						{/if}
						{#if s.activeTab < DB_TABS.length - 1}
							<button
								onclick={() => (s.activeTab += 1)}
								class="text-xs text-action-warm hover:text-action-warm-hover px-3 py-1.5 border border-action-warm rounded-lg"
							>
								다음 →
							</button>
						{/if}
					</div>
					<div class="flex gap-2">
						<button
							onclick={() => (open = false)}
							class="text-xs text-ink-2 hover:text-ink-0 px-4 py-1.5 border border-line-2 rounded-lg"
						>
							취소
						</button>
						<button
							onclick={s.createInstance}
							disabled={s.creating || !s.canCreate}
							title={s.step1Error || ''}
							class="text-xs text-action-on-warm bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 px-4 py-1.5 rounded-lg transition-colors"
						>
							{s.creating ? '생성 중...' : '생성'}
						</button>
					</div>
				</div>
			</div>
		</div>
	</div>
{/if}
