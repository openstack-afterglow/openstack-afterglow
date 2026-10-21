<script lang="ts">
	import { onDestroy } from 'svelte';
	import { Alert, Button, Field, FormModal, TextInput } from '$lib/components/ui';
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import { t } from '$lib/i18n/ns/instance';

	const s = useInstanceDetailController();
	const componentId = $props.id();
	onDestroy(() => s.closeRename());
</script>

<FormModal open={true} title={t('rename.title')} onClose={s.closeRename} submitting={s.renameLoading}>
	<p class="mb-4 text-sm text-ink-2">{t('rename.notice')}</p>
	<Field label={t('rename.name')} for={`${componentId}-name`} help={t('rename.invalidName')} required>
		<TextInput
			id={`${componentId}-name`}
			ariaLabel={t('rename.name')}
			bind:value={s.renameDraft}
			maxlength={63}
			required
			disabled={s.renameLoading}
			onkeydown={(event) => {
				if (event.key === 'Enter' && !event.isComposing && event.keyCode !== 229) {
					event.preventDefault();
					void s.submitRename();
				}
			}}
		/>
	</Field>
	{#if s.renameError}<Alert tone="danger" class="mt-4">{s.renameError}</Alert>{/if}
	{#snippet actions()}
		<Button onclick={s.closeRename} variant="secondary" disabled={s.renameLoading}>{t('rename.cancel')}</Button>
		<Button onclick={s.submitRename} disabled={s.renameLoading || !s.canRename || !s.renameDraft.trim()} ariaBusy={s.renameLoading}>
			{s.renameLoading ? t('rename.saving') : t('rename.submit')}
		</Button>
	{/snippet}
</FormModal>
