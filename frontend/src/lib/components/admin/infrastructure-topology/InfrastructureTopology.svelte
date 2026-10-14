<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { createInfrastructureTopologyController } from '$lib/stores/infrastructureTopologyController.svelte';
	import { t } from '$lib/i18n/ns/infra-topology';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import EvidenceMap from './EvidenceMap.svelte';
	import NicDetails from './NicDetails.svelte';
	import TraceDetails from './TraceDetails.svelte';
	import PeerProbeMap from './PeerProbeMap.svelte';
	import NetworkMap from './NetworkMap.svelte';
	const ctrl = createInfrastructureTopologyController();
	const roles = ['compute', 'controller', 'storage'] as const;
	const host = $derived(ctrl.snapshot?.hosts.find(item => item.id === ctrl.selectedId));
	const activeTrace = $derived(host?.traces.some(trace => trace.status === 'queued' || trace.status === 'running') ?? false);
	onMount(() => {
		const visibility = () => ctrl.setVisible(document.visibilityState !== 'hidden');
		visibility();
		const sync = () => {
			const state = get(auth);
			ctrl.setAuthority({ token: state.token ?? undefined, userId: state.userId ?? undefined, projectId: state.projectId ?? undefined, admin: state.isSystemAdmin, ready: get(authReady) && !get(projectSwitching) });
		};
		const subscriptions = [auth.subscribe(sync), authReady.subscribe(sync), projectSwitching.subscribe(sync)];
		document.addEventListener('visibilitychange', visibility);
		return () => { subscriptions.forEach(unsubscribe => unsubscribe()); document.removeEventListener('visibilitychange', visibility); ctrl.dispose(); };
	});
</script>

