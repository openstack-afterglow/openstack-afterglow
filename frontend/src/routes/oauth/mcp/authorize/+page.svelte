<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { api, ApiError } from '$lib/api/client';
	import { auth } from '$lib/stores/auth';
	import {
		clearMcpConsentTicket,
		pendingMcpConsentTicket,
		storeMcpConsentTicket,
	} from '$lib/utils/mcpConsent';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { t } from '$lib/i18n/ns/public-entry';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	interface ConsentDetails {
		client_id: string;
		client_name: string;
		redirect_uri: string;
		scopes: string[];
		grant_deadline: string;
	}

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const ticket = $state<{ value: string | null }>({ value: null });

	let ready = $state(false);
	let loading = $state(true);
	let deciding = $state(false);
	let error = $state('');
	let consent = $state<ConsentDetails | null>(null);
	let loadedTicket = $state<string | null>(null);

	function message(error: unknown, fallback: string) {
		return error instanceof ApiError ? error.message : fallback;
	}

	function formatDeadline(value: string) {
		return new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'long', timeStyle: 'short' }).format(new Date(value));
	}

	function discardTicket() {
		clearMcpConsentTicket();
		ticket.value = null;
		consent = null;
	}

	async function loadConsent() {
		if (!ticket.value || !token || !projectId || loadedTicket === ticket.value) return;
		loading = true;
		error = '';
		try {
			consent = await api.get<ConsentDetails>(
				`/api/v1/auth/mcp-oauth/consents/${encodeURIComponent(ticket.value)}`,
				token,
				projectId,
			);
			loadedTicket = ticket.value;
		} catch (errorValue) {
			error = message(errorValue, t('mcpConsent.error.loadFailed'));
			discardTicket();
		} finally {
			loading = false;
		}
	}

	async function decide(decision: 'approve' | 'deny') {
		if (!ticket.value || !token || !projectId) return;
		deciding = true;
		error = '';
		try {
			const result = await api.post<{ redirect_uri: string }>(
				`/api/v1/auth/mcp-oauth/consents/${encodeURIComponent(ticket.value)}/${decision}`,
				{},
				token,
				projectId,
			);
			discardTicket();
			window.location.assign(result.redirect_uri);
		} catch (errorValue) {
			error = message(errorValue, decision === 'approve' ? t('mcpConsent.error.approveFailed') : t('mcpConsent.error.denyFailed'));
		} finally {
			deciding = false;
		}
	}

	onMount(() => {
		const queryTicket = $page.url.searchParams.get('ticket');
		if (queryTicket) {
			if (!storeMcpConsentTicket(queryTicket)) {
				clearMcpConsentTicket();
				error = t('mcpConsent.error.invalidRequest');
			}
			try {
				history.replaceState(null, '', '/oauth/mcp/authorize');
			} catch {
				// URL cleanup is defense in depth; the backend still validates the ticket.
			}
		}
		ticket.value = pendingMcpConsentTicket();
		ready = true;
		if (!ticket.value && !error) error = t('mcpConsent.error.missingOrExpired');
	});

	$effect(() => {
		if (!ready) return;
		if (!ticket.value) {
			loading = false;
			return;
		}
		if (!token || !projectId) {
			void goto('/login');
			return;
		}
		void loadConsent();
	});
</script>

<svelte:head>
	<meta name="referrer" content="no-referrer" />
</svelte:head>

<main class="consent-page">
	<Card surface="raised" padding="lg" class="consent-card motion-stagger">
		<header>
			<p class="eyebrow">{t('mcpConsent.eyebrow')}</p>
			<h1>{t('mcpConsent.title')}</h1>
			<p>{t('mcpConsent.description')}</p>
		</header>

		{#if error}
			<Alert tone="danger" title={t('mcpConsent.error.title')}>
				{#snippet children()}{error}{/snippet}
			</Alert>
		{:else if loading}
			<ActivityIndicator label={t('mcpConsent.loading')} />
		{:else if consent}
			{@const requestsManage = consent.scopes.includes('mcp:write')}
			<section aria-labelledby="consent-client-heading" class="details">
				<div><span>{t('mcpConsent.details.client')}</span><strong id="consent-client-heading">{consent.client_name}</strong></div>
				<div><span>{t('mcpConsent.details.clientId')}</span><code>{consent.client_id}</code></div>
				<div><span>{t('mcpConsent.details.redirectUri')}</span><code>{consent.redirect_uri}</code></div>
				<div><span>{t('mcpConsent.details.permissions')}</span><div class="scopes">{#each consent.scopes as scope}<StatusChip status={scope === 'mcp:write' ? 'manage' : 'read'} />{/each}</div></div>
				<div><span>{t('mcpConsent.details.deadline')}</span><strong>{formatDeadline(consent.grant_deadline)}</strong></div>
			</section>
			<Alert tone={requestsManage ? 'warning' : 'info'} title={requestsManage ? t('mcpConsent.manage.title') : t('mcpConsent.read.title')}>
				{#snippet children()}{requestsManage ? t('mcpConsent.manage.body') : t('mcpConsent.read.body')}{/snippet}
			</Alert>
			<div class="actions">
				{#if deciding}
					<ActivityIndicator label={t('mcpConsent.actions.processing')} class="decision-activity motion-fade" />
				{/if}
				<Button variant="danger-outline" onclick={() => decide('deny')} disabled={deciding}>{t('mcpConsent.actions.deny')}</Button>
				<Button onclick={() => decide('approve')} disabled={deciding}>{requestsManage ? t('mcpConsent.actions.allowManage') : t('mcpConsent.actions.allowRead')}</Button>
			</div>
		{/if}
	</Card>
</main>

<style>
	.consent-page { display: grid; min-height: 100vh; place-items: center; padding: 1rem; background: var(--color-surface-canvas); }
	:global(.consent-card) { width: min(42rem, 100%); display: grid; gap: 1rem; }
	header h1 { margin: 0; color: var(--color-ink-0); font-size: 1.5rem; }
	header p { margin: 0.5rem 0 0; color: var(--color-ink-2); line-height: 1.5; }
	.eyebrow { color: var(--color-accent) !important; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
	.details { display: grid; gap: 0.75rem; padding: 1rem; border: 1px solid var(--color-line); border-radius: 0.75rem; background: var(--color-surface-sunken); }
	.details > div { display: grid; gap: 0.25rem; }
	.details span { color: var(--color-ink-2); font-size: 0.75rem; }
	.details strong, .details code { color: var(--color-ink-0); font-size: 0.875rem; overflow-wrap: anywhere; }
	.scopes { display: flex; gap: 0.5rem; flex-wrap: wrap; }
	.actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 0.5rem; }
	.actions :global(.decision-activity) { margin-right: auto; }
</style>
