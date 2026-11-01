<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/admin-ops';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { onMount, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { Overview, VersionInfo, DomainUsage } from '$lib/types/adminOverview';
	import KpiCardRow from '$lib/components/admin/overview/KpiCardRow.svelte';
	import ResourceDonutsCard from '$lib/components/admin/overview/ResourceDonutsCard.svelte';
	import DomainUsageTable from '$lib/components/admin/overview/DomainUsageTable.svelte';
	import ServiceCountCards from '$lib/components/admin/overview/ServiceCountCards.svelte';
	import VersionInfoPanel from '$lib/components/admin/overview/VersionInfoPanel.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { Alert, Button, PageHeader, PageShell } from '$lib/components/ui';

	interface Notification {
		severity: string;
		message: string;
		target?: string;
		href?: string;
		type?: string;
		count?: number;
		available?: boolean;
	}

	interface IdentitySummary {
		user_count: number;
		project_count: number;
		role_count: number;
		group_count: number;
		partial?: boolean;
		partial_reasons?: string[];
		recent_users?: { id: string; name: string }[];
		recent_projects?: { id: string; name: string }[];
	}

	interface RecentEvent { id: number; created_at: string; username: string; action: string; resource_name: string | null; resource_id: string | null; status: string }
	let recentEvents = $state<RecentEvent[] | null>(null);
	let eventsError = $state(false);
	let notificationsError = $state(false);
	let identityError = $state(false);

	let overview = $state<Overview | null>(null);
	let overviewLoading = $state(true);
	let error = $state('');
	let domainUsage = $state<DomainUsage[]>([]);
	let domainUsageLoading = $state(true);
	let domainUsageError = $state('');
	let versionInfo = $state<VersionInfo | null>(null);
	let versionOpen = $state(false);
	let notifications = $state<Notification[]>([]);
	let identitySummary = $state<IdentitySummary | null>(null);
	function identityCount(section: string, value: number): string {
		return identitySummary?.partial_reasons?.some(reason => reason.startsWith(`${section}:`))
			? t('overview.availability.unknown') : value.toLocaleString(intlLocale());
	}
	function notificationText(notification: Notification): string {
		const count = notification.count;
		if (notification.type === 'k3s' && notification.available === false) return t('overview.notices.clustersUnavailable');
		if (typeof count !== 'number' || !Number.isFinite(count)) return notification.message;
		if (notification.type === 'error') return t('overview.notices.instances', { count: count >= 50 ? `${count}+` : String(count) });
		if (notification.type === 'resource') return t('overview.notices.memory', { count });
		if (notification.type === 'k3s') return t('overview.notices.clusters', { count });
		if (notification.type === 'network') return t('overview.notices.network', { count });
		return notification.message;
	}
	function notificationHref(notification: Notification): string {
		if (notification.type === 'error') return '/admin/instances';
		if (notification.type === 'resource') return '/admin/hypervisors';
		if (notification.type === 'k3s') return '/admin/drover';
		if (notification.type === 'network') return '/admin/floating-ips';
		return notification.href || '/admin/monitoring';
	}

	let mounted = $state(false);
	let authorityRevision = $state(0);
	let domainRequest = 0;
	let overviewRequest = 0;
	function clearPublished() {
		authorityRevision += 1;
		domainRequest += 1;
		overviewRequest += 1;
		overview = null; overviewLoading = true; error = '';
		domainUsage = []; domainUsageLoading = true; domainUsageError = '';
		versionInfo = null; versionOpen = false; notifications = []; identitySummary = null;
		recentEvents = null; eventsError = false; notificationsError = false; identityError = false;
	}
	function capture() {
		const state = get(auth);
		if (!mounted || !state.token || !state.isSystemAdmin || !get(authReady) || get(logoutInProgress) || get(projectSwitching)) return null;
		const revision = authorityRevision;
		return { token: state.token, projectId: state.projectId ?? undefined, current: () => mounted && revision === authorityRevision };
	}
	function loadDomainUsage(opts?: { background?: boolean }) {
		const owner = capture();
		if (!owner) return;
		const request = ++domainRequest;
		const current = () => owner.current() && request === domainRequest;
		if (!opts?.background) domainUsageLoading = true;
		return api.get<DomainUsage[]>('/api/v1/admin/overview/domains', owner.token, owner.projectId)
			.then(result => { if (current()) { domainUsage = result; domainUsageError = ''; } })
			.catch(() => { if (current()) domainUsageError = t('overview.domains.loadFailed'); })
			.finally(() => { if (current()) domainUsageLoading = false; });
	}

	createAutoRefresh(() => loadDomainUsage({ background: true }),
		{ storageKey: 'admin-overview', defaultActive: true, defaultInterval: 60, invokeOnMount: false });

	function loadOverview() {
		const owner = capture();
		if (!owner) return;
		const request = ++overviewRequest;
		const current = () => owner.current() && request === overviewRequest;
		overviewLoading = true;
		api.get<Overview>('/api/v1/admin/overview', owner.token, owner.projectId)
			.then(result => { if (current()) { overview = result; error = ''; } })
			.catch(reason => {
				if (!current()) return;
				if (reason instanceof ApiError && reason.status === 403) { void goto('/dashboard'); return; }
				error = reason instanceof ApiError ? t('overview.page.queryFailed', { message: reason.message }) : t('overview.page.serverError');
			})
			.finally(() => { if (current()) overviewLoading = false; });
		loadDomainUsage();
		api.get<VersionInfo>('/api/v1/admin/version', owner.token, owner.projectId)
			.then(result => { if (current()) versionInfo = result; }).catch(() => {});
		api.get<{ notifications: Notification[] }>('/api/v1/admin/notifications', owner.token, owner.projectId)
			.then(result => { if (current()) { notifications = result.notifications; notificationsError = false; } }).catch(() => { if (current()) notificationsError = true; });
		api.get<IdentitySummary>('/api/v1/admin/identity/summary', owner.token, owner.projectId)
			.then(result => { if (current()) { identitySummary = result; identityError = false; } }).catch(() => { if (current()) identityError = true; });
		api.get<RecentEvent[]>('/api/v1/admin/events?limit=5', owner.token, owner.projectId)
			.then(result => { if (current()) { recentEvents = result; eventsError = false; } }).catch(() => { if (current()) eventsError = true; });
	}

	onMount(() => {
		// Synchronous subscriptions invalidate same-tick A→B→A, not just the final key.
		const unsubscribers = [auth.subscribe(clearPublished), authReady.subscribe(clearPublished),
			logoutInProgress.subscribe(clearPublished), projectSwitching.subscribe(clearPublished)];
		mounted = true;
		return () => { mounted = false; clearPublished(); unsubscribers.forEach(unsubscribe => unsubscribe()); };
	});
	$effect(() => {
		if (!mounted) return;
		authorityRevision;
		untrack(loadOverview);
	});