<PageShell>
	<PageHeader title={t('title')} breadcrumb={t('monitoring')} subtitle={t('description')}>
		{#snippet actions()}<Button variant="secondary" disabled={!ctrl.allowed || ctrl.loading} onclick={ctrl.load}>{t('refresh')}</Button>{/snippet}
	</PageHeader>
	<div class="space-y-4">
		<Alert tone="info">{t('notice')}</Alert>
		{#if ctrl.error}<Alert>{t(ctrl.error)}</Alert>{/if}
		{#if !ctrl.allowed && $authReady && !$projectSwitching}<Alert tone="warning">{t('denied')}</Alert>{/if}
		{#if ctrl.loading || !$authReady || $projectSwitching}<p role="status" class="text-sm text-ink-2">{t('loading')}</p>{/if}
		{#if ctrl.snapshot && ctrl.allowed}
			{#if !ctrl.snapshot.enabled}<Alert tone="warning">{t('disabled')}</Alert>{/if}
			{#if ctrl.snapshot.enabled && ctrl.snapshot.error}<Alert>{t('unavailable')}</Alert>{/if}
			{#if ctrl.snapshot.inventory_error}<Alert tone="warning">{t('inventoryWarning')}</Alert>{/if}
			{#if !ctrl.snapshot.hosts.length}<p class="text-sm text-ink-2">{t('empty')}</p>{/if}
			<section aria-label={t('hosts')} class="grid grid-cols-1 md:grid-cols-3 gap-3">
				{#each roles as role}<Card padding="sm"><h2 class="text-sm font-semibold mb-3">{t(`role.${role}`)}</h2><div class="flex flex-col gap-2">
					{#each ctrl.snapshot.hosts.filter(item => item.role === role) as item (item.id)}
						<Button variant={item.id === ctrl.selectedId ? 'primary' : 'secondary'} ariaPressed={item.id === ctrl.selectedId} onclick={() => ctrl.selectHost(item.id)} class="w-full"><span class="break-all font-mono">{item.name}</span></Button>
						<p class="text-xs text-ink-2 break-all">{item.address ?? t('unknown')} · {t(`state.${ctrl.verified ? item.observation_state : 'stale'}`)}</p>
					{:else}<p class="text-xs text-ink-2">{t('none')}</p>{/each}
				</div></Card>{/each}
			</section>
			<Card><NetworkMap hosts={ctrl.snapshot.hosts} verified={ctrl.verified} selectedId={ctrl.selectedId} onselect={ctrl.selectHost} /></Card>
			<Card><PeerProbeMap hosts={ctrl.snapshot.hosts} verified={ctrl.verified} selectedId={ctrl.selectedId} onselect={ctrl.selectHost} /></Card>
			{#if host}
				<Card><div class="space-y-4">
					<div class="flex flex-wrap items-center gap-3"><h2 class="font-semibold font-mono break-all">{host.name}</h2><Pill tone={ctrl.verified && host.observation_state === 'fresh' ? 'success' : 'neutral'}>{t(`state.${ctrl.verified ? host.observation_state : 'stale'}`)}</Pill></div>
					{#if host.observation && ((host.observation.interfaces_omitted ?? 0) > 0 || (host.observation.evidence_omitted ?? 0) > 0)}<Alert tone="warning">{t('omittedNotice', { interfaces: (host.observation.interfaces_omitted ?? 0).toLocaleString(intlLocale()), evidence: (host.observation.evidence_omitted ?? 0).toLocaleString(intlLocale()) })}</Alert>{/if}
					<dl class="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
						<div><dt class="text-ink-2">{t('reachability')}</dt><dd>{t(`state.${ctrl.verified ? host.reachability.status : 'unknown'}`)}</dd></div>
						<div><dt class="text-ink-2">{t('heartbeat')}</dt><dd>{t(`state.${ctrl.verified ? host.heartbeat.status : 'unknown'}`)}</dd></div>
						<div><dt class="text-ink-2">{t('captured')}</dt><dd>{host.observation ? new Date(host.observation.captured_at * 1000).toLocaleString(intlLocale()) : t('unknown')}</dd></div>
					</dl>
					<EvidenceMap {host} verified={ctrl.verified} selectedNic={ctrl.selectedNic} onselect={(nic) => { ctrl.selectedNic = nic; }} />
				</div></Card>
				{#if host.observation?.interfaces.length}<Card>
					<Field label={t('nic')} for="infra-nic"><SelectInput id="infra-nic" bind:value={ctrl.selectedNic}>{#each host.observation.interfaces as nic (nic.name)}<option value={nic.name}>{nic.name}</option>{/each}</SelectInput></Field>
					<div class="mt-4"><NicDetails {host} name={ctrl.selectedNic} verified={ctrl.verified} /></div>
				</Card>{/if}
				<Card><section aria-label={t('trace')} class="space-y-4">
					<h2 class="font-semibold">{t('trace')}</h2><p class="text-sm text-ink-2">{t('traceNotice')}</p>
					{#if !host.observer_configured}<Alert tone="warning">{t('observerNotConfigured')}</Alert>{/if}
					{#if ctrl.traceError}<Alert>{t(ctrl.traceError === 'unavailable' ? 'traceUnavailable' : ctrl.traceError)}</Alert>{/if}
					{#if ctrl.snapshot.trace_targets.length}<form class="flex flex-col md:flex-row md:items-end gap-3" onsubmit={(event) => { event.preventDefault(); void ctrl.submitTrace(); }}>
						<div class="flex-1 min-w-0"><Field label={t('target')} for="infra-target"><SelectInput id="infra-target" bind:value={ctrl.target} disabled={ctrl.busy || !ctrl.verified || !host.observer_configured}>{#each ctrl.snapshot.trace_targets as target}<option value={target}>{target}</option>{/each}</SelectInput></Field></div>
						<Button type="submit" variant="primary" disabled={!ctrl.verified || ctrl.busy || activeTrace || !ctrl.target || !host.observer_configured}>{t(ctrl.busy ? 'submitting' : 'submit')}</Button>
					</form>{:else}<p class="text-sm text-ink-2">{t('noTargets')}</p>{/if}
					<TraceDetails {host} verified={ctrl.verified} onselectnic={(nic) => { ctrl.selectedNic = nic; }} />
				</section></Card>
			{/if}
		{/if}
	</div>
</PageShell>
