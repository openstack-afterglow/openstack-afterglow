<script lang="ts">
	import { untrack } from 'svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import { auth, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { projectNames } from '$lib/stores/projectNames';
	import RichText from '$lib/i18n/RichText.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { t as tc } from '$lib/i18n/ns/common';

	interface Project {
		id: string;
		name: string;
		description: string;
		enabled: boolean;
		domain_id: string | null;
		created_at: string | null;
	}

	let {
		project,
		onClose,
		onSuccess,
	}: {
		project: Project | null;
		onClose: () => void;
		onSuccess: () => void;
	} = $props();

	interface ResourceCheck {
		kind: string;
		service: string;
		status: string;
		count: number | null;
		samples: Array<{ id: string; name?: string | null }>;
		reason: string | null;
	}
	interface DeletionCheck {
		project_id: string;
		checked_at: string;
		can_delete: boolean;
		resources: ResourceCheck[];
	}
	interface Scope {
		target: string;
		token: string;
		projectId: string | undefined;
		userId: string | null;
	}
	const resourceKeys = {
		instances: 'projectDelete.resources.instances', server_groups: 'projectDelete.resources.server_groups',
		volumes: 'projectDelete.resources.volumes', volume_snapshots: 'projectDelete.resources.volume_snapshots',
		volume_backups: 'projectDelete.resources.volume_backups', networks: 'projectDelete.resources.networks',
		subnets: 'projectDelete.resources.subnets', routers: 'projectDelete.resources.routers',
		ports: 'projectDelete.resources.ports', floating_ips: 'projectDelete.resources.floating_ips',
		security_groups: 'projectDelete.resources.security_groups', images: 'projectDelete.resources.images',
		load_balancers: 'projectDelete.resources.load_balancers', shares: 'projectDelete.resources.shares',
		share_snapshots: 'projectDelete.resources.share_snapshots', object_containers: 'projectDelete.resources.object_containers',
		secrets: 'projectDelete.resources.secrets', secret_containers: 'projectDelete.resources.secret_containers',
		database_instances: 'projectDelete.resources.database_instances', database_backups: 'projectDelete.resources.database_backups',
		containers: 'projectDelete.resources.containers', clusters: 'projectDelete.resources.clusters', stacks: 'projectDelete.resources.stacks',
		share_networks: 'projectDelete.resources.share_networks', security_services: 'projectDelete.resources.security_services',
		secret_orders: 'projectDelete.resources.secret_orders', database_configurations: 'projectDelete.resources.database_configurations',
		cluster_templates: 'projectDelete.resources.cluster_templates',
	} as const;
	const serviceKeys = {
		compute: 'projectDelete.services.compute', volume: 'projectDelete.services.volume',
		network: 'projectDelete.services.network', image: 'projectDelete.services.image',
		load_balancer: 'projectDelete.services.load_balancer', share: 'projectDelete.services.share',
		object_store: 'projectDelete.services.object_store', key_manager: 'projectDelete.services.key_manager',
		database: 'projectDelete.services.database', container: 'projectDelete.services.container',
		container_infra: 'projectDelete.services.container_infra', orchestration: 'projectDelete.services.orchestration',
	} as const;
	function resourceLabel(kind: string) {
		return Object.hasOwn(resourceKeys, kind) ? t(resourceKeys[kind as keyof typeof resourceKeys]) : t('projectDelete.resources.other');
	}
	function serviceLabel(service: string) {
		return Object.hasOwn(serviceKeys, service) ? t(serviceKeys[service as keyof typeof serviceKeys]) : t('projectDelete.services.other');
	}
	function isRecord(value: unknown): value is Record<string, unknown> {
		return !!value && typeof value === 'object' && !Array.isArray(value);
	}
	// Reports are target-bound, including reports embedded in a final DELETE refusal.
	function readReport(value: unknown, target: string): DeletionCheck | null {
		if (!isRecord(value) || value.project_id !== target || typeof value.checked_at !== 'string'
			|| typeof value.can_delete !== 'boolean' || !Array.isArray(value.resources) || !value.resources.length) return null;
		const resources: ResourceCheck[] = [];
		for (const row of value.resources) {
			if (!isRecord(row) || typeof row.kind !== 'string' || typeof row.service !== 'string'
				|| typeof row.status !== 'string' || !Array.isArray(row.samples)
				|| !(row.count === null || (typeof row.count === 'number' && Number.isSafeInteger(row.count) && row.count >= 0))) return null;
			const samples: ResourceCheck['samples'] = [];
			for (const sample of row.samples.slice(0, 5)) {
				if (!isRecord(sample) || typeof sample.id !== 'string') continue;
				samples.push({ id: sample.id.slice(0, 160), name: typeof sample.name === 'string' ? sample.name.slice(0, 160) : null });
			}
			resources.push({ kind: row.kind, service: row.service, status: row.status, count: row.count,
				samples, reason: typeof row.reason === 'string' ? row.reason : null });
		}
		return { project_id: target, checked_at: value.checked_at, can_delete: value.can_delete, resources };
	}
	function absent(row: ResourceCheck) {
		return row.status === 'skipped' && row.reason === 'service_not_present' && row.count === null;
	}
	function unknown(row: ResourceCheck) {
		return !absent(row) && (row.status !== 'ok' || row.count === null);
	}
	function reasonLabel(reason: string | null) {
		if (reason === 'admin_authority_unverified') return t('projectDelete.adminAuthorityUnverified');
		if (reason === 'project_scope_unverified') return t('projectDelete.scopeUnverified');
		if (reason === 'resource_ownership_unverified') return t('projectDelete.ownershipUnverified');
		if (reason === 'service_catalog_unavailable') return t('projectDelete.catalogUnavailable');
		if (reason === 'resource_check_failed') return t('projectDelete.inspectionUnavailable');
		return t('projectDelete.unknown');
	}

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	let scope = $state.raw<Scope | null>(null);
	let report = $state.raw<DeletionCheck | null>(null);
	let checking = $state(false);
	let checkError = $state('');
	let deleting = $state(false);
	let deleteError = $state('');
	let controller: AbortController | null = null;
	const canDelete = $derived(!!scope && current(scope) && !checking && !deleting && !!report?.can_delete
		&& report.project_id === scope.target && report.resources.every((row) => absent(row) || (row.status === 'ok' && row.count === 0)));

	function current(requestScope: Scope) {
		return scope === requestScope && project?.id === requestScope.target && token === requestScope.token
			&& projectId === requestScope.projectId && $auth.userId === requestScope.userId
			&& $auth.isSystemAdmin && !$logoutInProgress && !$projectSwitching;
	}
	$effect(() => {
		const target = project?.id;
		const accessToken = token;
		const callerProject = projectId;
		const userId = $auth.userId;
		const permitted = $auth.isSystemAdmin && !$logoutInProgress && !$projectSwitching;
		untrack(() => {
			controller?.abort();
			report = null;
			checkError = '';
			deleteError = '';
			deleting = false;
			checking = false;
			scope = target && accessToken && permitted ? { target, token: accessToken, projectId: callerProject, userId } : null;
			if (scope) void inspect(scope);
			else if (target) checkError = t('projectDelete.checkFailed');
		});
		return () => { controller?.abort(); scope = null; };
	});

	async function inspect(requestScope: Scope) {
		if (!current(requestScope) || deleting) return;
		controller?.abort();
		const request = new AbortController();
		controller = request;
		checking = true;
		report = null;
		checkError = '';
		try {
			const result = await api.get<unknown>(`/api/v1/admin/projects/${encodeURIComponent(requestScope.target)}/deletion-check`,
				requestScope.token, requestScope.projectId, { refresh: true, signal: request.signal });
			if (!current(requestScope) || request.signal.aborted || controller !== request) return;
			report = readReport(result, requestScope.target);
			if (!report) checkError = t('projectDelete.checkFailed');
		} catch {
			if (current(requestScope) && !request.signal.aborted && controller === request) checkError = t('projectDelete.checkFailed');
		} finally {
			if (current(requestScope) && controller === request) checking = false;
		}
	}
	function close() {
		if (deleting) return;
		controller?.abort();
		scope = null;
		report = null;
		onClose();
	}
	async function confirmDelete() {
		if (!canDelete || !scope) return;
		const requestScope = scope;
		const success = onSuccess;
		const dismiss = onClose;
		deleting = true;
		deleteError = '';
		const namesScope = projectNames.scope(requestScope.token, requestScope.projectId);
		projectNames.invalidate(namesScope);
		try {
			await api.delete(`/api/v1/admin/projects/${encodeURIComponent(requestScope.target)}`, requestScope.token, requestScope.projectId);
			projectNames.invalidate(namesScope);
			if (!current(requestScope)) return;
			scope = null;
			report = null;
			deleting = false;
			success();
			dismiss();
		} catch (e) {
			if (!current(requestScope)) return;
			report = null;
			if (e instanceof ApiError && (e.status === 409 || e.status === 503)) {
				let detail: Record<string, unknown> | null = null;
				try {
					const parsed: unknown = JSON.parse(e.message);
					if (isRecord(parsed)) detail = isRecord(parsed.detail) ? parsed.detail : parsed;
				} catch { /* Older servers may return a plain refusal message. */ }
				const resourcesRemain = detail?.code === 'project_has_resources';
				deleteError = t(resourcesRemain ? 'projectDelete.finalResources' : 'projectDelete.finalCheckFailed');
				if (resourcesRemain || detail?.code === 'project_resource_check_failed' || detail?.code === 'resource_check_failed') {
					report = readReport(detail?.check, requestScope.target);
					if (report) report = { ...report, can_delete: false };
				}
				deleting = false;
				if (!report) await inspect(requestScope);
			} else {
				deleteError = e instanceof Error && e.message && !/^[\s]*[\[{]/.test(e.message) ? e.message : t('projectDelete.failed');
			}
		} finally {
			if (current(requestScope)) deleting = false;
		}
	}
</script>

{#snippet nameTag(text: string)}<span class="text-ink-0 font-medium">{text}</span>{/snippet}

{#if project}
	{#key project.id}
	<FormModal open={true} title={t('projectDelete.title')} onClose={close} submitting={deleting}>
		<div class="space-y-3 min-w-0">
			<p class="text-sm text-ink-2 break-words"><RichText segments={t.rich('projectDelete.body', { name: project.name })} tags={{ name: nameTag }} /></p>
			<p class="text-xs text-[var(--color-state-danger-text)]">{t('projectDelete.irreversible')}</p>
			{#if deleteError}<Alert tone="danger">{deleteError}</Alert>{/if}
			{#if checking}
				<div class="flex items-center gap-2 text-sm text-ink-2" role="status" aria-live="polite">
					<ActivityIndicator size="xs" />{t('projectDelete.checking')}
				</div>
			{:else if checkError}
				<Alert tone="danger">{checkError}</Alert>
			{:else if report && scope && current(scope)}
				{#if report.resources.some(unknown)}
					<Alert tone="warning">{t('projectDelete.unavailable')}</Alert>
				{:else if report.resources.some((row) => (row.count ?? 0) > 0)}
					<Alert tone="warning">{t('projectDelete.blocked')}</Alert>
				{:else if canDelete || deleting}
					<Alert tone="success">{t('projectDelete.empty')}</Alert>
				{:else}
					<Alert tone="warning">{t('projectDelete.unavailable')}</Alert>
				{/if}
				<ul class="max-h-[40dvh] overflow-y-auto divide-y divide-line text-sm" aria-label={t('projectDelete.reportLabel')}>
					{#each report.resources as row}
						<li class="py-2 min-w-0">
							<div class="flex flex-wrap justify-between gap-x-3 gap-y-1">
								<span class="text-ink-0 font-medium">{resourceLabel(row.kind)}</span>
								<span class="text-ink-2">{#if row.count !== null && row.count > 0}{t('projectDelete.count', { count: row.count })}{:else if absent(row)}{t('projectDelete.notPresent')}{:else if unknown(row)}{t('projectDelete.unknown')}{:else}{t('projectDelete.count', { count: 0 })}{/if}</span>
							</div>
							<p class="text-xs text-ink-2">{serviceLabel(row.service)}{#if unknown(row)} · {reasonLabel(row.reason)}{/if}</p>
							{#if row.samples.length && row.count !== 0}
								<ul class="mt-1 space-y-1 text-xs text-ink-2 break-all">
									{#each row.samples as sample}
										<li>{#if sample.name && row.kind !== 'secrets' && row.kind !== 'secret_containers'}{sample.name} — {/if}<span class="font-mono">{sample.id}</span></li>
									{/each}
								</ul>
								<p class="mt-1 text-xs text-ink-2">{t('projectDelete.samplesHint')}</p>
							{/if}
						</li>
					{/each}
					</ul>
			{/if}
			<Button variant="secondary" size="sm" disabled={!scope || checking || deleting} onclick={() => { if (scope) { deleteError = ''; void inspect(scope); } }}>
				{t('projectDelete.recheck')}
			</Button>
		</div>
		{#snippet actions()}
			<Button onclick={close} variant="secondary" disabled={deleting}>{tc('actions.cancel')}</Button>
			<Button onclick={confirmDelete} variant="danger" disabled={!canDelete} ariaBusy={deleting}>
				{#if deleting}{t('state.deleting')}{:else}{t('actions.delete')}{/if}
			</Button>
		{/snippet}
	</FormModal>
	{/key}
{/if}
