<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { ApiError } from '$lib/api/client';
	import { domainIam, type IamSession } from '$lib/api/domainIam';
	import type { Project } from '$lib/types/project';
	import { t } from '$lib/i18n/ns/domain-iam';
	import { iamErrorMessage } from './iamError';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import TextareaInput from '$lib/components/ui/TextareaInput.svelte';
	import ProjectLifecycleSection from '$lib/components/account/ProjectLifecycleSection.svelte';

	let { session, project, blocked = false, onDenied, onSaved }: {
		session: IamSession; project: Project; blocked?: boolean; onDenied: () => void; onSaved: () => void;
	} = $props();
	const client = untrack(() => domainIam(session));
	const uid = $props.id();
	let live = true;
	let name = $state(untrack(() => project.name));
	let description = $state(untrack(() => project.description ?? ''));
	let busy = $state(false);
	let error = $state('');
	let notice = $state('');
	let form = $state<HTMLFormElement>();
	const dirty = $derived(name.trim() !== project.name || description.trim() !== (project.description ?? '').trim());

	async function save() {
		if (!live || !session.canSubmit() || blocked || busy || !dirty || !form?.reportValidity()) return;
		busy = true; error = ''; notice = '';
		try {
			await client.updateProject(project.id, { name: name.trim(), description: description.trim() });
			if (live) { notice = t('projectUpdated'); onSaved(); }
		} catch (cause) {
			if (!live || !session.isCurrent()) return;
			error = iamErrorMessage(cause, t('saveFailed'));
			if (cause instanceof ApiError && cause.status === 403) onDenied();
		} finally { if (live) busy = false; }
	}
	onDestroy(() => { live = false; });
</script>

<div class="space-y-4">
	<form bind:this={form} class="space-y-4" onsubmit={(event) => { event.preventDefault(); void save(); }}>
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		{#if notice}<Alert tone="success">{notice}</Alert>{/if}
		<Field label={t('name')} for={`${uid}-name`} required><TextInput id={`${uid}-name`} bind:value={name} required maxlength={64} disabled={busy || blocked} autocomplete="off" /></Field>
		<Field label={t('description')} for={`${uid}-description`}><TextareaInput id={`${uid}-description`} bind:value={description} disabled={busy || blocked} rows={3} /></Field>
		<div class="flex justify-end gap-2">
			<Button variant="primary" disabled={blocked || busy || !dirty || !session.canSubmit()} ariaBusy={busy} onclick={save}>{t('save')}</Button>
		</div>
	</form>
	<ProjectLifecycleSection {session} {project} {blocked} showDelete={false} {onDenied} onChanged={onSaved} onDeleted={onSaved} />
</div>
