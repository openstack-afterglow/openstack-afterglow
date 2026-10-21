<script lang="ts">
	import { onDestroy } from 'svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { t } from '$lib/i18n/ns/domain-auth';

	// Creates a password account from a verified onboarding link. Clear password
	// inputs before waiting so terminal states and late navigation retain no draft.
	let {
		idPrefix,
		submitLabel,
		disabled = false,
		onSubmit,
	}: {
		idPrefix: string;
		submitLabel: string;
		disabled?: boolean;
		onSubmit: (account: { name: string; password: string }) => Promise<void>;
	} = $props();

	let name = $state('');
	let password = $state('');
	let confirm = $state('');
	let submitting = $state(false);
	let attempted = $state(false);

	const nameError = $derived(attempted && !name.trim() ? t('onboarding.required') : '');
	// Mirrors the onboarding API's password bounds; the server remains authoritative.
	const PASSWORD_MIN = 12;
	const PASSWORD_MAX = 1024;
	const passwordError = $derived(
		attempted && !password ? t('onboarding.required')
			: password && password.length < PASSWORD_MIN && (attempted || confirm) ? t('onboarding.passwordTooShort')
				: '',
	);
	const confirmError = $derived(confirm && confirm !== password ? t('onboarding.passwordMismatch') : attempted && !confirm ? t('onboarding.required') : '');

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (submitting || disabled) return;
		attempted = true;
		if (!name.trim() || password.length < PASSWORD_MIN || confirm !== password) return;
		submitting = true;
		const account = { name: name.trim(), password };
		password = ''; confirm = ''; attempted = false;
		try {
			await onSubmit(account);
		} finally {
			password = '';
			confirm = '';
			attempted = false;
			submitting = false;
		}
	}
	onDestroy(() => { name = ''; password = ''; confirm = ''; });
</script>

<form class="onboarding-form" novalidate onsubmit={submit}>
	<p class="text-sm text-ink-2">{t('onboarding.personalOwnership')}</p>
	<Field label={t('onboarding.name')} for="{idPrefix}-name" help={t('onboarding.nameHelp')} error={nameError} required>
		<TextInput id="{idPrefix}-name" bind:value={name} autocomplete="username" disabled={submitting || disabled} required ariaInvalid={!!nameError} />
	</Field>
	<Field label={t('onboarding.password')} for="{idPrefix}-password" help={t('onboarding.passwordHelp')} error={passwordError} required>
		<TextInput id="{idPrefix}-password" type="password" bind:value={password} maxlength={PASSWORD_MAX} autocomplete="new-password" disabled={submitting || disabled} required ariaInvalid={!!passwordError} />
	</Field>
	<Field label={t('onboarding.passwordConfirm')} for="{idPrefix}-confirm" error={confirmError} required>
		<TextInput id="{idPrefix}-confirm" type="password" bind:value={confirm} maxlength={PASSWORD_MAX} autocomplete="new-password" disabled={submitting || disabled} required ariaInvalid={!!confirmError} />
	</Field>
	<Button type="submit" size="lg" disabled={submitting || disabled} ariaBusy={submitting}>{submitLabel}</Button>
	{#if submitting}
		<ActivityIndicator label={t('onboarding.processing')} class="onboarding-activity motion-fade" />
	{/if}
</form>

<style>
	.onboarding-form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.onboarding-form :global(.onboarding-activity) {
		align-self: center;
	}
</style>
