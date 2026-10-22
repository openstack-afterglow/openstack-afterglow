<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api/client';
	import { t } from '$lib/i18n/ns/admin-system';
	import { t as tq } from '$lib/i18n/ns/workspace-iam';
	import { Alert, Button, Field, SelectInput, ActivityIndicator } from '$lib/components/ui';
	import type { QuotaField } from '$lib/api/workspaceIam';
	let { token, projectId, current }: { token: string; projectId?: string; current: () => boolean } = $props();
	interface Project { id: string; name: string; user_id: string | null; enabled: boolean }
	interface Preview { project_id: string; owner_user_id: string; policy_revision: number; preview_id: string; limits: Record<string, number>; current: Record<string, { limit: number; in_use: number; reserved: number }>; can_apply: boolean; blocked_fields: string[] }
	let items = $state<Project[]>([]), selected = $state('');
	let cursor = $state<string | null>(null), next = $state<string | null>(null), history = $state<Array<string | null>>([]);
	let preview = $state<Preview | null>(null), confirmed = $state(false), busy = $state(false), loaded = $state(false);
	let error = $state(''), result = $state<{ status: string; operation_id: string; errors: Record<string, string> } | null>(null);
	let live = true, generation = 0;
	const path = '/api/v1/admin/personal-project-quotas';
	const options = { cache: 'no-store', replayOnUnauthorized: false } as const;
	onMount(() => () => { live = false; generation++; });
	function clearPreview() { generation++; preview = null; confirmed = false; error = ''; result = null; }
	async function load(nextCursor: string | null = null, nextHistory: Array<string | null> = []) {
		if (busy || !current()) return; clearPreview(); const ticket = generation; busy = true; loaded = false; items = []; selected = '';
		try {
			const page = await api.get<{ items: Project[]; next_cursor: string | null }>(`${path}${nextCursor ? `?cursor=${encodeURIComponent(nextCursor)}` : ''}`, token, projectId, { ...options, refresh: true });
			if (!live || ticket !== generation || !current()) return;
			items = page.items; next = page.next_cursor; cursor = nextCursor; history = nextHistory; loaded = true;
		} catch { if (live && ticket === generation && current()) error = t('enrollment.convergeFailed'); }
		finally { if (live && ticket === generation && current()) busy = false; }
	}
	async function inspect() {
		if (busy || !selected || !current()) return; clearPreview(); const ticket = generation; busy = true;
		try {
			const value = await api.get<Preview>(`${path}/${encodeURIComponent(selected)}/preview`, token, projectId, { ...options, refresh: true });
			if (live && ticket === generation && current()) preview = value;
		} catch { if (live && ticket === generation && current()) error = t('enrollment.convergeFailed'); }
		finally { if (live && ticket === generation && current()) busy = false; }
	}
	async function apply() {
		if (busy || !current() || !preview?.can_apply || !confirmed || selected !== preview.project_id) return;
		const ticket = generation, proof = preview; busy = true; error = ''; preview = null; confirmed = false;
		try {
			const value = await api.post<{ status: string; operation_id: string; errors: Record<string, string> }>(`${path}/${encodeURIComponent(selected)}/apply`, { preview_id: proof.preview_id }, token, projectId, options);
			if (live && ticket === generation && current()) result = value;
		} catch { if (live && ticket === generation && current()) error = t('enrollment.convergeFailed'); }
		finally { if (live && ticket === generation && current()) busy = false; }
	}
</script>

<section class="space-y-4" aria-label={t('enrollment.convergeTitle')}>
	<h3 class="text-sm font-semibold">{t('enrollment.convergeTitle')}</h3>
	<p class="text-sm text-ink-2">{t('enrollment.convergeHelp')}</p>
	<Button variant="secondary" disabled={busy} onclick={() => load()}>{t('enrollment.convergeLoad')}</Button>
	{#if busy}<ActivityIndicator label={t('enrollment.loading')} />{/if}
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if loaded}
		<Field label={t('enrollment.convergeProject')} for="personal-quota-project"><SelectInput id="personal-quota-project" bind:value={selected} disabled={busy} onchange={clearPreview}>
			<option value="">{t('enrollment.convergeSelect')}</option>
			{#each items as project (project.id)}<option value={project.id}>{project.name} · {project.id} · {project.user_id ?? '—'}</option>{/each}
		</SelectInput></Field>
		<div class="flex flex-wrap gap-2">
			<Button variant="secondary" disabled={busy || !selected} onclick={inspect}>{t('enrollment.convergePreview')}</Button>
			<Button variant="subtle" disabled={busy || history.length === 0} onclick={() => load(history[history.length - 1], history.slice(0, -1))}>{t('enrollment.previous')}</Button>
			<Button variant="subtle" disabled={busy || !next} onclick={() => load(next, [...history, cursor])}>{t('enrollment.next')}</Button>
		</div>
	{/if}
	{#if preview}
		<p class="text-xs text-ink-2 break-all">{t('enrollment.convergeOwner')}: <code>{preview.owner_user_id}</code> · {t('enrollment.convergeRevision')}: {preview.policy_revision}</p>
		<ul class="space-y-2 text-sm">
			{#each Object.entries(preview.limits) as [key, limit] (key)}<li class="flex flex-wrap justify-between gap-2"><span>{tq(`field.${key as QuotaField}`)}</span><span class="tabular-nums">{preview.current[key].limit} → {limit} · {t('enrollment.convergeUsage')}: {preview.current[key].in_use} + {preview.current[key].reserved}</span></li>{/each}
		</ul>
		{#if !preview.can_apply}<Alert tone="warning">{t('enrollment.convergeBlocked')} {preview.blocked_fields.join(', ')}</Alert>{/if}
		<label class="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" bind:checked={confirmed} disabled={busy || !preview.can_apply} />{t('enrollment.convergeConfirm')}</label>
		<Button variant="primary" disabled={busy || !preview.can_apply || !confirmed} onclick={apply}>{t('enrollment.convergeApply')}</Button>
	{/if}
	{#if result}<Alert tone={result.status === 'updated' ? 'success' : 'warning'}>{t(result.status === 'updated' ? 'enrollment.convergeDone' : 'enrollment.convergeUnknown')} <code class="break-all">{result.operation_id}</code>{#each Object.entries(result.errors) as [section, code]}<p>{section}: {code}</p>{/each}</Alert>{/if}
</section>
