<script lang="ts">
	import type { OrphanKind, CleanupResult } from '$lib/types/orphan';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/admin-storage';
	type Kind = OrphanKind;

	let {
		kind,
		ids,
		cleaning,
		cleanupError,
		cleanupResult,
		onConfirm,
		onClose,
	}: {
		kind: Kind | null;
		ids: string[];
		cleaning: boolean;
		cleanupError: string;
		cleanupResult: CleanupResult | null;
		onConfirm: () => void;
		onClose: () => void;
	} = $props();

	const KIND_LABELS: Record<Kind, string> = $derived({
		floating_ip: t('orphanCleanup.kind.floatingIp'),
		volume: t('orphanCleanup.kind.volume'),
		manila_share: t('orphanCleanup.kind.manilaShare'),
		security_group: t('orphanCleanup.kind.securityGroup'),
	});
</script>

{#if kind}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => onClose() }}
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={(event) => { if (event.target === event.currentTarget) (onClose)(); }}
		role="dialog" aria-modal="true"
		tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-lg mx-4 shadow-[var(--shadow-restraint)]"
			role="document"
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-3">
				{t('orphanCleanup.title', { kind: KIND_LABELS[kind], count: ids.length })}
			</h2>

			{#if !cleanupResult}
				<p class="text-sm text-ink-2 mb-4">
					{t('orphanCleanup.warning')}
				</p>
				<div class="bg-surface-canvas border border-line rounded-lg p-3 mb-4 max-h-48 overflow-y-auto">
					<ul class="text-xs font-mono text-ink-2 space-y-0.5">
						{#each ids as id}
							<li>{id}</li>
						{/each}
					</ul>
				</div>
				{#if kind === 'volume'}
					<p class="text-xs text-warm-text mb-3">
						{t('orphanCleanup.volumeNote')}
					</p>
				{:else if kind === 'manila_share'}
					<p class="text-xs text-warm-text mb-3">
						{t('orphanCleanup.shareNote')}
					</p>
				{:else if kind === 'security_group'}
					<p class="text-xs text-warm-text mb-3">
						{t('orphanCleanup.securityGroupNote')}
					</p>
				{/if}
				{#if cleanupError}
					<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">
						{cleanupError}
					</div>
				{/if}
				<div class="flex justify-end gap-3">
					<button
						onclick={onClose}
						class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg"
					>
						{t('orphanCleanup.cancel')}
					</button>
					<button
						onclick={onConfirm}
						disabled={cleaning}
						class="px-4 py-2 bg-red-600 hover:bg-red-500 text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30"
					>
						{cleaning ? t('orphanCleanup.cleaning') : t('orphanCleanup.clean')}
					</button>
				</div>
			{:else}
				<div class="space-y-3 mb-4">
					<div class="text-sm text-green-400">
						{t('orphanCleanup.successCount', { count: cleanupResult.deleted.length })}
					</div>
					{#if cleanupResult.deleted.length > 0}
						<details class="bg-surface-canvas border border-line rounded-lg p-3">
							<summary class="text-xs text-ink-2 cursor-pointer">{t('orphanCleanup.showDeletedIds')}</summary>
							<ul class="text-xs font-mono text-ink-2 mt-2 space-y-0.5 max-h-32 overflow-y-auto">
								{#each cleanupResult.deleted as id}
									<li>{id}</li>
								{/each}
							</ul>
						</details>
					{/if}
					<div class="text-sm {cleanupResult.failed.length > 0 ? 'text-red-400' : 'text-ink-2'}">
						{t('orphanCleanup.failedCount', { count: cleanupResult.failed.length })}
					</div>
					{#if cleanupResult.failed.length > 0}
						<div class="bg-red-900/20 border border-red-800 rounded-lg p-3 max-h-48 overflow-y-auto">
							<ul class="text-xs space-y-1.5">
								{#each cleanupResult.failed as f}
									<li>
										<span class="font-mono text-red-300">{f.id.slice(0, 8)}</span>
										<span class="text-red-400 ml-2">{f.error}</span>
									</li>
								{/each}
							</ul>
						</div>
					{/if}
				</div>
				<div class="flex justify-end">
					<button
						onclick={onClose}
						class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg"
					>
						{t('orphanCleanup.close')}
					</button>
				</div>
			{/if}
		</div>
	</div>
{/if}
