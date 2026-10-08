<script lang="ts">
	import { untrack } from 'svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { t as tc } from '$lib/i18n/ns/common';
	import RichText from '$lib/i18n/RichText.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import TextareaInput from '$lib/components/ui/TextareaInput.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import type { ManagedRole, RoleMetadata } from './types';
	import { isNativeRole, managedRoleName, normalizeRolePart, splitManagedRole, validRolePart } from './naming';
	let { role, busy, disabled, error, onClose, onSave }: {
		role: ManagedRole | null; busy: boolean; disabled: boolean; error: string;
		onClose: () => void; onSave: (metadata: RoleMetadata) => void;
	} = $props();
	const original = untrack(() => role ? splitManagedRole(role.name) : null);
	let area = $state(original?.area ?? '');
	let grade = $state(original?.grade ?? '');
	const protectedName = $derived(!!role && (role.protected || isNativeRole(role.name)));
	const renaming = $derived(!role || area !== (original?.area ?? '') || grade !== (original?.grade ?? ''));
	const preview = $derived(managedRoleName(area, grade));
	const valid = $derived(protectedName || !renaming || (validRolePart(normalizeRolePart(area)) && validRolePart(normalizeRolePart(grade))));
	function submit() {
		if (busy || disabled || !valid) return;
		onSave({ ...(!protectedName && renaming ? { name: preview } : {}), description, ...(!role ? { domain_id: domain.trim() || null } : {}) });
	}
	let description = $state(untrack(() => role?.description ?? ''));
	let domain = $state('');
	const id = $props.id();
</script>

{#snippet roleName(text: string)}<code class="[overflow-wrap:anywhere]">{text}</code>{/snippet}

<FormModal open={true} title={role ? t('roleMetadata.edit') : t('rolePage.create')} {onClose} submitting={busy}>
	<form id={`${id}-form`} onsubmit={(event) => { event.preventDefault(); submit(); }} class="space-y-4">
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		{#if role}<p class="text-sm text-ink-1 [overflow-wrap:anywhere]"><RichText segments={t.rich('roleMetadata.currentName', { name: role.name })} tags={{ name: roleName }} /></p>{/if}
		{#if protectedName}
			<p class="text-sm text-ink-2">{t('roleMetadata.protectedNameHelp')}</p>
		{:else}
			<Field label={t('roleMetadata.area')} for={`${id}-area`} required={!role}>
				<TextInput id={`${id}-area`} bind:value={area} disabled={busy} />
			</Field>
			<Field label={t('roleMetadata.grade')} for={`${id}-grade`} required={!role} help={t('roleMetadata.gradeHelp')}>
				<TextInput id={`${id}-grade`} bind:value={grade} disabled={busy} />
			</Field>
			<p class="text-sm text-ink-2" aria-live="polite"><RichText segments={t.rich('roleMetadata.namePreview', { name: renaming ? preview : role?.name ?? '' })} tags={{ name: roleName }} /></p>
			{#if !valid}<Alert tone="warning">{t('roleMetadata.invalidName')}</Alert>{/if}
		{/if}
		<Field label={t('form.description')} for={`${id}-description`}>
			<TextareaInput id={`${id}-description`} bind:value={description} disabled={busy} />
		</Field>
		{#if !role}
			<Field label={t('roleMetadata.domain')} for={`${id}-domain`} help={t('roleMetadata.domainHelp')}>
				<TextInput id={`${id}-domain`} bind:value={domain} disabled={busy} />
			</Field>
		{/if}
	</form>
	{#snippet actions()}
		<Button variant="secondary" disabled={busy} onclick={onClose}>{tc('actions.cancel')}</Button>
		<Button variant="primary" disabled={busy || disabled || !valid} ariaBusy={busy} onclick={submit}>{role ? t('actions.save') : t('roleMetadata.create')}</Button>
	{/snippet}
</FormModal>
