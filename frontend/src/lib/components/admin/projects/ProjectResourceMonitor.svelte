<script lang="ts">
	import { untrack } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { createPrivateViewScope } from '$lib/utils/privateViewScope';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { t as tc } from '$lib/i18n/ns/common';

	let { projectId, domainId, kind = 'instances', onKindChange }: {
		projectId: string; domainId: string; kind?: string; onKindChange: (kind: string) => void;
	} = $props();
	const kinds = ['instances', 'server_groups', 'volumes', 'volume_snapshots', 'volume_backups',
		'networks', 'subnets', 'routers', 'ports', 'floating_ips', 'security_groups', 'images',
		'load_balancers', 'shares', 'share_snapshots', 'object_containers', 'secrets', 'secret_containers',
		'database_instances', 'database_backups', 'containers', 'clusters', 'stacks', 'share_networks',
		'security_services', 'secret_orders', 'database_configurations', 'cluster_templates', 'child_projects'] as const;
	type Kind = typeof kinds[number];
	interface Resource { id: string; name: string | null; status: string | null }
	interface Inventory { status: 'ok' | 'unavailable' | 'skipped'; reason: string | null; resources: Resource[]; count: number | null }
	interface Scope { project: string; domain: string; kind: Kind; revision: number }
	const privateScope = createPrivateViewScope();
	const id = $props.id();
	let scope = $state.raw<Scope | null>(null);
	let inventory = $state.raw<Inventory | null>(null);
	let loading = $state(false);
	let error = $state('');
	let selected = $state.raw<Resource | null>(null);
	let confirmation = $state('');
	let submitting = $state(false);
	let outcomes = $state<Record<string, 'accepted' | 'unknown'>>({});
	let notice = $state<'accepted' | 'unknown' | 'readback' | 'refused' | null>(null);
	let controller: AbortController | null = null;
	const ready = $derived($authReady && !!$auth.token && $auth.isSystemAdmin && !$logoutInProgress && !$projectSwitching);
	const validKind = (value: string): value is Kind => kinds.includes(value as Kind);
	function label(value: Kind) { return t(`projectDelete.resources.${value}`); }
	function outcome(resourceId: string) { return Object.hasOwn(outcomes, resourceId) ? outcomes[resourceId] : undefined; }
	function reasonLabel(reason: string | null) {
		if (reason === 'admin_authority_unverified') return t('projectDelete.adminAuthorityUnverified');
		if (reason === 'project_scope_unverified') return t('projectDelete.scopeUnverified');
		if (reason === 'resource_ownership_unverified') return t('projectDelete.ownershipUnverified');
		if (reason === 'service_catalog_unavailable') return t('projectDelete.catalogUnavailable');
		return null;
	}
	function sameScope(value: Scope) {
		return scope === value && projectId === value.project && domainId === value.domain && kind === value.kind
			&& $privateScope === value.revision && !!$auth.token && $auth.isSystemAdmin && !$logoutInProgress && !$projectSwitching;
	}
	function current(value: Scope) { return sameScope(value) && ready; }
	function endpoint(value: Scope) {
		return `/api/v1/admin/projects/${encodeURIComponent(value.project)}/resources`;
	}
	function query(value: Scope) { return new URLSearchParams({ domain_id: value.domain, kind: value.kind }); }
	function parse(value: unknown, target: Scope): Inventory {
		if (!value || typeof value !== 'object') throw new Error('invalid inventory');
		const result = value as Record<string, unknown>;
		if (result.project_id !== target.project || result.kind !== target.kind || !Array.isArray(result.resources)
			|| !['ok', 'unavailable', 'skipped'].includes(String(result.status))
			|| !(result.reason === null || typeof result.reason === 'string')) throw new Error('invalid inventory');
		const seen = new Set<string>();
		const resources: Resource[] = result.resources.map((row: unknown) => {
			if (!row || typeof row !== 'object') throw new Error('invalid resource');
			const item = row as Record<string, unknown>;
			if (typeof item.id !== 'string' || !item.id || seen.has(item.id)
				|| !(item.name == null || typeof item.name === 'string')
				|| !(item.status == null || typeof item.status === 'string')) throw new Error('invalid resource');
			seen.add(item.id);
			return { id: item.id, name: target.kind.startsWith('secret') ? null : (item.name as string | null) ?? null,
				status: (item.status as string | null) ?? null };
		});
		if (result.status === 'ok' ? result.count !== resources.length : result.count !== null || resources.length !== 0) throw new Error('incomplete inventory');
		return { status: result.status as Inventory['status'], reason: result.reason as string | null, resources, count: result.count as number | null };
	}
	$effect(() => {
		const target = projectId; const domain = domainId; const category = kind; const revision = $privateScope;
		const loggingOut = $logoutInProgress; const switching = $projectSwitching;
		untrack(() => {
			controller?.abort(); selected = null; confirmation = ''; submitting = false;
			inventory = null; outcomes = {}; notice = null; error = ''; loading = false;
			scope = target && domain && validKind(category) && !loggingOut && !switching
				? { project: target, domain, kind: category, revision } : null;
			if (scope && ready) void load(scope);
			else error = t('resourceMonitor.invalidScope');
		});
		return () => { controller?.abort(); scope = null; };
	});
	$effect(() => {
		if (ready) untrack(() => {
			if (scope && !loading && !inventory && error === t('resourceMonitor.invalidScope')) void load(scope);
		});
	});
	async function load(target: Scope, explicit = false): Promise<Inventory | null> {
		if (!current(target)) return null;
		controller?.abort();
		const request = new AbortController(); controller = request;
		loading = true; error = ''; inventory = null;
		try {
			const value = await api.get<unknown>(`${endpoint(target)}?${query(target)}`, $auth.token ?? undefined, $auth.projectId ?? undefined,
				{ refresh: true, cache: 'no-store', signal: request.signal });
			if (!current(target) || request.signal.aborted || controller !== request) return null;
			const result = parse(value, target); inventory = result;
			if (explicit && result.status === 'ok') {
				// A new list permits a new explicit review, never replays the previous request.
				outcomes = Object.fromEntries(Object.entries(outcomes).filter(([resourceId, state]) => state === 'accepted' && result.resources.some(row => row.id === resourceId)));
				if (notice === 'unknown') notice = 'readback';
			}
			return result;
		} catch {
			if (current(target) && !request.signal.aborted && controller === request) error = t('resourceMonitor.loadFailed');
			return null;
		} finally { if (scope === target && controller === request) loading = false; }
	}
	function choose(value: string) {
		if (value === kind) return;
		controller?.abort(); selected = null; confirmation = ''; inventory = null;
		onKindChange(value);
	}
	function close() { if (!submitting) { selected = null; confirmation = ''; } }
	async function remove() {
		if (!scope || !current(scope) || !selected || submitting || confirmation !== selected.id || outcome(selected.id)) return;
		const target = scope; const resource = selected;
		submitting = true;
		// Re-read complete exact-project inventory immediately before the single mutation.
		const fresh = await load(target);
		if (!current(target)) {
			if (scope === target) { submitting = false; selected = null; confirmation = ''; }
			return;
		}
		if (!fresh || fresh.status !== 'ok' || !fresh.resources.some(row => row.id === resource.id)) {
			submitting = false; selected = null; confirmation = ''; error = t('resourceMonitor.changed'); return;
		}
		try {
			await api.delete(`${endpoint(target)}/${encodeURIComponent(target.kind)}/${encodeURIComponent(resource.id)}?${new URLSearchParams({ domain_id: target.domain })}`,
				$auth.token ?? undefined, $auth.projectId ?? undefined, { replayOnUnauthorized: false });
			if (!sameScope(target)) return;
			outcomes = { ...outcomes, [resource.id]: 'accepted' }; notice = 'accepted';
			selected = null; confirmation = '';
			await load(target);
		} catch (reason) {
			if (!sameScope(target)) return;
			if (reason instanceof ApiError && [400, 403, 404, 409, 412, 422].includes(reason.status)) notice = 'refused';
			else { outcomes = { ...outcomes, [resource.id]: 'unknown' }; notice = 'unknown'; }
			selected = null; confirmation = ''; inventory = null;
		} finally { if (scope === target) submitting = false; }
	}
