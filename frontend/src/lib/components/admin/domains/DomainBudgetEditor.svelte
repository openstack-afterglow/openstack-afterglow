<script lang="ts">
	import { untrack } from 'svelte';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { ApiError } from '$lib/api/client';
	import { adminDomainBudgets, quotaBlocked, type DomainBudgets, type QuotaMap } from '$lib/api/workspaceIam';
	import { t } from '$lib/i18n/ns/workspace-iam';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import BudgetSummary from '$lib/components/iam/BudgetSummary.svelte';
	import QuotaEditor from '$lib/components/iam/QuotaEditor.svelte';
	let { domainId }: { domainId: string } = $props();
	let data = $state<DomainBudgets | null>(null);
	let loading = $state(false);
	let busy = $state(false);
	let error = $state('');
	let outcome = $state('');
	let reloadRequired = $state(false);
	let confirmed = $state<Record<string, boolean>>({});
	let revision = $state(0);
	const authority = $derived(JSON.stringify([$auth.sessionId, $auth.userId, $auth.domainId, $auth.projectId, $auth.isSystemAdmin, $authReady, $projectSwitching, domainId]));
	let verified = $state('');
	function client() {
		const owner = authority; const target = domainId;
		return adminDomainBudgets(target, {
			token: () => $auth.token ?? '', projectId: () => $auth.projectId ?? undefined,
			isCurrent: () => authority === owner && domainId === target && $authReady && !$projectSwitching && $auth.isSystemAdmin === true && !!$auth.token
		});
	}
	function accept(snapshot: DomainBudgets) {
		if (snapshot.domain_id !== domainId || snapshot.enforcement_scope !== 'afterglow_project_allocations') throw new Error(t('scopeMismatch'));
		data = snapshot;
	}
	$effect(() => {
		const owner = authority; const pending = revision;
		let live = true;
		untrack(() => { data = null; loading = true; busy = false; error = ''; verified = ''; confirmed = {}; reloadRequired = false; outcome = ''; });
		if (!untrack(() => $authReady && !$projectSwitching && $auth.isSystemAdmin && !!$auth.token)) { untrack(() => { loading = false; error = t('denied'); }); return; }
		untrack(() => client().load()).then(snapshot => {
			if (live && authority === owner && revision === pending) { accept(snapshot); verified = owner; }
		}).catch(cause => {
			if (live && authority === owner) error = cause instanceof ApiError ? cause.message : t('loadFailed');
		}).finally(() => { if (live && authority === owner) loading = false; });
		return () => { live = false; };
	});
	async function save(values: QuotaMap) {
		if (busy || loading || !data || quotaBlocked(data) || reloadRequired || verified !== authority) return;
		const owner = authority;
		busy = true; error = ''; outcome = '';
		try { const snapshot = await client().save(data.revision, values); if (owner === authority) { accept(snapshot); outcome = t('budgetSaved'); } }
		catch (cause) { if (owner === authority) { error = cause instanceof ApiError ? cause.message : t('loadFailed'); outcome = t('unknownOutcome'); } }
		finally { if (owner === authority) { busy = false; reloadRequired = true; } }
	}
	async function reconcile(operationId: string) {
		if (busy || loading || reloadRequired || !confirmed[operationId] || verified !== authority || !data?.operations.some(row => row.id === operationId && ['applying', 'unknown', 'partial'].includes(row.status))) return;
		const owner = authority;
		busy = true; error = ''; outcome = '';
		try { const snapshot = await client().reconcile(operationId); if (owner === authority) { accept(snapshot); outcome = t('reconciledOutcome'); } }
		catch (cause) { if (owner === authority) { error = cause instanceof ApiError ? cause.message : t('loadFailed'); outcome = t('unknownOutcome'); } }
		finally { if (owner === authority) { busy = false; reloadRequired = true; confirmed = {}; } }
	}
</script>

<PageShell>
	<div class="space-y-4">
		<div class="flex flex-wrap items-center gap-2"><h2 class="mr-auto text-lg font-semibold text-ink-0">{t('domainBudget')}</h2><Button variant="secondary" disabled={loading || busy} onclick={() => revision++}>{t('reload')}</Button></div>
		<Alert tone="info">{t('adminHelp')}</Alert>
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		{#if outcome}<Alert tone="warning">{outcome}</Alert>{/if}
		{#if reloadRequired}<Alert tone="warning">{t('reloadRequired')}</Alert>{/if}
		{#if loading}<ActivityIndicator label={t('loading')} />{/if}
		{#if data && verified === authority}
			<BudgetSummary {data} />
			{#each data.operations.filter(row => ['applying', 'unknown', 'partial'].includes(row.status)) as operation (operation.id)}
				<section class="space-y-3 rounded-lg border border-line p-4">
					<h3 class="text-sm font-semibold text-ink-0 [overflow-wrap:anywhere]">{t('reconcile')} · {operation.id}</h3>
					<p class="text-sm text-ink-2">{t('reconcileHelp')}</p>
					<label class="flex items-start gap-2 text-sm text-ink-1"><input type="checkbox" bind:checked={confirmed[operation.id]} disabled={busy || reloadRequired} />{t('settledConfirm')}</label>
					<Button variant="secondary" disabled={busy || reloadRequired || !confirmed[operation.id]} onclick={() => reconcile(operation.id)}>{t('reconcile')}</Button>
				</section>
			{/each}
			{#if !reloadRequired}{#key `${authority}:${revision}`}<QuotaEditor values={data.ceilings} disabled={busy || loading || quotaBlocked(data)} onSave={save} />{/key}{/if}
		{/if}
	</div>
</PageShell>
