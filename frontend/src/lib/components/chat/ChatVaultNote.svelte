<script lang="ts">
	import { onDestroy, tick, untrack } from 'svelte';
	import { isAppendOnly, isVaultError, vaultApi, vaultContentLimit, vaultPageSize, type VaultNote, type VaultRevision, type VaultSelection } from '$lib/api/chatVault';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t } from '$lib/i18n/ns/chat-settings';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import TextareaInput from '$lib/components/ui/TextareaInput.svelte';

	interface Props {
		token: string;
		projectId: string;
		canRead: boolean;
		canWrite: boolean;
		isCurrent: () => boolean;
		selection: VaultSelection;
		onClose: () => void;
		onSaved: () => void;
	}
	let { token, projectId, canRead, canWrite, isCurrent, selection, onClose, onSaved }: Props = $props();
	const uid = $props.id();
	const lifetime = new AbortController();
	const current = () => !lifetime.signal.aborted && isCurrent();
	const client = () => vaultApi(token, projectId, lifetime.signal);
	onDestroy(() => lifetime.abort());

	let note = $state.raw<VaultNote | null>(null);
	let heading: HTMLHeadingElement;
	let started = false;
	let loading = $state(true);
	let loadError = $state(false);
	let draft = $state<{ mode: 'append' | 'replace'; title: string; content: string } | null>(null);
	let appendSlug: string | undefined;
	let saving = $state(false);
	let error = $state<'secretRefused' | 'saveFailed' | 'noteExists' | 'mergeLoadFailed' | null>(null);
	let conflict = $state(false);
	let latest = $state.raw<VaultNote | null | undefined>(undefined);
	let reloading = $state(false);
	let historyOpen = $state(false);
	let revisions = $state.raw<VaultRevision[]>([]);
	let historyMore = $state(false);
	let historyLoading = $state(false);
	let historyError = $state(false);
	const title = $derived(note?.title ?? ('slot' in selection ? t(`settings.vault.kinds.${selection.slot}`) : t('settings.vault.notes')));
	const scope = $derived(note?.scope ?? ('slot' in selection && selection.slot !== 'short_term' ? 'global' : 'domain'));

	async function load() {
		if (!canRead || !current()) return;
		loading = true;
		loadError = false;
		try {
			const result = await client().note(selection);
			if (current()) note = result;
		} catch {
			if (current()) loadError = true;
		} finally {
			if (current()) loading = false;
		}
	}

	$effect(() => {
		if (!canRead || started) return;
		started = true;
		untrack(() => {
			heading?.focus();
			void load();
		});
	});

	function edit(mode: 'replace' | 'append') {
		if (!canWrite || !current()) return;
		draft = { mode, title, content: mode === 'append' ? '' : note?.content ?? '' };
		appendSlug = undefined;
		historyOpen = false;
		revisions = [];
		historyMore = false;
		void tick().then(() => {
			if (current()) document.getElementById(`${uid}-content`)?.focus();
		});
	}

	function finishEdit() {
		draft = null;
		conflict = false;
		latest = undefined;
		error = null;
		void tick().then(() => { if (current()) heading?.focus(); });
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (!canWrite || !current() || saving || conflict || !draft?.content.trim() || !draft.title.trim()) return;
		const { mode, title, content } = draft;
		saving = true;
		error = null;
		try {
			if (mode === 'append' && note) {
				await client().create({
					kind: note.kind,
					slug: appendSlug ??= crypto.randomUUID(),
					title: note.title,
					content,
					mode,
					scope: note.scope,
					...(note.project_key ? { project_key: note.project_key } : {}),
					...(note.role ? { role: note.role } : {})
				});
			} else {
				const saved = await client().replace(selection, { content, title: title.trim(), expectedHash: note?.hash });
				if (!current()) return;
				note = saved;
			}
			if (!current()) return;
			finishEdit();
			onSaved();
		} catch (e) {
			if (!current()) return;
			if (mode === 'replace' && (isVaultError(e, 'hash_mismatch') || isVaultError(e, 'note_exists'))) conflict = true;
			else if (isVaultError(e, 'secret_detected')) error = 'secretRefused';
			else if (isVaultError(e, 'note_exists') || isVaultError(e, 'append_only')) error = 'noteExists';
			else error = 'saveFailed';
		} finally {
			if (current()) saving = false;
		}
	}

	async function loadLatest() {
		if (!canRead || !current() || reloading) return;
		reloading = true;
		error = null;
		try {
			const next = await client().note(selection);
			if (current()) latest = next;
		} catch {
			if (current()) error = 'mergeLoadFailed';
		} finally {
			if (current()) reloading = false;
		}
	}

	function resolveConflict(keepDraft: boolean) {
		if (latest === undefined || !current()) return;
		note = latest;
		conflict = false;
		latest = undefined;
		error = null;
		if (!keepDraft) finishEdit();
	}

	async function loadHistory(before?: number) {
		if (!note || historyLoading || !canRead || !current()) return;
		historyLoading = true;
		historyError = false;
		try {
			const page = await client().revisions(note.id, before);
			if (!current() || !historyOpen) return;
			revisions = before === undefined ? page : [...revisions, ...page];
			historyMore = page.length === vaultPageSize;
		} catch {
			if (current() && historyOpen) historyError = true;
		} finally {
			if (current()) historyLoading = false;
		}
	}

	function toggleHistory() {
		historyOpen = !historyOpen;
		if (historyOpen && !revisions.length) void loadHistory();
	}
