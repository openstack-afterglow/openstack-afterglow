<script lang="ts">
	import { onDestroy, tick, untrack } from 'svelte';
	import { isVaultSlot, vaultApi, vaultKinds, vaultPageSize, type VaultKind, type VaultNote, type VaultSelection } from '$lib/api/chatVault';
	import { t } from '$lib/i18n/ns/chat-settings';
	import { toast } from '$lib/stores/toast';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import ChatVaultCreate from './ChatVaultCreate.svelte';
	import ChatVaultDocument from './ChatVaultDocument.svelte';
	import ChatVaultNote from './ChatVaultNote.svelte';

	interface Props {
		token: string;
		projectId: string;
		canRead: boolean;
		canWrite: boolean;
		isCurrent: () => boolean;
	}
	let { token, projectId, canRead, canWrite, isCurrent }: Props = $props();
	const uid = $props.id();
	let notes = $state.raw<VaultNote[]>([]);
	let refreshNeeded = $state(true);
	let kind = $state<VaultKind | ''>('');
	let searchText = $state('');
	let query = $state('');
	let loading = $state(true);
	let listError = $state(false);
	let more = $state(false);
	let createKind = $state<VaultKind | null>(null);
	let selected = $state.raw<VaultSelection | null>(null);
	let trigger: HTMLButtonElement | undefined;
	let heading: HTMLHeadingElement;
	let docRevision = $state(0);
	let noteRequest: AbortController | undefined;
	const valid = () => isCurrent() && canRead;
	onDestroy(() => noteRequest?.abort());

	async function loadNotes(before?: number) {
		if (!valid()) return;
		noteRequest?.abort();
		const request = new AbortController();
		noteRequest = request;
		loading = true;
		listError = false;
		const current = () => isCurrent() && !request.signal.aborted;
		try {
			const page = await vaultApi(token, projectId, request.signal).list(kind, query, before);
			if (!current()) return;
			notes = before === undefined ? page : [...notes, ...page];
			more = page.length === vaultPageSize;
		} catch {
			if (current()) listError = true;
		} finally {
			if (current()) loading = false;
		}
	}

	$effect(() => {
		if (!canRead || !refreshNeeded) return;
		refreshNeeded = false;
		void untrack(() => loadNotes());
	});

	function filter(event: Event) {
		kind = (event.currentTarget as HTMLSelectElement).value as VaultKind | '';
		notes = [];
		void loadNotes();
	}

	function search(event: SubmitEvent) {
		event.preventDefault();
		query = searchText.trim();
		notes = [];
		void loadNotes();
	}

	function openNote(selection: VaultSelection, target?: HTMLButtonElement) {
		if (!valid()) return;
		trigger = target;
		selected = selection;
	}

	async function closeNote() {
		selected = null;
		await tick();
		if (trigger?.isConnected) trigger.focus();
		else heading?.focus();
	}

	function saved() {
		if (!isCurrent()) return;
		docRevision++;
		refreshNeeded = true;
		toast.success(t('settings.vault.saved'));
	}

	function created(note: VaultNote) {
		createKind = null;
		saved();
		trigger = undefined;
		selected = { id: note.id };
	}
</script>

<div hidden={!canRead} inert={!canRead} class="space-y-5">
	{#key docRevision}
		<ChatVaultDocument {token} {projectId} {canRead} {isCurrent} />
	{/key}

	<section class="space-y-3">
		<div hidden={selected !== null}>
			<header class="flex flex-wrap items-center justify-between gap-2">
				<h3 bind:this={heading} tabindex="-1" class="text-sm font-semibold">{t('settings.vault.notes')}</h3>
				{#if canWrite}
					<Button size="sm" onclick={() => (createKind = kind && !isVaultSlot(kind) ? kind : 'user_note')}>
						{t('settings.vault.create')}
					</Button>
				{/if}
			</header>
			<search aria-label={t('settings.vault.notes')} class="mt-3">
				<form method="get" class="flex flex-wrap items-end gap-2" onsubmit={search}>
					<div class="min-w-0 basis-40 grow">
						<Field for={`${uid}-filter`} label={t('settings.vault.kind')}>
							<SelectInput id={`${uid}-filter`} value={kind} onchange={filter}>
								<option value="">{t('settings.vault.allKinds')}</option>
								{#each vaultKinds as option (option)}
									<option value={option}>{t(`settings.vault.kinds.${option}`)}</option>
								{/each}
							</SelectInput>
						</Field>
					</div>
					<div class="min-w-0 basis-48 grow">
						<Field for={`${uid}-search`} label={t('settings.vault.search')}>
							<TextInput id={`${uid}-search`} type="search" bind:value={searchText} maxlength={200} />
						</Field>
					</div>
					<Button type="submit" variant="secondary">{t('settings.vault.search')}</Button>
				</form>
			</search>
			{#if isVaultSlot(kind) && !query}
				{@const slot = kind}
				<div class="mt-3">
					<Button variant="secondary" size="sm" onclick={(event) => openNote({ slot }, event.currentTarget as HTMLButtonElement)}>
						{t('settings.vault.openSlot', { name: t(`settings.vault.kinds.${slot}`) })}
					</Button>
				</div>
			{/if}
			<div class="mt-3 space-y-2" aria-busy={loading}>
				{#if listError}
					<Alert flat>{t('settings.vault.loadFailed')}</Alert>
					<Button variant="secondary" size="sm" onclick={() => loadNotes()}>{t('settings.vault.retry')}</Button>
				{:else if loading && !notes.length}
					<LoadingState variant="section" label={t('settings.memory.loading')} />
				{:else}
					{#if notes.length === 0}
						<p class="text-sm text-[var(--color-ink-2)]" role="status">{t(query || kind ? 'settings.vault.noResults' : 'settings.vault.empty')}</p>
					{:else}
						<ul class="divide-y divide-[var(--color-line)]">
							{#each notes as note (note.id)}
								<li class="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2">
									<Button variant="ghost" class="min-w-0 max-w-full text-left" onclick={(event) => openNote({ id: note.id }, event.currentTarget as HTMLButtonElement)}>
										<span class="whitespace-normal break-all">{note.title}</span>
									</Button>
									<div class="flex flex-wrap items-center gap-2 text-xs text-[var(--color-ink-2)]">
										<span>{t(`settings.vault.kinds.${note.kind}`)}</span>
										<Pill size="xs">{t(`settings.vault.scopes.${note.scope}`)}</Pill>
									</div>
								</li>
							{/each}
						</ul>
					{/if}
					{#if more && notes.length}
						<Button variant="secondary" size="sm" disabled={loading} onclick={() => loadNotes(notes.at(-1)?.id)}>
							{loading ? t('settings.memory.loading') : t('settings.vault.more')}
						</Button>
					{/if}
				{/if}
			</div>
		</div>

		{#if selected}
			<ChatVaultNote {token} {projectId} {canRead} {canWrite} {isCurrent} selection={selected} onClose={closeNote} onSaved={saved} />
		{/if}
	</section>
</div>

{#if createKind !== null}
	<ChatVaultCreate {token} {projectId} {canWrite} {isCurrent} initialKind={createKind} onClose={() => (createKind = null)} onCreated={created} />
{/if}