</script>

<PageShell class="space-y-5">
	<PageHeader breadcrumb={t('projectDetail.breadcrumb')} title={t('resourceMonitor.title')} subtitle={t('resourceMonitor.help')}>
		{#snippet actions()}
			<nav aria-label={t('projectDetail.breadcrumb')}>
				<Button variant="secondary" class="min-h-11" href={`/admin/projects?${new URLSearchParams({ domain_id: domainId })}`}>{t('resourceMonitor.back')}</Button>
			</nav>
		{/snippet}
	</PageHeader>
	<dl class="grid min-w-0 gap-3 text-sm sm:grid-cols-2">
		<div class="min-w-0"><dt class="text-ink-2">{t('projectDetail.projectId')}</dt><dd class="break-all font-mono">{projectId}</dd></div>
		<div class="min-w-0"><dt class="text-ink-2">{t('projectDetail.domainId')}</dt><dd class="break-all font-mono">{domainId}</dd></div>
	</dl>
	<div class="flex flex-wrap items-end gap-3">
		<div class="w-full min-w-0 sm:w-80"><Field for={`${id}-kind`} label={t('resourceMonitor.kind')}>
			<SelectInput id={`${id}-kind`} value={kind} class="min-h-11" onchange={(event) => choose((event.target as HTMLSelectElement).value)}>
				{#if !validKind(kind)}<option value={kind}>{t('resourceMonitor.invalidKind')}</option>{/if}
				{#each kinds as category}<option value={category}>{label(category)}</option>{/each}
			</SelectInput>
		</Field></div>
		<Button variant="secondary" class="min-h-11" disabled={!ready || !scope || loading || submitting} onclick={() => { if (scope) { selected = null; confirmation = ''; void load(scope, true); } }}>{t('resourceMonitor.refresh')}</Button>
	</div>
	{#if ready}
		{#if notice}<Alert tone="warning">{t(`resourceMonitor.${notice}`)}</Alert>{/if}
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		{#if loading}<div role="status"><ActivityIndicator label={t('resourceMonitor.loading')} /></div>
		{:else if inventory && scope && current(scope)}
			{#if inventory.status !== 'ok'}
				<Alert tone="warning">{inventory.status === 'skipped' && inventory.reason === 'service_not_present' ? t('projectDelete.notPresent') : t('resourceMonitor.unavailable')}</Alert>
				{#if reasonLabel(inventory.reason)}<p class="mt-2 text-sm text-ink-2">{reasonLabel(inventory.reason)}</p>{/if}
			{:else}
				<p class="text-sm text-ink-2" role="status">{t('resourceMonitor.count', { count: inventory.count ?? 0 })}</p>
				{#if inventory.resources.length === 0}<p class="text-sm text-ink-2">{t('resourceMonitor.empty')}</p>{/if}
				<ul aria-label={t('resourceMonitor.list')} class="divide-y divide-line rounded-lg border border-line bg-surface-base">
					{#each inventory.resources as resource (resource.id)}
						<li class="flex min-w-0 flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
							<div class="min-w-0 space-y-1">
								{#if resource.name}<p class="break-words text-sm font-medium">{resource.name}</p>{/if}
								<p class="break-all font-mono text-xs">{resource.id}</p>
								{#if resource.status}<StatusChip status={resource.status} />{/if}
								{#if outcome(resource.id)}<Pill tone="warning" class="max-w-full whitespace-normal! text-xs!">{t(outcome(resource.id) === 'accepted' ? 'resourceMonitor.pending' : 'resourceMonitor.unknownStatus')}</Pill>{/if}
							</div>
							<Button variant="danger-outline" class="min-h-11 shrink-0" disabled={submitting || !!outcome(resource.id)} ariaLabel={t('resourceMonitor.removeLabel', { id: resource.id })} onclick={() => { selected = resource; confirmation = ''; }}>{t('resourceMonitor.remove')}</Button>
						</li>
					{/each}
				</ul>
			{/if}
		{/if}
	{:else}<Alert tone="warning">{t('resourceMonitor.invalidScope')}</Alert>{/if}
</PageShell>
{#if selected && scope && current(scope)}
	<FormModal open={true} title={t('resourceMonitor.confirmTitle')} onClose={close} {submitting}>
		<div class="min-w-0 space-y-3">
			<Alert tone="warning">{t('resourceMonitor.confirmHelp')}</Alert>
			{#if selected.name}<p class="break-words text-sm font-medium">{selected.name}</p>{/if}
			<p class="break-all font-mono text-sm">{selected.id}</p>
			<Field for={`${id}-confirm`} label={t('resourceMonitor.confirmId')} help={t('resourceMonitor.confirmIdHelp')}>
				<TextInput id={`${id}-confirm`} bind:value={confirmation} disabled={submitting} />
			</Field>
		</div>
		{#snippet actions()}
			<Button variant="secondary" class="min-h-11" disabled={submitting} onclick={close}>{tc('actions.cancel')}</Button>
			<Button variant="danger" class="min-h-11" disabled={submitting || confirmation !== selected?.id} onclick={remove}>{t('resourceMonitor.remove')}</Button>
		{/snippet}
	</FormModal>
{/if}
