<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { createInfrastructureTopologyController } from '$lib/stores/infrastructureTopologyController.svelte';
	import type { TopologySelection } from '$lib/types/infrastructureTopology';
	import { t } from '$lib/i18n/ns/infra-topology';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import RadialWorkspace from './RadialWorkspace.svelte';
	import TopologyInspector from './TopologyInspector.svelte';
	import { buildRadialGraph } from './radialGraph';
	import { fabricErrorMessages, timestamp } from './presentation';
	const ctrl = createInfrastructureTopologyController();
	let mobile = $state(false), inspectorOpen = $state(false);
	const graph = $derived(ctrl.snapshot ? buildRadialGraph(ctrl.snapshot, ctrl.verified) : null);
	function select(next: TopologySelection) {
		const edge = next.kind === 'edge' ? graph?.edges.find(item => item.id === next.id) : undefined;
		const hostId = next.kind === 'node' ? graph?.nodes.find(node => node.id === next.id)?.hostId : edge?.hostId;
		ctrl.selectElement(next, hostId); inspectorOpen = true;
		const nic = edge?.flow?.interface ?? edge?.route?.interface ?? edge?.trace?.result?.source_interface;
		if (nic && ctrl.snapshot?.hosts.find(host => host.id === hostId)?.observation?.interfaces.some(item => item.name === nic)) ctrl.selectedNic = nic;
	}
	onMount(() => {
		const visibility = () => ctrl.setVisible(document.visibilityState !== 'hidden' && navigator.onLine !== false);
		visibility();
		const sync = () => {
			const state = get(auth);
			ctrl.setAuthority({ token: state.token ?? undefined, userId: state.userId ?? undefined, projectId: state.projectId ?? undefined, admin: state.isSystemAdmin, ready: get(authReady) && !get(projectSwitching) });
			if (!ctrl.allowed) inspectorOpen = false;
		};
		const subscriptions = [auth.subscribe(sync), authReady.subscribe(sync), projectSwitching.subscribe(sync)];
		const mq = typeof window.matchMedia === 'function' ? window.matchMedia('(max-width: 767px)') : null;
		const resize = () => { mobile = mq?.matches ?? false; }; resize(); mq?.addEventListener('change', resize);
		document.addEventListener('visibilitychange', visibility);
		window.addEventListener('online', visibility);
		window.addEventListener('offline', visibility);
		return () => { subscriptions.forEach(unsubscribe => unsubscribe()); mq?.removeEventListener('change', resize); document.removeEventListener('visibilitychange', visibility); window.removeEventListener('online', visibility); window.removeEventListener('offline', visibility); ctrl.dispose(); };
	});
</script>

<PageShell>
	<PageHeader title={t('title')} breadcrumb={t('monitoring')} subtitle={t('description')}>
		{#snippet actions()}<Button variant="secondary" disabled={!ctrl.allowed || ctrl.loading} onclick={ctrl.load}>{t('refresh')}</Button>{/snippet}
	</PageHeader>
	<div class="space-y-4">
		{#if ctrl.error}<Alert>{t(ctrl.error)}</Alert>{/if}
		{#if !ctrl.allowed && $authReady && !$projectSwitching}<Alert tone="warning">{t('denied')}</Alert>{/if}
		{#if ctrl.loading || !$authReady || $projectSwitching}<p role="status" class="text-sm text-ink-2">{t('loading')}</p>{/if}
		{#if ctrl.snapshot && ctrl.allowed && graph}
			{#if !ctrl.snapshot.enabled}<Alert tone="warning">{t('disabled')}</Alert>{/if}
			{#if ctrl.snapshot.enabled && ctrl.snapshot.error}<Alert>{t('unavailable')}</Alert>{/if}
			{#if ctrl.snapshot.inventory_error}<Alert tone="warning">{t('inventoryWarning')}</Alert>{/if}
			{#if !ctrl.snapshot.hosts.length}<p class="text-sm text-ink-2">{t('empty')}</p>{/if}
			<div class="coverage" aria-label={t('workspace.coverage')}>
				<p>{t('workspace.flowCoverage', { measured: ctrl.snapshot.hosts.filter(host => ctrl.verified && host.observation_state === 'fresh' && host.observation?.sources.flows === 'measured').length.toLocaleString(intlLocale()), total: ctrl.snapshot.hosts.length.toLocaleString(intlLocale()) })}</p>
				<p>{t('workspace.flowUnavailableCoverage', { unsupported: ctrl.snapshot.hosts.filter(host => host.observation?.sources.flows === 'unsupported').length.toLocaleString(intlLocale()), errors: ctrl.snapshot.hosts.filter(host => host.observation?.sources.flows === 'error').length.toLocaleString(intlLocale()), unknown: ctrl.snapshot.hosts.filter(host => !host.observation).length.toLocaleString(intlLocale()) })}</p>
				<p>{t('workspace.fabric')} · {ctrl.verified ? t(`workspace.fabricState.${ctrl.snapshot.fabric.state}`) : t('workspace.retained')} · {timestamp(ctrl.snapshot.fabric.coverage.last_observed_at)}</p>
				{#each fabricErrorMessages(ctrl.snapshot.fabric.coverage.error) as message}<p role="status">{message}</p>{/each}
				<p class="coverage-notice">{t('workspace.flowNotice')} {t('workspace.physicalNotice')}</p>
			</div>
			<div class="workspace-grid">
				<div class="graph-pane"><RadialWorkspace {graph} selection={ctrl.selection} onselect={select} /></div>
				{#if !mobile}<aside class="inspector-pane"><TopologyInspector {ctrl} {graph} snapshot={ctrl.snapshot} onselect={select} /></aside>{/if}
			</div>
			{#if mobile}
				<Button variant="secondary" disabled={!ctrl.selection} onclick={() => { inspectorOpen = true; }}>{t('workspace.openInspector')}</Button>
				{#if inspectorOpen}<div class="inspector-modal"><SlidePanel onClose={() => { inspectorOpen = false; }} resizable={false} ariaLabel={t('workspace.inspector')}><div class="p-4 pb-8"><TopologyInspector {ctrl} {graph} snapshot={ctrl.snapshot} onselect={select} /></div></SlidePanel></div>{/if}
			{/if}
		{/if}
	</div>
</PageShell>
<style>
	.workspace-grid { display: grid; gap: 1rem; min-width: 0; }
	.graph-pane, .inspector-pane { min-width: 0; }
	.inspector-pane { border-top: 1px solid var(--color-line); padding-top: 1rem; }
	.coverage { display: flex; flex-wrap: wrap; gap: 0.35rem 1.25rem; font-size: 0.75rem; color: var(--color-ink-2); padding-block: 0.75rem; border-block: 1px solid var(--color-line); }
	.coverage-notice { flex-basis: 100%; max-width: 100ch; }
	.inspector-modal :global([data-slide-panel-close]) { min-width: 44px; min-height: 44px; }
	@media (min-width: 1024px) { .workspace-grid { grid-template-columns: minmax(0, 1.8fr) minmax(18rem, 1fr); align-items: start; } .inspector-pane { border-top: 0; border-inline-start: 1px solid var(--color-line); padding-top: 0; padding-inline-start: 1rem; max-height: 78dvh; overflow-y: auto; } }
</style>
