<script lang="ts">
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import { t } from '$lib/i18n/ns/instance';
	import RichText from '$lib/i18n/RichText.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

	interface Props {
		onClose: () => void;
	}

	let { onClose }: Props = $props();

	const s = useInstanceDetailController();

	let newPassword = $state('');
	let confirmPassword = $state('');
	let passwordError = $state('');
	let submitting = $state(false);

	async function handleSetPassword() {
		if (newPassword !== confirmPassword) {
			passwordError = t('password.mismatch');
			return;
		}
		if (newPassword.length < 8) {
			passwordError = t('password.tooShort');
			return;
		}
		passwordError = '';
		submitting = true;
		try {
			const err = await s.doSetPassword(newPassword);
			if (err) {
				passwordError = err;
			} else {
				onClose();
			}
		} finally {
			submitting = false;
		}
	}
</script>

{#snippet instanceName(text: string)}<span class="text-ink-0">{text}</span>{/snippet}
{#snippet accountName(text: string)}<span class="text-warm-text">{text}</span>{/snippet}
{#snippet sshNotice(text: string)}<span class="text-ink-2 font-medium">{text}</span>{/snippet}
{#snippet keypairsLink(text: string)}<a href="/dashboard/compute/keypairs" class="text-cyan-400 hover:underline">{text}</a>{/snippet}

<Modal open={true} onClose={onClose} labelledBy="instance-password-title">
	<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
		<h3 id="instance-password-title" class="text-ink-0 font-semibold text-lg mb-1">{t('password.title')}</h3>
		<p class="text-ink-2 text-sm mb-4"><RichText segments={t.rich('password.instance', { name: s.instance?.name ?? '' })} tags={{ resource: instanceName }} /></p>
		{#if s.passwordPrecheck?.os_admin_user}
			<p class="text-xs text-ink-2 mb-4"><RichText segments={t.rich('password.targetAccount', { account: s.passwordPrecheck.os_admin_user })} tags={{ account: accountName }} /></p>
		{:else}
			<p class="text-xs text-ink-2 mb-4"><RichText segments={t.rich('password.automaticAccount')} classes={{ code: 'text-warm-text' }} /></p>
		{/if}
		<div class="bg-yellow-900/20 border border-yellow-800/40 rounded-lg p-3 mb-4 text-xs text-yellow-300">
			{t('password.guestAgentNotice')}
		</div>
		<div class="space-y-3 mb-4">
			<div>
				<label class="block text-sm text-ink-2 mb-1" for="new-password">{t('password.newPassword')}</label>
				<input
					id="new-password"
					type="password"
					bind:value={newPassword}
					placeholder={t('password.newPasswordPlaceholder')}
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
				/>
			</div>
			<div>
				<label class="block text-sm text-ink-2 mb-1" for="confirm-password">{t('password.confirmPassword')}</label>
				<input
					id="confirm-password"
					type="password"
					bind:value={confirmPassword}
					placeholder={t('password.confirmPasswordPlaceholder')}
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
				/>
			</div>
		</div>
		{#if passwordError}
			<p class="text-red-400 text-sm mb-3">{passwordError}</p>
		{/if}
		<div class="bg-surface-sunken/60 border border-line-2/40 rounded-lg p-3 mb-4 text-xs text-ink-2">
			<RichText segments={t.rich('password.sshKeyNotice')} tags={{ notice: sshNotice, keypairs: keypairsLink }} />
		</div>
		<div class="flex justify-end gap-3">
			<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{t('password.cancel')}</button>
			<button
				onclick={handleSetPassword}
				disabled={submitting || s.passwordPrecheckLoading || !newPassword || !confirmPassword}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg disabled:opacity-30"
			>
				{#if submitting}<ActivityIndicator size="xs" label={t('password.changing')} />{:else if s.passwordPrecheckLoading}<ActivityIndicator size="xs" label={t('header.checking')} />{:else}{t('password.submit')}{/if}
			</button>
		</div>
	</div>
</Modal>
