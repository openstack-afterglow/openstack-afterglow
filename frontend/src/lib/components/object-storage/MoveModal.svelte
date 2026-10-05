<script lang="ts">
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/object-storage';
	import source from '$lib/i18n/messages/ko/object-storage.json';

	const moveRoot = source['dialogs.controller.move.rootToken'];

	interface Props { bulk?: boolean; }
	let { bulk = false }: Props = $props();

	const s = useObjectBrowser();
	const show = $derived(bulk ? s.showBulkMove : s.showMove);
</script>

{#if show}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => (bulk ? (s.showBulkMove = false) : (s.showMove = false)) }}
		class="fixed inset-0 z-50 flex items-center justify-center bg-surface-scrim/70"
		onclick={() => { if (bulk) s.showBulkMove = false; else s.showMove = false; }}
		role="dialog" aria-modal="true" tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line rounded-xl p-6 w-full max-w-md shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
		>
			{#if bulk}
				<h2 class="text-ink-0 font-semibold mb-1">{t('dialogs.move.bulkTitle')}</h2>
				<p class="text-indigo-400 text-xs mb-4">{t('dialogs.move.selectedCount', { count: s.selectedCount })}</p>
			{:else}
				<h2 class="text-ink-0 font-semibold mb-1">{t('dialogs.move.title')}</h2>
				<p class="text-indigo-400 text-sm mb-4 break-all">{s.displayName(s.moveTarget)}</p>
			{/if}

			{#if s.moveError}
				<div class="bg-red-900/20 border border-red-800 rounded-lg px-3 py-2 text-red-400 text-xs mb-3">{s.moveError}</div>
			{/if}

			<label class="text-ink-2 text-xs mb-1 block font-medium" for="field-movemodal-36">{t('dialogs.move.destinationBucket')}</label>
			{#if s.moveContainers.length > 0}
				<select id="field-movemodal-36"
					value={s.moveDestContainer}
					onchange={(e) => s.onMoveContainerChange((e.target as HTMLSelectElement).value)}
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 mb-4 focus:outline-none focus:border-indigo-500"
				>
					{#each s.moveContainers as c}
						<option value={c.name}>{t('dialogs.move.bucketOption', { name: c.name, count: c.count })}</option>
					{/each}
				</select>
			{:else}
				<input
					type="text"
					bind:value={s.moveDestContainer}
					placeholder={t('dialogs.move.bucketName')}
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 mb-4 focus:outline-none focus:border-indigo-500"
				/>
			{/if}

			<label class="text-ink-2 text-xs mb-1 block font-medium" for="field-movemodal-56">{t('dialogs.move.destinationDirectory')}</label>
			{#if s.moveLoadingDirs}
				<div class="bg-surface-sunken border border-line-2 rounded-lg p-3 mb-3">
					<p class="text-ink-2 text-xs">{t('dialogs.move.loadingDirectories')}</p>
				</div>
			{:else}
				<div class="bg-surface-sunken border border-line-2 rounded-lg max-h-48 overflow-y-auto mb-3">
					{#each s.moveDirectories.filter(d =>
						d === moveRoot ||
						(bulk
							? ![...s.selected].some(sel => d === sel || d.startsWith(sel))
							: (d !== s.moveTarget && !d.startsWith(s.moveTarget)))
					) as dir}
						{@const isSelected = (dir === moveRoot && s.moveSelectedDir === '') || dir === s.moveSelectedDir}
						<button id="field-movemodal-56"
							onclick={() => bulk ? s.selectBulkMoveDir(dir) : s.selectMoveDir(dir)}
							class="w-full text-left px-3 py-2 text-sm flex items-center gap-2 transition-colors {isSelected ? 'bg-indigo-600/20 text-indigo-300 border-l-2 border-indigo-500' : 'text-ink-2 hover:bg-surface-selected/50'}"
						>
							<svg class="w-4 h-4 shrink-0 {isSelected ? 'text-indigo-400' : 'text-warm-text'}" viewBox="0 0 20 20" fill="currentColor">
								<path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/>
							</svg>
							<span class="truncate">{dir === moveRoot ? t('dialogs.controller.move.rootToken') : dir}</span>
							{#if isSelected}
								<svg class="w-4 h-4 ml-auto text-indigo-400 shrink-0" viewBox="0 0 20 20" fill="currentColor">
									<path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
								</svg>
							{/if}
						</button>
					{/each}
					{#if !bulk && s.moveDirectories.length <= 1}
						<p class="text-ink-2 text-xs px-3 py-2">{t('dialogs.move.noDirectories')}</p>
					{/if}
				</div>
			{/if}

			{#if s.moveDestinationChosen}
				<div class="bg-surface-sunken/50 border border-line-2 rounded px-3 py-2 mb-4">
					<p class="text-xs text-ink-2 uppercase tracking-wider mb-0.5">{t(bulk ? 'dialogs.move.destinationLocation' : 'dialogs.move.destinationPath')}</p>
					<p class="text-ink-0 text-sm font-mono break-all">{t('dialogs.move.path', { bucket: s.moveDestContainer, path: s.moveDest || t('dialogs.move.root') })}</p>
				</div>
			{/if}

			<div class="flex gap-2 justify-end">
				<button
					onclick={() => { if (bulk) s.showBulkMove = false; else s.showMove = false; }}
					class="text-xs text-ink-2 hover:text-ink-0 px-4 py-2 rounded-lg border border-line-2 transition-colors"
				>{t('dialogs.move.cancel')}</button>
				<button
					onclick={bulk ? s.doBulkMove : s.doMove}
					disabled={bulk ? s.bulkMoving || !s.moveDestinationChosen : (s.moving || !s.moveDestinationChosen)}
					class="text-xs text-ink-0 bg-indigo-600 hover:bg-indigo-500 disabled:bg-surface-selected disabled:text-ink-3 px-4 py-2 rounded-lg border border-indigo-500 disabled:border-line-2 transition-colors"
				>
					{#if bulk}
						{s.bulkMoving ? t('dialogs.move.moving') : t('dialogs.move.moveCount', { count: s.selectedCount })}
					{:else}
						{t(s.moving ? 'dialogs.move.moving' : 'dialogs.move.submit')}
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}
