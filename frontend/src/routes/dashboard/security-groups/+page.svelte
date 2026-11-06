<script lang="ts">
	import { t as tl } from '$lib/i18n/ns/common';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { t } from '$lib/i18n/ns/network-resources';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { auth } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { api, ApiError } from '$lib/api/client';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import SecurityGroupCard from '$lib/components/dashboard/security-groups/SecurityGroupCard.svelte';
	import SecurityGroupCreateModal from '$lib/components/dashboard/security-groups/SecurityGroupCreateModal.svelte';

	import type { SecurityGroupRule, SecurityGroup } from '$lib/types/securityGroup';
	import { toast } from '$lib/stores/toast';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import { untrack } from 'svelte';
	import { t as tp } from '$lib/i18n/ns/network-pages';

	let securityGroups = $state<SecurityGroup[]>([]);
	let loading = $state(true);
	let sgError = $state('');
	let showSgModal = $state(false);
	let search = $state('');
	const columns = (): TableColumn<SecurityGroup>[] => [
		{ key: 'name', label: t('network.labels.name'), value: row => row.name },
		{ key: 'description', label: t('securityGroup.create.description'), value: row => row.description },
		{ key: 'rules', label: tp('securityGroupRules.rulesLabel'), value: row => row.rules.length },
	];
	const view = createTableView({ rows: () => securityGroups, columns, search: () => search, searchable: row => [row.name, row.id, row.description ?? ''] });

	async function fetchSecurityGroups() {
		try {
			securityGroups = await api.get<SecurityGroup[]>('/api/v1/security-groups', $auth.token ?? undefined, $auth.projectId ?? undefined);
			sgError = '';
		} catch (e) {
			sgError = e instanceof ApiError ? t('securityGroup.error.load', { status: e.status, error: (e as ApiError).message }) : t('securityGroup.error.server');
		} finally {
			loading = false;
		}
	}

	async function createSecurityGroup(form: { name: string; description: string }): Promise<string | true> {
		if (!form.name.trim()) return t('securityGroup.error.nameRequired');
		try {
			await api.post('/api/v1/security-groups', form, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await fetchSecurityGroups();
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : t('securityGroup.error.create');
		}
	}

	async function deleteSecurityGroup(sgId: string, name: string) {
		if (!await confirmDialog(t('securityGroup.confirm.delete', { name }))) return;
		try {
			await api.delete(`/api/v1/security-groups/${sgId}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await fetchSecurityGroups();
		} catch (e) {
			toast.error(t('securityGroup.error.delete', { error: e instanceof ApiError ? e.message : String(e) }));
		}
	}

	async function addSgRule(
		sgId: string,
		form: { direction: string; protocol: string; port_range_min: string; port_range_max: string; remote_ip_prefix: string; ethertype: string }
	): Promise<string | true> {
		try {
			const body: Record<string, unknown> = {
				direction: form.direction,
				ethertype: form.ethertype,
			};
			if (form.protocol) body.protocol = form.protocol;
			if (form.port_range_min) body.port_range_min = parseInt(form.port_range_min);
			if (form.port_range_max) body.port_range_max = parseInt(form.port_range_max);
			if (form.remote_ip_prefix) body.remote_ip_prefix = form.remote_ip_prefix;
			await api.post(`/api/v1/security-groups/${sgId}/rules`, body, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await fetchSecurityGroups();
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : t('securityGroup.error.addRule');
		}
	}

	async function deleteSgRule(sgId: string, ruleId: string) {
		try {
			await api.delete(`/api/v1/security-groups/${sgId}/rules/${ruleId}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await fetchSecurityGroups();
		} catch (e) {
			toast.error(t('securityGroup.error.deleteRule', { error: e instanceof ApiError ? e.message : String(e) }));
		}
	}

	const viewOwner = $derived(sessionScopeKey($auth));
	$effect(() => {
		viewOwner;
		const projectId = untrack(() => $auth.projectId);
		untrack(() => {
			search = ''; view.reset();
			if (projectId) void fetchSecurityGroups();
		});
	});
</script>

<PageShell>
	<div class="flex items-center justify-between mb-6">
		<div>
			<div class="flex items-center gap-2 text-sm text-ink-2 mb-1">
				<a href="/dashboard" class="hover:text-ink-2 transition-colors">{t('securityGroup.page.dashboard')}</a>
				<span>›</span>
				<span class="text-ink-2">{t('securityGroup.page.title')}</span>
			</div>
			<h1 class="text-xl font-semibold text-ink-0">{t('securityGroup.page.title')}</h1>
		</div>
		<button
			onclick={() => { showSgModal = true; }}
			class="bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm px-4 py-2 rounded-lg transition-colors"
		>{t('securityGroup.page.create')}</button>
	</div>

	<RegexSearch id="legacy-security-group-search" bind:value={search} />
	<TableViewControls {view} class="" />
	{#if securityGroups.length > 0 && view.rows.length === 0}<p class="text-sm text-ink-2">{tl('table.noMatches')}</p>{/if}
	{#if sgError}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{sgError}</div>
	{/if}

	{#if loading}
		<LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('securityGroup.page.title') })} />
	{:else if securityGroups.length === 0}
		<div class="text-center py-20 text-ink-2">
			<div class="text-5xl mb-4">🔒</div>
			<div class="text-lg">{t('securityGroup.page.empty')}</div>
		</div>
	{:else}
		<div class="motion-stagger space-y-3">
			{#each view.rows as sg (sg.id)}
				<SecurityGroupCard
					{sg}
					onDelete={deleteSecurityGroup}
					onAddRule={addSgRule}
					onDeleteRule={deleteSgRule}
				/>
			{/each}
		</div>
	{/if}
</PageShell>

<SecurityGroupCreateModal bind:open={showSgModal} onCreate={createSecurityGroup} />
