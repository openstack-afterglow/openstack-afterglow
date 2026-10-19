<script lang="ts">
	import { onMount, onDestroy, untrack } from 'svelte';
	import { ApiError } from '$lib/api/client';
	import type { IamSession } from '$lib/api/domainIam';
	import { workspaceIam, quotaBlocked, quotaFields, nativeQuotaKey, type DomainBudgets, type ProjectQuotas, type QuotaMap, type QuotaSection } from '$lib/api/workspaceIam';
	import { t } from '$lib/i18n/ns/workspace-iam';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import QuotaEditor from './QuotaEditor.svelte';
	import BudgetSummary from './BudgetSummary.svelte';
	let { session, blocked = false, onDenied }: { session: IamSession; blocked?: boolean; onDenied: () => void } = $props();
	const client = untrack(() => workspaceIam(session));
	let live = true;
	let generation = 0;
	let data = $state<DomainBudgets | null>(null);
	let native = $state<ProjectQuotas | null>(null);
	let loading = $state(true);
	let busy = $state(false);
	let error = $state('');
	let outcome = $state('');
	let reloadRequired = $state(false);
	let editor = $state<'defaults' | 'project'>('defaults');
	let project = $state('');
	let editorRevision = $state(0);
	function fail(cause: unknown) {
		if (!live || !session.isCurrent()) return;
		error = cause instanceof ApiError ? cause.message : t('loadFailed');
		if (cause instanceof ApiError && cause.status === 403) onDenied();
	}
	function accept(snapshot: DomainBudgets) {
		if (snapshot.domain_id !== session.domainId || snapshot.enforcement_scope !== 'afterglow_project_allocations') throw new Error(t('scopeMismatch'));
		data = snapshot;
		if (!snapshot.projects.some(row => row.id === project)) project = snapshot.projects[0]?.id ?? '';
	}
	async function load() {
		if (busy || blocked || !session.isCurrent()) return;
		const pending = ++generation;
		loading = true; error = ''; native = null; data = null;
		try {
			const snapshot = await client.budgets();
			if (!live || pending !== generation) return;
			accept(snapshot); reloadRequired = false; editorRevision++;
			if (editor === 'project') await loadProject();
		} catch (cause) { if (pending === generation) fail(cause); }
		finally { if (live && pending === generation) loading = false; }
	}
	async function loadProject() {
		const target = project; const pending = ++generation;
		native = null; loading = true; error = '';
		try {
			if (target) {
				const result = await client.project(target);
				if (!live || pending !== generation) return;
				if (result.project_id !== target) throw new Error(t('scopeMismatch'));
				native = result;
			}
			editorRevision++;
		} catch (cause) { if (pending === generation) fail(cause); }
		finally { if (live && pending === generation) loading = false; }
	}
	function projectValues(): QuotaMap {
		const values: QuotaMap = {};
		for (const [section, fields] of Object.entries(quotaFields)) for (const field of fields) {
			const entry = native?.[section as QuotaSection]?.[nativeQuotaKey(field)];
			if (entry) values[field] = entry.limit;
		}
		return values;
	}
	async function save(values: QuotaMap) {
		if (!live || blocked || busy || loading || !data || quotaBlocked(data) || reloadRequired || !session.isCurrent() || !session.canSubmit()) return;
		const target = project; const mode = editor;
		busy = true; error = ''; outcome = '';
		try {
			if (mode === 'defaults') { accept(await client.defaults(data.revision, values)); outcome = t('defaultsSaved'); }
			else {
				const result = await client.saveProject(target, values);
				if (!live) return;
				if (result.domain_id !== session.domainId || result.project_id !== target) throw new Error(t('scopeMismatch'));
				outcome = result.status === 'updated' ? t('projectSaved') : result.status === 'partial' ? t('partialOutcome') : t('unknownOutcome');
			}
		} catch (cause) { fail(cause); outcome = t('unknownOutcome'); }
		finally { if (live) { busy = false; reloadRequired = true; native = null; editorRevision++; } }
	}
	onMount(() => { void load(); });
	onDestroy(() => { live = false; generation++; data = null; native = null; });
</script>

<div class="space-y-4">
	<div class="flex flex-wrap items-center gap-2"><h2 class="mr-auto text-lg font-semibold text-ink-0">{t('quotas')}</h2><Button variant="secondary" disabled={blocked || loading || busy} onclick={load}>{t('reload')}</Button></div>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if outcome}<Alert tone={reloadRequired ? 'warning' : 'info'}>{outcome}</Alert>{/if}
	{#if reloadRequired}<Alert tone="warning">{t('reloadRequired')}</Alert>{/if}
	{#if loading}<ActivityIndicator label={t('loading')} />{/if}
	{#if data}
		<BudgetSummary {data} />
		<div class="flex flex-wrap gap-2"><Button variant={editor === 'defaults' ? 'secondary' : 'ghost'} disabled={busy || loading || blocked || reloadRequired} onclick={() => { editor = 'defaults'; native = null; editorRevision++; }}>{t('editDefaults')}</Button><Button variant={editor === 'project' ? 'secondary' : 'ghost'} disabled={busy || loading || blocked || reloadRequired} onclick={() => { editor = 'project'; void loadProject(); }}>{t('editProject')}</Button></div>
		{#if editor === 'defaults'}<p class="text-sm text-ink-2">{t('defaultsHelp')}</p>
		{:else}<SelectInput bind:value={project} ariaLabel={t('project')} disabled={busy || loading || blocked || reloadRequired} onchange={() => void loadProject()}><option value="">{t('chooseProject')}</option>{#each data.projects as row (row.id)}<option value={row.id}>{row.name || row.id} · {row.id}{row.enabled ? '' : ` · ${t('disabled')}`}</option>{/each}</SelectInput>{/if}
		{#if !reloadRequired && (editor === 'defaults' || native)}
			{#key `${editor}:${project}:${editorRevision}`}<QuotaEditor values={editor === 'defaults' ? data.defaults : projectValues()} {native} projectMode={editor === 'project'} disabled={blocked || busy || loading || quotaBlocked(data)} onSave={save} />{/key}
		{/if}
	{/if}
</div>
