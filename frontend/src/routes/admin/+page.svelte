<script lang="ts">
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
	import { Alert, PageHeader, PageShell, StatTile } from '$lib/components/ui';

	interface Notification {
		severity: string;
		message: string;
		target: string;
		href: string;
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

	let mounted = $state(false);
	let authorityRevision = $state(0);
	let domainRequest = 0;
	function clearPublished() {
		authorityRevision += 1;
		domainRequest += 1;
		overview = null; overviewLoading = true; error = '';
		domainUsage = []; domainUsageLoading = true; domainUsageError = '';
		versionInfo = null; versionOpen = false; notifications = []; identitySummary = null;
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
		api.get<Overview>('/api/v1/admin/overview', owner.token, owner.projectId)
			.then(result => { if (owner.current()) overview = result; })
			.catch(reason => {
				if (!owner.current()) return;
				if (reason instanceof ApiError && reason.status === 403) { void goto('/dashboard'); return; }
				error = reason instanceof ApiError ? t('overview.page.queryFailed', { message: reason.message }) : t('overview.page.serverError');
			})
			.finally(() => { if (owner.current()) overviewLoading = false; });
		loadDomainUsage();
		api.get<VersionInfo>('/api/v1/admin/version', owner.token, owner.projectId)
			.then(result => { if (owner.current()) versionInfo = result; }).catch(() => {});
		api.get<Notification[]>('/api/v1/admin/notifications', owner.token, owner.projectId)
			.then(result => { if (owner.current()) notifications = result; }).catch(() => {});
		api.get<IdentitySummary>('/api/v1/admin/identity/summary', owner.token, owner.projectId)
			.then(result => { if (owner.current()) identitySummary = result; }).catch(() => {});
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
	<PageHeader
		breadcrumb={t('overview.page.breadcrumb')}
		title={t('overview.page.title')}
		subtitle={t('overview.page.subtitle')}
	/>

	{#if notifications.length > 0}
		{@const critCount = notifications.filter(n => n.severity === 'critical').length}
		{@const warnCount = notifications.filter(n => n.severity === 'warning').length}
		<Alert tone={critCount > 0 ? 'danger' : 'warning'} class="notification-alert">
			<span class="text-sm" style="color: var(--color-ink-1);">
				{#if critCount > 0}
					<span class="font-semibold" style="color: var(--color-state-danger);">{t('overview.notifications.critical', { count: critCount.toLocaleString(intlLocale(), { useGrouping: false }) })}</span> ·
				{/if}
				{#if warnCount > 0}
					<span class="font-semibold" style="color: var(--color-state-warning);">{t('overview.notifications.warning', { count: warnCount.toLocaleString(intlLocale(), { useGrouping: false }) })}</span> ·
				{/if}
				{t('overview.notifications.info', { count: (notifications.length - critCount - warnCount).toLocaleString(intlLocale(), { useGrouping: false }) })}
				<a href="/admin/monitoring" class="underline" style="color: var(--admin-tone);">{t('overview.notifications.monitoringDetails')}</a>
			</span>
		</Alert>
	{/if}

	{#if error}
		<Alert tone="danger">{error}</Alert>
	{/if}


	{#if overviewLoading}
		<div class="flex flex-col gap-5" role="status" aria-busy="true" aria-label={t('overview.loading')}>
			<div class="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3">
				{#each Array(3) as _}
					<div class="h-[82px] motion-skeleton"></div>
				{/each}
			</div>
			<div class="motion-skeleton border border-line rounded-lg h-[260px]"></div>
		</div>
	{:else if overview}
		<KpiCardRow {overview} />

		<!-- Identity 통계: 사용자/프로젝트/역할/그룹 -->
		{#if identitySummary}
			<div class="motion-enter grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4">
				<a href="/admin/users" class="block">
					<StatTile label={t('overview.identity.users')} value={identitySummary.user_count} unit={t('overview.identity.peopleUnit', { count: identitySummary.user_count })} accent="amber" flat class="h-full">
						{#snippet icon()}
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
								<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8"/>
							</svg>
						{/snippet}
						{#if identitySummary.recent_users && identitySummary.recent_users.length > 0}
							{#snippet footer()}
								<span class="flex items-center gap-1 text-xs text-state-success-text">
									<span class="w-1.5 h-1.5 rounded-full bg-state-success shrink-0 animate-pulse"></span>
									{t('overview.identity.recentUsers', { count: identitySummary?.recent_users?.length ?? 0 })}
								</span>
							{/snippet}
						{/if}
					</StatTile>
				</a>
				<a href="/admin/projects" class="block">
					<StatTile label={t('overview.identity.projects')} value={identitySummary.project_count} unit={t('overview.identity.active')} accent="blue" flat class="h-full">
						{#snippet icon()}
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
								<path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
							</svg>
						{/snippet}
						{#if identitySummary.recent_projects && identitySummary.recent_projects.length > 0}
							{#snippet footer()}
								<span class="flex items-center gap-1 text-xs text-state-success-text">
									<span class="w-1.5 h-1.5 rounded-full bg-state-success shrink-0 animate-pulse"></span>
									{t('overview.identity.recentProjects', { count: identitySummary?.recent_projects?.length ?? 0 })}
								</span>
							{/snippet}
						{/if}
					</StatTile>
				</a>
				<a href="/admin/roles" class="block">
					<StatTile label={t('overview.identity.roles')} value={identitySummary.role_count} unit={t('overview.identity.defined')} accent="violet" flat class="h-full">
						{#snippet icon()}
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
								<path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
							</svg>
						{/snippet}
					</StatTile>
				</a>
				<a href="/admin/groups" class="block">
					<StatTile label={t('overview.identity.groups')} value={identitySummary.group_count} unit={t('overview.identity.groupsUnit', { count: identitySummary.group_count })} accent="cyan" flat class="h-full">
						{#snippet icon()}
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
								<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/>
								<circle cx="9" cy="7" r="4"/>
								<path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>
							</svg>
						{/snippet}
					</StatTile>
				</a>
			</div>

			{#if identitySummary.partial && identitySummary.partial_reasons && identitySummary.partial_reasons.length > 0}
				<div class="flex items-center gap-2.5 px-4 py-2.5 rounded-lg border text-xs"
				     style="background: color-mix(in oklab, var(--color-state-warning) 10%, transparent); border-color: color-mix(in oklab, var(--color-state-warning) 30%, transparent); color: var(--color-state-warning);">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="flex-shrink-0">
						<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
						<line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
					</svg>
					<span>{t('overview.identity.partial', { reasons: identitySummary.partial_reasons.map(r => r.includes('insufficient_privileges') ? t('overview.identity.insufficientPrivileges', { target: r.split(':')[0] }) : r).join(', ') })}</span>
				</div>
			{/if}
		{/if}

		<ResourceDonutsCard {overview} />

		<div class="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-3.5">
			<DomainUsageTable domains={domainUsage} loading={domainUsageLoading} error={domainUsageError} />
			<ServiceCountCards {overview} />
		</div>

		<!-- 퀵 링크 -->
		<div class="flex gap-3 flex-wrap text-sm">
			<a href="/admin/hypervisors" class="text-ink-2 hover:text-ink-0 transition-colors">{t('overview.links.hypervisors')}</a>
			<a href="/admin/instances" class="text-ink-2 hover:text-ink-0 transition-colors">{t('overview.links.instances')}</a>
			<a href="/admin/containers" class="text-ink-2 hover:text-ink-0 transition-colors">{t('overview.links.containers')}</a>
			<a href="/admin/file-storage" class="text-ink-2 hover:text-ink-0 transition-colors">{t('overview.links.fileStorage')}</a>
			<a href="/admin/database-instances" class="text-ink-2 hover:text-ink-0 transition-colors">{t('overview.links.database')}</a>
			<a href="/admin/object-storage" class="text-ink-2 hover:text-ink-0 transition-colors">{t('overview.links.objectStorage')}</a>
			<a href="/admin/topology" class="text-ink-2 hover:text-ink-0 transition-colors">{t('overview.links.topology')}</a>
			<a href="/admin/networks" class="text-ink-2 hover:text-ink-0 transition-colors">{t('overview.links.networks')}</a>
		</div>

		<VersionInfoPanel {versionInfo} bind:open={versionOpen} />
	{:else}
		<div class="text-ink-2 text-sm">{t('overview.page.unavailable')}</div>
	{/if}
</PageShell>

