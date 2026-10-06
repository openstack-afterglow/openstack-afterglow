<script lang="ts">
	import { untrack } from 'svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import TextareaInput from '$lib/components/ui/TextareaInput.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import type { ManagedRole, RoleMetadata } from './types';
	let { role, busy, disabled, error, onClose, onSave }: {
		role: ManagedRole | null; busy: boolean; disabled: boolean; error: string;
		onClose: () => void; onSave: (metadata: RoleMetadata) => void;
	} = $props();
	let name = $state(untrack(() => role?.name ?? ''));
	let description = $state(untrack(() => role?.description ?? ''));
	let domain = $state('');
	const id = $props.id();
	function submit() {
		if (busy || disabled || !name.trim()) return;
		onSave({ name: name.trim(), description, ...(!role ? { domain_id: domain.trim() || null } : {}) });
	}
</script>

<FormModal open={true} title={role ? t('roleMetadata.editTitle') : t('rolePage.create')} {onClose} submitting={busy}>
	<form id={`${id}-form`} onsubmit={(event) => { event.preventDefault(); submit(); }} class="space-y-4">
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		<Field label={t('form.name')} for={`${id}-name`} required help={role?.protected ? t('roleMetadata.protectedName') : undefined}>
			<TextInput id={`${id}-name`} bind:value={name} required disabled={busy || role?.protected} />
		</Field>
		<Field label={t('form.description')} for={`${id}-description`}>
			<TextareaInput id={`${id}-description`} bind:value={description} disabled={busy} />
		</Field>
		{#if !role}
			<Field label={t('roleMetadata.domainId')} for={`${id}-domain`} help={t('roleMetadata.domainHelp')}>
				<TextInput id={`${id}-domain`} bind:value={domain} disabled={busy} />
			</Field>
		{/if}
	</form>
	{#snippet actions()}
		<Button variant="secondary" disabled={busy} onclick={onClose}>{t('rolePage.delete.cancel')}</Button>
		<Button variant="primary" disabled={busy || disabled || !name.trim()} ariaBusy={busy} onclick={submit}>{role ? t('actions.save') : t('roleMetadata.create')}</Button>
	{/snippet}
</FormModal>