</script>

<PageShell class="flex flex-col gap-5">
	<PageHeader breadcrumb={t('overview.page.breadcrumb')} title={t('overview.page.title')} subtitle={t('overview.page.subtitle')} />
	<section class="rounded-lg border border-line bg-surface-base p-5" aria-labelledby="overview-attention-title">
		<div class="flex flex-wrap items-center justify-between gap-2"><h2 id="overview-attention-title" class="text-[15px] font-semibold text-ink-0">{t('overview.attention.title')}</h2><div class="flex flex-wrap items-center gap-2"><Button variant="secondary" disabled={overviewLoading} onclick={loadOverview}>{t('monitoring.refresh')}</Button><Button variant="link" href="/admin/monitoring">{t('overview.notifications.monitoringDetails')}</Button></div></div>
		{#if error}<Alert tone="danger" class="mt-3">{error}</Alert>{/if}
		{#if notificationsError}<Alert tone="danger" class="mt-3">{t('overview.attention.notificationsFailed')}</Alert>{/if}
		{#if overview?.unavailable_sections?.length}<Alert tone="warning" class="mt-3">{t('overview.availability.partial')} <span class="font-mono text-xs">{overview.unavailable_sections.join(', ')}</span></Alert>{/if}
		{#if overview?.instance_stats}
			<div class="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm tabular-nums">
				<a href="/admin/instances" class={overview.instance_stats.error > 0 ? 'font-semibold text-state-danger-text underline underline-offset-2' : 'text-ink-2'}>{t('overview.kpi.errorCount', { count: overview.instance_stats.error })}</a>
				<span class="text-ink-2">{t('overview.attention.instanceStates', { active: overview.instance_stats.active, shutoff: overview.instance_stats.shutoff, other: overview.instance_stats.other })}</span>
				{#if overview.running_vms !== null}<span class="text-ink-2">{t('overview.attention.running', { count: overview.running_vms })}</span>{/if}
			</div>
		{:else if !overviewLoading}<p class="mt-3 text-sm text-ink-2">{t('overview.availability.unknown')}</p>{/if}
		{#if overviewLoading}<LoadingState variant="inline" label={t('overview.loading')} />{/if}
		{#if notifications.length > 0}<ul class="mt-3 divide-y divide-line">{#each notifications as notification}<li class="py-2 text-sm"><a href={notificationHref(notification)} class="flex flex-wrap justify-between gap-2 hover:underline"><span class={notification.severity === 'critical' || notification.severity === 'high' ? 'text-state-danger-text' : notification.severity === 'warning' ? 'text-state-warning-text' : 'text-ink-1'}>{notificationText(notification)}</span>{#if notification.target}<span class="text-ink-2">{notification.target}</span>{/if}</a></li>{/each}</ul>{/if}
	</section>
	{#if overviewLoading && !overview}<LoadingState variant="section" label={t('overview.loading')} />
	{:else if overview}
		<ResourceDonutsCard {overview} />
		<KpiCardRow {overview} />
	{/if}
	<section class="rounded-lg border border-line bg-surface-base p-5" aria-labelledby="overview-events-title">
		<div class="flex items-center justify-between gap-2"><h2 id="overview-events-title" class="text-[15px] font-semibold text-ink-0">{t('overview.events.title')}</h2><Button variant="link" href="/admin/events">{t('overview.kpi.viewAll')}</Button></div>
		{#if eventsError}<Alert tone="danger" class="mt-3">{t('overview.events.failed')}</Alert>{:else if recentEvents === null}<LoadingState variant="table" columns={3} rows={4} label={t('overview.loading')} />{:else if recentEvents.length === 0}<p class="mt-3 text-sm text-ink-2">{t('overview.events.empty')}</p>{:else}
			<ul class="mt-2 divide-y divide-line">{#each recentEvents as event}<li class="py-2"><a href="/admin/events" class="grid gap-x-4 gap-y-1 text-sm hover:underline sm:grid-cols-[minmax(0,1fr)_auto]"><span class="break-words text-ink-1">{event.action} · {event.resource_name || event.resource_id || '—'} · {event.username}</span><time datetime={event.created_at} class="text-xs tabular-nums text-ink-2">{new Date(event.created_at).toLocaleString(intlLocale())}</time><span class={event.status === 'failed' || event.status === 'error' ? 'text-state-danger-text' : 'text-ink-2'}>{event.status}</span></a></li>{/each}</ul>
		{/if}
	</section>
	<DomainUsageTable domains={domainUsage} loading={domainUsageLoading} error={domainUsageError} />
	{#if overview}<ServiceCountCards {overview} />{/if}
	{#if identityError}<Alert tone="danger">{t('overview.identity.failed')}</Alert>{/if}
	{#if identitySummary}
		<div class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4">
			{#each [{ href: '/admin/users', label: t('overview.identity.users'), value: identitySummary.user_count }, { href: '/admin/projects', label: t('overview.identity.projects'), value: identitySummary.project_count }, { href: '/admin/roles', label: t('overview.identity.roles'), value: identitySummary.role_count }, { href: '/admin/groups', label: t('overview.identity.groups'), value: identitySummary.group_count }] as item}
				<a href={item.href} class="flex items-baseline justify-between gap-2 bg-surface-base px-4 py-3 text-sm hover:bg-surface-selected"><span class="text-ink-2">{item.label}</span><span class="font-semibold tabular-nums text-ink-0">{identityCount(item.href.split('/').at(-1)!, item.value)}</span></a>
			{/each}
		</div>
		{#if identitySummary.partial && identitySummary.partial_reasons?.length}<Alert tone="warning">{t('overview.identity.partial', { reasons: identitySummary.partial_reasons.map(r => r.includes('insufficient_privileges') ? t('overview.identity.insufficientPrivileges', { target: r.split(':')[0] }) : r).join(', ') })}</Alert>{/if}
		{#if identitySummary.recent_users?.length || identitySummary.recent_projects?.length}<details class="text-sm text-ink-2"><summary class="cursor-pointer">{t('overview.identity.recentUsers', { count: identitySummary.recent_users?.length ?? 0 })} · {t('overview.identity.recentProjects', { count: identitySummary.recent_projects?.length ?? 0 })}</summary><ul class="mt-2 flex flex-wrap gap-x-5 gap-y-2">{#each identitySummary.recent_users ?? [] as user}<li><a href="/admin/users" class="hover:underline">{user.name}</a></li>{/each}{#each identitySummary.recent_projects ?? [] as project}<li><a href="/admin/projects" class="hover:underline">{project.name}</a></li>{/each}</ul></details>{/if}
	{/if}
	<nav class="flex flex-wrap gap-x-5 gap-y-2 text-sm text-ink-2" aria-label={t('overview.kpi.details')}>
		{#each [{ href: '/admin/hypervisors', label: t('overview.links.hypervisors') }, { href: '/admin/instances', label: t('overview.links.instances') }, { href: '/admin/containers', label: t('overview.links.containers') }, { href: '/admin/file-storage', label: t('overview.links.fileStorage') }, { href: '/admin/database-instances', label: t('overview.links.database') }, { href: '/admin/object-storage', label: t('overview.links.objectStorage') }, { href: '/admin/topology', label: t('overview.links.topology') }, { href: '/admin/networks', label: t('overview.links.networks') }] as link}<Button variant="link" href={link.href}>{link.label}</Button>{/each}
	</nav>
	<VersionInfoPanel {versionInfo} bind:open={versionOpen} />
</PageShell>