</script>

<article class="space-y-3">
	<header class="flex flex-wrap items-start justify-between gap-2">
		<div class="min-w-0 space-y-1">
			<h3 id={`${uid}-title`} bind:this={heading} tabindex="-1" class="[overflow-wrap:anywhere] text-sm font-semibold">{title}</h3>
			{#if note || 'slot' in selection}
				<div class="flex flex-wrap items-center gap-2 text-xs text-[var(--color-ink-2)]">
					<Pill size="xs">{t(`settings.vault.scopes.${scope}`)}</Pill>
					{#if note?.project_key}<span class="[overflow-wrap:anywhere]">{note.project_key}</span>{/if}
					{#if note?.role}<span>{t(`settings.vault.roles.${note.role}`)}</span>{/if}
				</div>
			{/if}
		</div>
		<Button variant="ghost" size="sm" onclick={onClose} disabled={saving}>{t('settings.vault.back')}</Button>
	</header>
	{#if loading}
		<LoadingState variant="section" label={t('settings.memory.loading')} />
	{:else if loadError}
		<Alert flat>{t('settings.vault.loadFailed')}</Alert>
		<Button variant="secondary" size="sm" onclick={load}>{t('settings.vault.retry')}</Button>
	{:else}
		{#if note}
			<pre class="whitespace-pre-wrap [overflow-wrap:anywhere] bg-surface-sunken p-3 font-mono text-sm text-[var(--color-ink-1)]">{note.content}</pre>
		{:else}
			<p class="text-sm text-[var(--color-ink-2)]">{t('settings.vault.emptySlot')}</p>
		{/if}

		{#if canWrite}
			{#if draft}
				<form method="post" class="space-y-3" aria-labelledby={`${uid}-title`} onsubmit={save}>
					{#if draft.mode === 'append'}
						<p class="text-sm text-[var(--color-ink-2)]">{t('settings.vault.appendOnly')}</p>
					{:else if 'id' in selection}
						<Field for={`${uid}-name`} label={t('settings.vault.noteTitle')}>
							<TextInput id={`${uid}-name`} bind:value={draft.title} maxlength={200} required disabled={saving} />
						</Field>
					{/if}
					<Field for={`${uid}-content`} label={t(draft.mode === 'append' ? 'settings.vault.appendContent' : 'settings.vault.content')}>
						<TextareaInput id={`${uid}-content`} bind:value={draft.content} rows={6} maxlength={vaultContentLimit} required disabled={saving} />
					</Field>
					{#if error}<Alert flat>{t(`settings.vault.${error}`)}</Alert>{/if}
					{#if conflict}
						<Alert tone="warning" flat>{t('settings.vault.conflict')}</Alert>
						{#if latest === undefined}
							<Button variant="secondary" size="sm" onclick={loadLatest} disabled={reloading}>
								{reloading ? t('settings.memory.loading') : t('settings.vault.loadLatest')}
							</Button>
						{:else}
							<h4 class="text-sm font-semibold">{t('settings.vault.latestVersion')}</h4>
							{#if latest}
								<p class="text-sm [overflow-wrap:anywhere]">{latest.title}</p>
								<pre class="whitespace-pre-wrap [overflow-wrap:anywhere] bg-surface-sunken p-3 font-mono text-sm">{latest.content}</pre>
							{:else}
								<p class="text-sm text-[var(--color-ink-2)]">{t('settings.vault.emptySlot')}</p>
							{/if}
							<div class="flex flex-wrap gap-2">
								<Button variant="secondary" size="sm" onclick={() => resolveConflict(false)}>{t('settings.vault.useLatest')}</Button>
								<Button variant="secondary" size="sm" onclick={() => resolveConflict(true)}>{t('settings.vault.keepDraft')}</Button>
							</div>
						{/if}
					{/if}
					<div class="flex flex-wrap gap-2">
						<Button variant="secondary" size="sm" onclick={finishEdit} disabled={saving || reloading}>{t('settings.memory.cancel')}</Button>
						<Button size="sm" type="submit" disabled={saving || conflict || !draft.content.trim() || !draft.title.trim()} ariaBusy={saving}>
							{saving ? t('settings.memory.saving') : draft.mode === 'append' ? t('settings.vault.append') : t('settings.memory.saveChanges')}
						</Button>
					</div>
				</form>
			{:else if note && isAppendOnly(note.kind)}
				<Button size="sm" onclick={() => edit('append')}>{t('settings.vault.append')}</Button>
			{:else}
				<Button size="sm" onclick={() => edit('replace')}>{t('settings.memory.edit')}</Button>
			{/if}
		{/if}

		{#if note && !draft}
			<div class="space-y-2 border-t border-[var(--color-line)] pt-2">
				<Button variant="secondary" size="sm" ariaExpanded={historyOpen} onclick={toggleHistory}>{t('settings.vault.revisions')}</Button>
				{#if historyOpen}
					{#if historyError}
						<Alert flat>{t('settings.vault.revisionsFailed')}</Alert>
						<Button variant="secondary" size="sm" onclick={() => loadHistory()}>{t('settings.vault.retry')}</Button>
					{:else if historyLoading && revisions.length === 0}
						<LoadingState variant="inline" label={t('settings.memory.loading')} />
					{:else if revisions.length === 0}
						<p class="text-sm text-[var(--color-ink-2)]">{t('settings.vault.noRevisions')}</p>
					{/if}
					{#each revisions as revision (revision.revision)}
						<details class="border-b border-[var(--color-line)] py-2">
							<summary class="cursor-pointer text-sm">
								{t('settings.vault.revision', { number: revision.revision })}
								<time datetime={revision.created_at} class="ms-2 text-xs text-[var(--color-ink-2)]">{new Date(revision.created_at).toLocaleString(intlLocale())}</time>
							</summary>
							<h4 class="mt-2 text-sm font-semibold [overflow-wrap:anywhere]">{revision.title}</h4>
							<pre class="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere] bg-surface-sunken p-3 font-mono text-sm">{revision.content}</pre>
						</details>
					{/each}
					{#if historyMore && !historyError}
						<Button variant="secondary" size="sm" onclick={() => loadHistory(revisions.at(-1)?.revision)} disabled={historyLoading}>{t('settings.vault.more')}</Button>
					{/if}
				{/if}
			</div>
		{/if}
	{/if}
</article>
