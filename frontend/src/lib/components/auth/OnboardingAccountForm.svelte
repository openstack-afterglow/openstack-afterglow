<script lang="ts">
	import { onDestroy } from 'svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/domain-auth';
	import { beginAuthExperience, type ExperienceContext } from './authExperience';

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
		onSubmit: (account: { name: string; password: string }, experience?: ExperienceContext) => Promise<void>;
	} = $props();

	let name = $state('');
	let password = $state('');
	let confirm = $state('');
	let submitting = $state(false);
	let attempted = $state(false);
	let live = true;

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
		const observation = beginAuthExperience(idPrefix === 'invitation' ? 'auth.invitation' : 'auth.signup', 'create', () => live);
		if (!name.trim() || password.length < PASSWORD_MIN || confirm !== password) {
			observation.validation(!name.trim() || !password || !confirm ? 'required' : 'policy');
			const key = !name.trim() || !password || !confirm ? 'onboarding.required' : confirm !== password ? 'onboarding.passwordMismatch' : 'onboarding.passwordTooShort';
			t(key); observation.message('domain-auth', key);
			void observation.applied();
			return;
		}
		submitting = true;
		observation.state('loading');
		const account = { name: name.trim(), password };
		password = ''; confirm = ''; attempted = false;
		try {
			if (observation.context) await onSubmit(account, observation.context); else await onSubmit(account);
		} finally {
			password = '';
			confirm = '';
			attempted = false;
			submitting = false;
		}
	}
	onDestroy(() => { live = false; name = ''; password = ''; confirm = ''; });
</script>

<form class="onboarding-form auth-flow" novalidate onsubmit={submit}>
	<p class="text-sm text-ink-2">{t('onboarding.personalOwnership')}</p>
	<Field label={t('onboarding.name')} for="{idPrefix}-name" help={t('onboarding.nameHelp')} error={nameError} required>
		<TextInput id="{idPrefix}-name" bind:value={name} autocomplete="username" disabled={submitting || disabled} required ariaInvalid={!!nameError} />
	</Field>
	<div class="auth-flow-fields">
		<Field label={t('onboarding.password')} for="{idPrefix}-password" help={t('onboarding.passwordHelp')} error={passwordError} required>
			<TextInput id="{idPrefix}-password" type="password" bind:value={password} maxlength={PASSWORD_MAX} autocomplete="new-password" disabled={submitting || disabled} required ariaInvalid={!!passwordError} />
		</Field>
		<Field label={t('onboarding.passwordConfirm')} for="{idPrefix}-confirm" error={confirmError} required>
			<TextInput id="{idPrefix}-confirm" type="password" bind:value={confirm} maxlength={PASSWORD_MAX} autocomplete="new-password" disabled={submitting || disabled} required ariaInvalid={!!confirmError} />
		</Field>
	</div>
	<div class="auth-flow-actions">
		<Button type="submit" size="lg" disabled={submitting || disabled} ariaBusy={submitting}>{submitLabel}</Button>
	</div>
	{#if submitting}
		<LoadingState variant="section" label={t('onboarding.processing')} class="onboarding-activity motion-fade"  />
	{/if}
</form>

<style>
	.onboarding-form :global(.onboarding-activity) {
		justify-self: center;
	}
</style>
