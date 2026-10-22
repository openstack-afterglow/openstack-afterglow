<script lang="ts">
	import { onMount } from 'svelte';
	import { derived, get } from 'svelte/store';
	import { api } from '$lib/api/client';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { invalidateWorkspaceDisplaySnapshots } from '$lib/stores/workspaceController.svelte';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { t } from '$lib/i18n/ns/account';
	import { ActivityIndicator, Alert, Button, Card, Field, TextInput } from '$lib/components/ui';

	interface ProjectDisplayName {
		project_id: string;
		display_name: string;
		native_name: string;
		can_edit: boolean;
	}
	const uid = $props.id();
	let mounted = false;
	let epoch = 0;
	let request: AbortController | null = null;
	let metadata = $state<ProjectDisplayName | null>(null);
	let draft = $state('');
	let busy = $state(false);
	let error = $state('');
	let saved = $state(false);
	const blocked = $derived(!$authReady || $logoutInProgress || $projectSwitching || !metadata?.can_edit || busy);

	function validLabel(value: string): boolean {
		const length = Array.from(value).length;
		return value === value.trim() && length >= 1 && length <= 64 && !/[\p{Cc}\p{Cf}]/u.test(value);
	}
	function readMetadata(value: unknown, project: string): ProjectDisplayName {
		if (!value || typeof value !== 'object') throw new Error('Invalid project metadata');
		const row = value as ProjectDisplayName;
		if (row.project_id !== project || typeof row.display_name !== 'string' || !validLabel(row.display_name)
			|| typeof row.native_name !== 'string' || !row.native_name.trim() || typeof row.can_edit !== 'boolean') {
			throw new Error('Invalid project metadata');
		}
		return row;
	}
	function capture() {
		const state = get(auth), ticket = epoch;
		if (!mounted || !state.token || !state.userId || !state.identityDomainId || !state.domainId || !state.projectId
			|| !get(authReady) || get(logoutInProgress) || get(projectSwitching)) return null;
		request?.abort();
		const controller = new AbortController(); request = controller;
		return {
			token: state.token, project: state.projectId, signal: controller.signal,
			current: () => mounted && epoch === ticket && !controller.signal.aborted && get(authReady)
				&& !get(logoutInProgress) && !get(projectSwitching)
		};
	}
	async function load() {
		if (busy) return;
		const owner = capture(); if (!owner) return;
		busy = true; metadata = null; draft = ''; error = ''; saved = false;
		try {
			const result = await api.get<unknown>(`/api/v1/projects/${encodeURIComponent(owner.project)}/display-name`, owner.token, owner.project,
				{ refresh: true, cache: 'no-store', replayOnUnauthorized: false, signal: owner.signal });
			if (!owner.current()) return;
			metadata = readMetadata(result, owner.project); draft = metadata.display_name;
		} catch {
			if (owner.current()) error = t('personalLabel.loadFailed');
		} finally { if (owner.current()) busy = false; }
	}
	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (blocked || !metadata) return;
		const label = draft.trim();
		if (/[\p{Cc}\p{Cf}]/u.test(draft) || !validLabel(label)) { error = t('personalLabel.invalid'); saved = false; return; }
		if (label === metadata.display_name) return;
		const owner = capture(); if (!owner) return;
		const originalNativeName = metadata.native_name;
		const path = `/api/v1/projects/${encodeURIComponent(owner.project)}/display-name`;
		busy = true; error = ''; saved = false;
		try {
			const result = await api.put<unknown>(path, { display_name: label }, owner.token, owner.project,
				{ cache: 'no-store', replayOnUnauthorized: false, signal: owner.signal });
			if (!owner.current()) return;
			const written = readMetadata(result, owner.project);
			if (!written.can_edit || written.native_name !== originalNativeName || written.display_name !== label) throw new Error('Unconfirmed write');
			const resultReadback = await api.get<unknown>(path, owner.token, owner.project,
				{ refresh: true, cache: 'no-store', replayOnUnauthorized: false, signal: owner.signal });
			if (!owner.current()) return;
			const confirmed = readMetadata(resultReadback, owner.project);
			if (!confirmed.can_edit || confirmed.native_name !== originalNativeName || confirmed.display_name !== label) throw new Error('Unconfirmed readback');
			// Display-only publication preserves credentials, native identity and every authority field.
			auth.update(state => owner.current() ? {
				...state, projectName: confirmed.display_name,
				availableProjects: state.availableProjects.map(row => row.id === owner.project ? { ...row, name: confirmed.display_name } : row)
			} : state);
			if (!owner.current()) return;
			invalidateWorkspaceDisplaySnapshots();
			metadata = confirmed; draft = confirmed.display_name; saved = true;
		} catch {
			if (owner.current()) { metadata = null; draft = ''; error = t('personalLabel.saveFailed'); }
		} finally { if (owner.current()) busy = false; }
	}
	onMount(() => {
		mounted = true; let previous = '';
		const unsubscribe = derived([auth, authReady, logoutInProgress, projectSwitching], ([state, ready, loggingOut, switching]) =>
			JSON.stringify([sessionScopeKey(state), state.token, ready, loggingOut, switching, state.isSystemAdmin, state.isDomainManager,
				state.canWrite, state.canCreateDomain, [...state.roles].sort(), (state.availableDomains ?? []).map(row => [row.id, row.kind]).sort()])
		).subscribe(next => {
			if (next === previous) return;
			previous = next; epoch++; request?.abort(); metadata = null; draft = ''; busy = false; error = ''; saved = false;
			void load();
		});
		return () => { mounted = false; epoch++; request?.abort(); unsubscribe(); };
	});
</script>

{#if $auth.projectId}
	<Card class="p-5 space-y-4 min-w-0">
		<h3 class="text-sm font-semibold text-ink-0">{t('personalLabel.title')}</h3>
		<p class="text-sm text-ink-2">{t('personalLabel.help')}</p>
		{#if busy}<ActivityIndicator label={t('personalLabel.loading')} />{/if}
		{#if error}
			<Alert tone="danger">{error}</Alert>
			{#if !metadata}<Button variant="secondary" disabled={busy || !$authReady || $logoutInProgress || $projectSwitching} onclick={load}>{t('personalLabel.reload')}</Button>{/if}
		{/if}
		{#if saved}<Alert tone="success">{t('personalLabel.saved')}</Alert>{/if}
		{#if metadata?.can_edit}
			<form class="space-y-4" onsubmit={save}>
				<Field label={t('personalLabel.name')} for={`${uid}-name`} help={t('personalLabel.nameHelp')}>
					<TextInput id={`${uid}-name`} bind:value={draft} disabled={blocked} required autocomplete="off" />
				</Field>
				<Button type="submit" variant="primary" disabled={blocked || draft.trim() === metadata.display_name} ariaBusy={busy}>{t('personalLabel.save')}</Button>
			</form>
		{:else if metadata}
			<p class="text-sm text-ink-0 [overflow-wrap:anywhere]">{metadata.display_name}</p>
			<p class="text-sm text-ink-2">{t('personalLabel.readOnly')}</p>
		{/if}
		{#if metadata}
			<details class="text-xs text-ink-2">
				<summary>{t('personalLabel.nativeName')}</summary>
				<p class="mt-2 font-mono [overflow-wrap:anywhere]">{metadata.native_name}</p>
			</details>
		{/if}
	</Card>
{/if}
