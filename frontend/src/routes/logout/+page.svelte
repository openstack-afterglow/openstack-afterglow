<script lang="ts">
	import { onMount } from 'svelte';
	import LoginBrandHeader from '$lib/components/auth/LoginBrandHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import LocaleSelect from '$lib/i18n/LocaleSelect.svelte';
	import { t } from '$lib/i18n/ns/shell';
	import { ensureLogoutStarted, logoutProgress, type LogoutStep } from '$lib/utils/logout';

	const steps = ['shell', 'server', 'local'] as const;
	const statusKeys = { pending: 'logout.pending', active: 'logout.active', done: 'logout.complete', warning: 'logout.unconfirmed' } as const satisfies Record<LogoutStep, Parameters<typeof t>[0]>;
	const finished = $derived($logoutProgress.phase === 'complete');
	const partial = $derived(steps.some(step => $logoutProgress[step] === 'warning'));
	const canLeave = $derived(finished && $logoutProgress.local === 'done');
	const heading = $derived(!finished ? t('logout.working')
		: $logoutProgress.local === 'warning' ? t('logout.pageTitle')
		: partial ? t('logout.partialTitle') : t('logout.finished'));

	onMount(() => { void ensureLogoutStarted(); });
</script>

<svelte:head><title>{t('logout.pageTitle')}</title></svelte:head>

<div class="logout-page">
	<div class="logout-locale"><LocaleSelect id="logout-locale" variant="labelled" /></div>
	<main class="logout-shell" aria-labelledby="logout-title">
		<LoginBrandHeader />
		<Card padding="lg">
			<div class="logout-content">
				<header class="logout-introduction">
					<h1 id="logout-title">{heading}</h1>
					<p>{$logoutProgress.all ? t('logout.allExplanation') : t('logout.explanation')}</p>
				</header>
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
					{#if $logoutProgress.local === 'warning'}
						<Alert tone="danger">{t('logout.localFailed')}</Alert>
					{:else if $logoutProgress.server === 'warning'}
						<Alert tone="warning">{$logoutProgress.all ? t('logout.allPartial') : t('logout.partial')}</Alert>
					{:else if !partial}
						<Alert tone="success">{t('logout.done')}</Alert>
					{/if}
					{#if $logoutProgress.shell === 'warning'}
						<Alert tone="warning">{t('logout.shellFailed')}</Alert>
					{/if}
				{/if}
				<Button href={$logoutProgress.loginHref} size="lg" disabled={!canLeave} class="logout-back">{t('logout.back')}</Button>
			</div>
		</Card>
	</main>
</div>

<style>
	.logout-page {
		min-height: 100dvh;
		display: grid;
		grid-template-rows: auto 1fr;
		background: var(--color-surface-canvas);
		color: var(--color-ink-0);
	}
	.logout-locale { justify-self: end; margin: 1rem; }
	.logout-shell { width: min(100%, 30rem); align-self: center; margin: 0 auto; padding: 1rem 1rem 3rem; }
	.logout-content { display: flex; flex-direction: column; gap: 1.5rem; }
	.logout-introduction h1 { margin: 0 0 0.5rem; font-size: 1.25rem; line-height: 1.4; font-weight: 600; text-wrap: balance; }
	.logout-introduction p { margin: 0; color: var(--color-ink-2); font-size: 0.875rem; line-height: 1.6; }
	.logout-steps { margin: 0; }
	.logout-step { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; padding-block: 0.875rem; border-bottom: 1px solid var(--color-line); font-size: 0.875rem; line-height: 1.5; }
	.logout-step:first-child { border-top: 1px solid var(--color-line); }
	.logout-step dt { min-width: 0; }
	.logout-step dd { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 0.375rem; max-width: 48%; margin: 0; text-align: end; color: var(--color-ink-2); }
	.logout-step[data-state='warning'] dd { color: var(--color-state-warning-text); }
	.logout-content :global(.logout-back) { width: 100%; white-space: normal; overflow-wrap: anywhere; }
	@media (max-width: 767px) {
		.logout-shell { padding-inline: 0.75rem; }
		.logout-step { gap: 0.75rem; }
	}
</style>
