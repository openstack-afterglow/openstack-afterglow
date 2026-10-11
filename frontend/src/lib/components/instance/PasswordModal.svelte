<script lang="ts">
	import { onDestroy } from 'svelte';
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import { Alert, Button, Field, FormModal, TextInput } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/instance';
	import RichText from '$lib/i18n/RichText.svelte';

	interface Props {
		onClose: () => void;
	}

	let { onClose }: Props = $props();

	const s = useInstanceDetailController();

	let newPassword = $state('');
	let confirmPassword = $state('');
	let passwordError = $state('');
	let submitting = $state(false);
	const componentId = $props.id();
	let disposed = false;
	onDestroy(() => {
		disposed = true;
		newPassword = '';
		confirmPassword = '';
	});

	function onPasswordKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter') {
			event.preventDefault();
			void handleSetPassword();
		}
	}

	async function handleSetPassword() {
		if (submitting || s.passwordPrecheckLoading || !s.passwordPrecheck?.supported || !s.canChangePassword) return;
		if (newPassword !== confirmPassword) {
			passwordError = t('password.mismatch');
			return;
		}
		if (newPassword.length < 8 || newPassword.length > 128) {
			passwordError = t('password.invalidLength');
			return;
		}
		passwordError = '';
		submitting = true;
		try {
			const err = await s.doSetPassword(newPassword);
			if (disposed) return;
			if (err) {
				passwordError = err;
			} else {
				newPassword = '';
				confirmPassword = '';
				onClose();
			}
		} finally {
			submitting = false;
		}
	}
</script>

{#snippet instanceName(text: string)}<span class="text-ink-0">{text}</span>{/snippet}
{#snippet accountName(text: string)}<span class="text-warm-text">{text}</span>{/snippet}

<FormModal open={true} title={t('password.title')} {onClose} {submitting}>
	<p class="text-ink-2 text-sm mb-4"><RichText segments={t.rich('password.instance', { name: s.instance?.name ?? '' })} tags={{ resource: instanceName }} /></p>
	{#if s.passwordPrecheck?.os_admin_user}
		<p class="text-xs text-ink-2 mb-4"><RichText segments={t.rich('password.targetAccount', { account: s.passwordPrecheck.os_admin_user })} tags={{ account: accountName }} /></p>
	{:else}
		<p class="text-xs text-ink-2 mb-4"><RichText segments={t.rich('password.automaticAccount')} classes={{ code: 'text-ink-0' }} /></p>
	{/if}
	<Alert tone="warning" class="mb-4">{t('password.guestAgentNotice')}</Alert>
	<div class="space-y-3 mb-4">
		<Field label={t('password.newPassword')} for={`${componentId}-new-password`} required>
			<TextInput
				id={`${componentId}-new-password`}
				type="password"
				autocomplete="new-password"
				ariaLabel={t('password.newPassword')}
				required
				bind:value={newPassword}
				maxlength={128}
				disabled={submitting}
				placeholder={t('password.newPasswordPlaceholder')}
				onkeydown={onPasswordKeydown}
			/>
		</Field>
		<Field label={t('password.confirmPassword')} for={`${componentId}-confirm-password`} required>
			<TextInput
				id={`${componentId}-confirm-password`}
				type="password"
				autocomplete="new-password"
				ariaLabel={t('password.confirmPassword')}
				required
				bind:value={confirmPassword}
				maxlength={128}
				disabled={submitting}
				placeholder={t('password.confirmPasswordPlaceholder')}
				onkeydown={onPasswordKeydown}
			/>
		</Field>
	</div>
	{#if passwordError || s.passwordPrecheckReason || s.passwordPrecheckError}
		<Alert>{passwordError || s.passwordPrecheckReason || s.passwordPrecheckError}</Alert>
	{/if}
	{#snippet actions()}
		<Button onclick={onClose} variant="secondary" disabled={submitting}>{t('password.cancel')}</Button>
		<Button
			onclick={handleSetPassword}
			disabled={submitting || !s.canChangePassword || s.instance?.status !== 'ACTIVE' || s.passwordPrecheckLoading || !s.passwordPrecheck?.supported || !newPassword || !confirmPassword}
			ariaBusy={submitting}
		>
			{submitting ? t('password.changing') : t('password.submit')}
		</Button>
	{/snippet}
</FormModal>
