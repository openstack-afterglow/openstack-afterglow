<script lang="ts">
	import { onMount } from 'svelte';
	import AuthStudioShell from '$lib/components/auth/AuthStudioShell.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { siteConfig } from '$lib/config/site';
	import { t } from '$lib/i18n/ns/shell';
	import { t as tp } from '$lib/i18n/ns/public-entry';
	import { ensureLogoutStarted, logoutProgress, type LogoutStep } from '$lib/utils/logout';
	import { get } from 'svelte/store';
	import { auth } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { beginAuthExperience, createAuthNoticePresenter, type AuthExperience } from '$lib/components/auth/authExperience';

	const steps = ['shell', 'server', 'local'] as const;
	const statusKeys = { pending: 'logout.pending', active: 'logout.active', done: 'logout.complete', warning: 'logout.unconfirmed' } as const satisfies Record<LogoutStep, Parameters<typeof t>[0]>;
	const finished = $derived($logoutProgress.phase === 'complete');
	const partial = $derived(steps.some(step => $logoutProgress[step] === 'warning'));
	const canLeave = $derived(finished && $logoutProgress.local === 'done');
	const heading = $derived(!finished ? t('logout.working')
		: $logoutProgress.local === 'warning' ? t('logout.pageTitle')
		: partial ? t('logout.partialTitle') : t('logout.finished'));

	// Authored glyph state marker; status text below remains the accessible source.
	const art = $derived(!finished ? '[ : : · · ]' : partial || $logoutProgress.local === 'warning' ? '[ ! ]' : '[ + ]');
	let live = false;
	let observation = $state.raw<AuthExperience>();
	const presentNotice = createAuthNoticePresenter();
	$effect(() => {
		if (!observation) return;
		const progress = $logoutProgress;
		const step = progress.local === 'active' || progress.phase === 'complete' ? 2 : progress.server === 'active' || progress.server === 'done' || progress.server === 'warning' ? 1 : 0;
		observation.state(progress.phase !== 'complete' ? 'loading' : partial ? 'error' : 'ready', step);
		void observation.applied(() => get(logoutProgress) === progress);
	});
	$effect(() => {
		const progress = $logoutProgress;
		const key = progress.phase !== 'complete' ? null : progress.local === 'warning' ? 'logout.localFailed' : progress.server === 'warning' ? progress.all ? 'logout.allPartial' : 'logout.partial' : !partial ? 'logout.done' : null;
		if (key) t(key);
		presentNotice('result', observation, 'shell', key, progress.local === 'warning' ? 'danger' : partial ? 'warning' : 'success');
		const shell = progress.phase === 'complete' && progress.shell === 'warning' ? 'logout.shellFailed' : null;
		if (shell) t(shell);
		presentNotice('shell', observation, 'shell', shell, 'warning');
	});

	onMount(() => {
		live = true;
		observation = beginAuthExperience('page', 'view', () => live);
		let previous = '';
		const unsubscribe = auth.subscribe(state => {
			const next = sessionScopeKey(state);
			if (previous && next !== previous) observation = beginAuthExperience('page', 'view', () => live);
			previous = next;
		});
		if (observation.context) void ensureLogoutStarted(observation.context); else void ensureLogoutStarted();
		return () => { live = false; unsubscribe(); };
	});
</script>

<svelte:head><title>{t('logout.pageTitle')}</title></svelte:head>

