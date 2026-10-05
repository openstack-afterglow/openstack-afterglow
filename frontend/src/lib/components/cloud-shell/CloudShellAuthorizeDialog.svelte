<script lang="ts">
	import { t } from '$lib/i18n/ns/containers-shell';
	import RichText from '$lib/i18n/RichText.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import { cloudShell } from '$lib/stores/cloudShell.svelte';

	const projectName = $derived(cloudShell.identity?.projectName || t('shell.currentProject'));
</script>

{#snippet projectLabel(text: string)}<span class="font-medium text-ink-1">{text}</span>{/snippet}

<Modal
	open={cloudShell.phase === 'consent'}
	onClose={() => cloudShell.cancelConsent()}
	ariaLabel={t('shell.authorize')}
>
	<section class="w-[min(34rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface-raised shadow-[var(--shadow-restraint)]">
		<header class="border-b border-line px-5 py-4 sm:px-6">
			<p class="text-xs font-semibold uppercase tracking-[0.14em] text-ink-3">{t('shell.sessionAuthorization')}</p>
			<h2 class="mt-1 font-display text-lg font-semibold text-ink-0">{t('shell.authorize')}</h2>
			<p class="mt-1 text-sm text-ink-2">
				<RichText segments={t.rich('shell.authorizeIntro', { projectName })} tags={{ project: projectLabel }} />
			</p>
		</header>

		<div class="space-y-4 px-5 py-5 sm:px-6">
			<Alert tone="info" title={t('shell.permissionsTitle')}>
				{t('shell.permissionsBody')}
			</Alert>

			<ul class="space-y-3 text-sm leading-6 text-ink-2">
				<li class="flex gap-3">
					<span class="mt-2 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true"></span>
					<span><RichText segments={t.rich('shell.tokenStorage', { path: '/dev/shm/afterglow' })} classes={{ code: 'font-mono text-xs text-ink-1' }} /></span>
				</li>
				<li class="flex gap-3">
					<span class="mt-2 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true"></span>
					<span><RichText segments={t.rich('shell.persistentHome', { size: cloudShell.homeSizeGiB })} classes={{ strong: 'font-medium text-ink-1' }} /></span>
				</li>
				<li class="flex gap-3">
					<span class="mt-2 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true"></span>
					<span>{t('shell.sessionLifetime')}</span>
				</li>
			</ul>
		</div>

		<footer class="flex flex-col-reverse gap-2 border-t border-line px-5 py-4 sm:flex-row sm:justify-end sm:px-6">
			<Button variant="ghost" onclick={() => cloudShell.cancelConsent()}>{t('shell.cancel')}</Button>
			<Button variant="primary" onclick={() => void cloudShell.approve()}>{t('shell.authorize')}</Button>
		</footer>
	</section>
</Modal>
