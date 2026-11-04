<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	import { siteConfig } from '$lib/config/site';
	import { k3sOperations } from '$lib/stores/k3sOperations.svelte';
	import { observedProjectPermissions } from '$lib/stores/servicePermissions';
	import { K3S_CREATE_STEPS, K3S_DELETE_STEPS, k3sProgressState, k3sStagePercent } from '$lib/components/k3sSteps';
	import { t } from '$lib/i18n/ns/drover-pages';
	import { t as td } from '$lib/i18n/ns/drover';
	import { t as tc } from '$lib/i18n/ns/common';
	import { Button, ProgressTrack } from '$lib/components/ui';
	import K3sProgressModal from './K3sProgressModal.svelte';
	let { inline = false }: { inline?: boolean } = $props();

	let minimized = $state<string[]>([]);
	onMount(() => k3sOperations.mount());
	const entries = $derived.by(() => {
		// Store reads make identity changes immediately hide the previous owner's observation.
		if (!$auth.token || !$authReady || $projectSwitching || $logoutInProgress) return [];
		void $siteConfig.runtime.api_base;
		void $observedProjectPermissions;
		void $auth.projectId; void $auth.userId; void $auth.sessionId;
		return k3sOperations.entries;
	});
</script>

{#if entries.length}
	<section style:display={entries.some(entry => entry.progress.visible) ? 'none' : undefined} class="{inline ? 'relative w-full shrink-0' : 'fixed bottom-4 right-4 z-[var(--z-toast)] w-96 max-w-[calc(100vw-2rem)]'} flex max-h-[calc(100dvh-5rem)] flex-col gap-2 overflow-y-auto" aria-label={t('progress.operations')}>
		{#each entries as entry (entry.id)}
			{@const p = entry.progress}
			{@const stages = p.mode === 'delete' ? K3S_DELETE_STEPS : K3S_CREATE_STEPS}
			{@const state = k3sProgressState(p.step, p.stepTimings, stages)}
			<article class="rounded-xl border border-line-2 bg-surface-raised p-4 text-sm text-ink-0 shadow-[var(--shadow-restraint)]">
				<div class="flex flex-wrap items-start justify-between gap-3">
					<div class="min-w-0">
						<p class="font-medium">{p.mode === 'delete' ? t('cluster.deleteTitle') : t('cluster.createTitle')}</p>
						{#if entry.name}<p class="break-words text-ink-2">{entry.name}</p>{/if}
					</div>
					<div class="flex shrink-0 flex-wrap justify-end gap-1">
						<Button variant="ghost" size="sm" onclick={() => { p.visible = true; }}>{t('actions.details')}</Button>
						<Button variant="ghost" size="sm" ariaExpanded={!minimized.includes(entry.id)} onclick={() => { minimized = minimized.includes(entry.id) ? minimized.filter(id => id !== entry.id) : [...minimized, entry.id]; }}>{minimized.includes(entry.id) ? t('progress.expand') : t('progress.minimize')}</Button>
					</div>
				</div>
				<p class="mt-2 break-words text-ink-2" class:line-clamp-2={minimized.includes(entry.id)} role="status" aria-live="polite" aria-atomic="true">
					{#if minimized.includes(entry.id)}
						{p.step === 'completed' ? td('steps.completed') : p.step === 'failed' ? tc('stepProgress.failed') : p.uncertain ? t('progress.unknown') : (stages.find(stage => stage.id === state.current)?.label || td('steps.prepare'))}
					{:else}
						{p.isTerminal ? (p.error || (p.step === 'completed' ? td('steps.completed') : td('progress.unknownError'))) : p.uncertain ? t('progress.unknown') : (p.msg || stages.find(stage => stage.id === state.current)?.label || td('steps.prepare'))}
					{/if}
				</p>
				{#if !minimized.includes(entry.id)}
				<ProgressTrack value={k3sStagePercent(p.step, p.stepTimings, stages)} label={t('progress.reported')} active={!p.isTerminal && !p.uncertain} tone={p.step === 'completed' ? 'success' : p.step === 'failed' ? 'danger' : 'accent'} class="mt-3" />
				<p class="mt-1 text-xs text-ink-2">{t('progress.reported')}{#if k3sStagePercent(p.step, p.stepTimings, stages) !== null} <span class="tabular-nums">{k3sStagePercent(p.step, p.stepTimings, stages)}%</span>{/if}</p>
				{#if p.isTerminal}
					<div class="mt-2 flex justify-end"><Button variant="ghost" size="sm" onclick={() => k3sOperations.dismiss(entry.id)}>{t('actions.close')}</Button></div>
				{:else if p.uncertain}
					<Button variant="ghost" size="sm" onclick={() => { void k3sOperations.refresh(); }}>{t('clusterError.reload')}</Button>
				{/if}
				{/if}
			</article>
		{/each}
	</section>
	{#each entries.filter(entry => entry.progress.visible) as entry (entry.id)}
		<K3sProgressModal controller={entry.progress} activeSteps={entry.progress.mode === 'delete' ? K3S_DELETE_STEPS : K3S_CREATE_STEPS}
			onClose={() => { entry.progress.visible = false; }}
			onViewCluster={(id) => { entry.progress.visible = false; void goto(`/dashboard/drover/${encodeURIComponent(id)}`); }} />
	{/each}
{/if}
