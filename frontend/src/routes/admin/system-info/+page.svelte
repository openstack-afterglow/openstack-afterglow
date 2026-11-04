<script lang="ts">
	import { onMount } from 'svelte';
	import { derived, get } from 'svelte/store';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { authDisplayContext } from '$lib/stores/authDisplayContext';
	import { api } from '$lib/api/client';
	import { t } from '$lib/i18n/ns/admin-ops';
	import { t as tn } from '$lib/i18n/ns/nav';
	import { t as tc } from '$lib/i18n/ns/common';
	import { Alert, Button, LoadingState, PageHeader, PageShell } from '$lib/components/ui';
	import VersionInfoPanel from '$lib/components/admin/system-info/VersionInfoPanel.svelte';
	import ServiceVersionsPanel from '$lib/components/admin/system-info/ServiceVersionsPanel.svelte';
	import { ApiError } from '$lib/api/errors';
	import type { ServiceVersions, VersionInfo } from '$lib/types/adminOverview';

	let versionInfo = $state<VersionInfo | null>(null);
	let loading = $state(true);
	let failed = $state(false);
	let serviceVersions = $state<ServiceVersions | null>(null);
	let servicesLoading = $state(true);
	let servicesFailure = $state<'unavailable' | 'failed' | null>(null);
	let mounted = false;
	let generation = 0;
	const authorization = derived([authDisplayContext, auth, authReady, logoutInProgress, projectSwitching],
		([context, state, ready, loggingOut, switching]) =>
			state.token && state.isSystemAdmin && ready && !loggingOut && !switching ? context.key : null);
	let owner: string | null = null;

	async function load(refresh = false) {
		if (!mounted || owner === null || get(authorization) !== owner || (refresh && (loading || servicesLoading))) return;
		const request = ++generation;
		const requestOwner = owner;
		const state = get(auth);
		const current = () => mounted && request === generation && requestOwner === get(authorization);
		loading = true;
		failed = false;
		servicesLoading = true;
		servicesFailure = null;
		await Promise.all([
			(async () => {
				try {
					const result = await api.get<VersionInfo>('/api/v1/admin/version', state.token ?? undefined, state.projectId ?? undefined, { refresh });
					if (current()) versionInfo = result;
				} catch {
					if (current()) failed = true;
				} finally {
					if (current()) loading = false;
				}
			})(),
			(async () => {
				try {
					const result = await api.get<ServiceVersions>('/api/v1/admin/service-versions', state.token ?? undefined, state.projectId ?? undefined, { refresh });
					if (current()) serviceVersions = result;
				} catch (error) {
					if (current()) {
						servicesFailure = error instanceof ApiError && error.status === 404 ? 'unavailable' : 'failed';
						if (servicesFailure === 'unavailable') serviceVersions = null;
					}
				} finally {
					if (current()) servicesLoading = false;
				}
			})(),
		]);
	}

	onMount(() => {
		mounted = true;
		const unsubscribe = authorization.subscribe(next => {
			if (next === owner) return;
			owner = next;
			++generation;
			versionInfo = null;
			failed = false;
			loading = true;
			serviceVersions = null;
			servicesFailure = null;
			servicesLoading = true;
			if (next !== null) void load();
		});
		return () => { mounted = false; ++generation; unsubscribe(); };
	});
</script>

<PageShell class="flex flex-col gap-5">
	<PageHeader breadcrumb={tn('sections.system')} title={tn('items.systemInfo')}>
		{#snippet actions()}
			<Button variant="secondary" disabled={loading || servicesLoading || $authorization === null} onclick={() => load(true)}>{tc('autoRefresh.refreshNow')}</Button>
		{/snippet}
	</PageHeader>
	{#if failed}<Alert tone="danger">{t('systemInfo.loadFailed')}</Alert>{/if}
	{#if loading}<LoadingState variant={versionInfo ? 'inline' : 'section'} label={tc('state.loadingNamed', { name: tn('items.systemInfo') })} />{/if}
	{#if versionInfo}<VersionInfoPanel {versionInfo} />{/if}
	<ServiceVersionsPanel data={serviceVersions} loading={servicesLoading} failure={servicesFailure} />
</PageShell>