<AuthStudioShell variant="logout" localeId="logout-locale" themeId="logout-theme" footerNote={tp('authStudio.logout.footerNote')}>
	<div class="logout-content">
		<header class="logout-introduction">
			<p class="auth-eyebrow" aria-hidden="true">{tp('authStudio.logout.formEyebrow', { site: $siteConfig.site_name.toUpperCase() })}</p>
			<h1 id="logout-title">{heading}</h1>
			<p>{$logoutProgress.all ? t('logout.allExplanation') : t('logout.explanation')}</p>
		</header>
		<div class="logout-art" aria-hidden="true">{art}</div>
		<dl class="logout-steps" aria-live="polite" aria-busy={!finished}>
			{#each steps as step (step)}
				<div class="logout-step" data-step={step} data-state={$logoutProgress[step]}>
					<dt>{t(`logout.${step}`)}</dt>
					<dd>
						{#if $logoutProgress[step] === 'active'}
							<LoadingState variant="inline" label="" aria-hidden="true" />
						{/if}
						<span>{step === 'server' && $logoutProgress.serverNotRequired ? t('logout.notRequired') : t(statusKeys[$logoutProgress[step]])}</span>
					</dd>
				</div>
			{/each}
		</dl>
		{#if finished}
			<div class="logout-messages">
				{#if $logoutProgress.local === 'warning'}
					<p class="logout-status" data-tone="danger" role="alert">{t('logout.localFailed')}</p>
				{:else if $logoutProgress.server === 'warning'}
					<p class="logout-status" data-tone="warning" role="status">{$logoutProgress.all ? t('logout.allPartial') : t('logout.partial')}</p>
				{:else if !partial}
					<p class="logout-status" data-tone="success" role="status">{t('logout.done')}</p>
				{/if}
				{#if $logoutProgress.shell === 'warning'}
					<p class="logout-status" data-tone="warning" role="status">{t('logout.shellFailed')}</p>
				{/if}
			</div>
		{/if}
		<Button href={$logoutProgress.loginHref} size="lg" disabled={!canLeave} class="logout-back">{t('logout.back')}<span aria-hidden="true">↗</span></Button>
	</div>
</AuthStudioShell>

<style>
	.logout-content { display: flex; flex-direction: column; gap: 1rem; }
	.logout-introduction h1 { margin: 0 0 0.65rem; font-size: 1.8rem; line-height: 1.35; font-weight: 500; letter-spacing: -0.055em; word-break: keep-all; text-wrap: balance; }
	.logout-introduction p:last-child { margin: 0; font-size: 0.8125rem; line-height: 1.6; color: var(--color-ink-2); }
	.logout-art { padding: 0.5rem 0; font: 1.2rem var(--font-mono); color: var(--color-warm); white-space: pre; }
	.logout-steps { margin: 0; }
	.logout-step { display: flex; align-items: center; justify-content: space-between; gap: 1rem; min-height: 48px; border-bottom: 1px solid var(--color-line); font-size: 0.8125rem; line-height: 1.5; }
	.logout-step:first-child { border-top: 1px solid var(--color-line); }
	.logout-step dt { min-width: 0; }
	.logout-step dd { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 0.375rem; max-width: 48%; margin: 0; text-align: end; color: var(--color-warm-text); }
	.logout-step[data-state='pending'] dd { color: var(--color-ink-2); }
	.logout-step[data-state='warning'] dd { color: var(--color-state-warning-text); }
	.logout-messages { display: flex; flex-direction: column; gap: 0.35rem; }
	.logout-status { margin: 0; font-size: 0.75rem; line-height: 1.6; color: var(--color-ink-2); }
	.logout-status[data-tone='warning'] { color: var(--color-state-warning-text); }
	.logout-status[data-tone='danger'] { color: var(--color-state-danger-text); }
	.logout-content :global(.logout-back) {
		width: 100%; min-height: 48px; justify-content: space-between; padding-inline: 1rem;
		background: var(--color-action-warm); color: var(--color-action-on-warm); border-color: transparent;
		white-space: normal; overflow-wrap: anywhere;
	}
	.logout-content :global(.logout-back:hover:not([aria-disabled='true'])) { background: var(--color-action-warm-hover); }
	.logout-content :global(.logout-back[aria-disabled='true']) { opacity: 0.55; }
	@media (min-width: 1600px) { .logout-introduction h1 { font-size: 2rem; } }
	@media (max-width: 767px) { .logout-introduction h1 { font-size: 1.4rem; } }
	@media (max-height: 800px) {
		.logout-content { gap: 0.65rem; }
		.logout-introduction .auth-eyebrow { display: none; }
		.logout-introduction h1 { font-size: 1.35rem; line-height: 1.3; margin-bottom: 0.4rem; }
		.logout-introduction p:last-child { font-size: 0.75rem; }
		.logout-art { font-size: 1rem; padding: 0; }
		.logout-step { min-height: 40px; }
		.logout-status { font-size: 0.6875rem; }
	}
	@media (max-height: 620px) {
		.logout-art, .logout-introduction p:last-child { display: none; }
		.logout-step { min-height: 36px; }
		.logout-content :global(.logout-back) { min-height: 44px; }
	}
</style>
