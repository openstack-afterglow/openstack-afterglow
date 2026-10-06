<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { api, ApiError } from '$lib/api/client';
	import { auth } from '$lib/stores/auth';
	import {
		beginClaudeGatewayAuthorization,
		clearClaudeGatewayAuthorization,
		pendingClaudeGatewayUserCode,
		storeClaudeGatewayUserCode,
	} from '$lib/utils/mcpConsent';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import { t } from '$lib/i18n/ns/public-entry';

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let ready = $state(false);
	let code = $state('');
	let deciding = $state(false);
	let error = $state('');
	let outcome = $state<'approved' | 'denied' | null>(null);

	function errorMessage(value: unknown): string {
		return value instanceof ApiError ? value.message : t('claudeConsent.error.requestFailed');
	}

	async function decide(action: 'approve' | 'deny') {
		if (!token || !projectId || deciding) return;
		if (!storeClaudeGatewayUserCode(code)) {
			error = t('claudeConsent.error.checkCode');
			return;
		}

		deciding = true;
		error = '';
		try {
			const normalizedCode = pendingClaudeGatewayUserCode();
			if (!normalizedCode) throw new Error('Missing normalized device code');
			await api.post(
				'/api/v1/chat/claude-gateway/authorize',
				{ user_code: normalizedCode, action },
				token,
				projectId,
			);
			outcome = action === 'approve' ? 'approved' : 'denied';
			clearClaudeGatewayAuthorization();
		} catch (value) {
			error = errorMessage(value);
		} finally {
			deciding = false;
		}
	}

	function leave() {
		clearClaudeGatewayAuthorization();
		void goto('/dashboard/chat/settings');
	}

	onMount(() => {
		beginClaudeGatewayAuthorization();
		const queryCode = $page.url.searchParams.get('user_code');
		if (queryCode && !storeClaudeGatewayUserCode(queryCode)) {
			error = t('claudeConsent.error.invalidUrlCode');
		}
		if (queryCode) {
			try {
				history.replaceState(null, '', '/oauth/claude/authorize');
			} catch {
				// URL cleanup is defense in depth; Lumen still verifies the code hash and expiry.
			}
		}
		code = pendingClaudeGatewayUserCode() ?? '';
		ready = true;
	});

	$effect(() => {
		if (!ready || outcome) return;
		if (!token) {
			void goto('/login');
			return;
		}
		if (!projectId) void goto('/select-project');
	});
</script>

<svelte:head>
	<title>{t('claudeConsent.pageTitle')}</title>
	<meta name="referrer" content="no-referrer" />
</svelte:head>

<main class="authorization-page">
	<Card surface="raised" padding="lg" class="authorization-card motion-stagger">
		<header>
			<p class="eyebrow">{t('claudeConsent.eyebrow')}</p>
			<h1>{t('claudeConsent.title')}</h1>
			<p>{t('claudeConsent.description')}</p>
		</header>

		{#if outcome === 'approved'}
			<Alert tone="success" title={t('claudeConsent.approved.title')}>
				{#snippet children()}{t('claudeConsent.approved.body')}{/snippet}
			</Alert>
			<div class="actions"><Button onclick={leave}>{t('claudeConsent.actions.chatSettings')}</Button></div>
		{:else if outcome === 'denied'}
			<Alert tone="info" title={t('claudeConsent.denied.title')}>
				{#snippet children()}{t('claudeConsent.denied.body')}{/snippet}
			</Alert>
			<div class="actions"><Button variant="secondary" onclick={leave}>{t('claudeConsent.actions.chatSettings')}</Button></div>
		{:else}
			{#if error}<Alert tone="danger" title={t('claudeConsent.error.title')}>{#snippet children()}{error}{/snippet}</Alert>{/if}

			<section class="details" aria-labelledby="gateway-code-heading">
				<div class="scope-summary">
					<div>
						<span>{t('claudeConsent.details.scope')}</span>
						<strong id="gateway-code-heading">{t('claudeConsent.details.scopeDescription')}</strong>
					</div>
					<div class="scopes" aria-label={t('claudeConsent.details.permissions')}>
						<StatusChip status="models:read" />
						<StatusChip status="compat:completions:write" />
					</div>
				</div>
				<form
					onsubmit={(event) => {
						event.preventDefault();
						void decide('approve');
					}}
				>
					<Field label={t('claudeConsent.code.label')} for="gateway-code" help={t('claudeConsent.code.help', { example: 'ABCD-2345' })}>
						<TextInput
							id="gateway-code"
							ariaLabel={t('claudeConsent.code.label')}
							maxlength={9}
							placeholder="ABCD-2345"
							bind:value={code}
						/>
					</Field>
					<div class="actions">
						{#if deciding}
							<ActivityIndicator label={t('claudeConsent.actions.processing')} class="decision-activity motion-fade" />
						{/if}
						<Button variant="danger-outline" type="button" onclick={() => decide('deny')} disabled={deciding || !code.trim()}>{t('claudeConsent.actions.deny')}</Button>
						<Button type="submit" disabled={deciding || !code.trim()}>{t('claudeConsent.actions.approve')}</Button>
					</div>
				</form>
			</section>

			<Alert tone="warning" title={t('claudeConsent.warning.title')}>
				{#snippet children()}{t('claudeConsent.warning.body')}{/snippet}
			</Alert>
		{/if}
	</Card>
</main>

<style>
	.authorization-page { display: grid; min-height: 100vh; place-items: center; padding: 1rem; background: var(--color-surface-canvas); }
	:global(.authorization-card) { width: min(42rem, 100%); display: grid; gap: 1rem; }
	header h1 { margin: 0; color: var(--color-ink-0); font-size: 1.5rem; }
	header p { margin: 0.5rem 0 0; color: var(--color-ink-2); line-height: 1.5; }
	.eyebrow { color: var(--color-accent) !important; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
	.details { display: grid; gap: 1rem; padding: 1rem; border: 1px solid var(--color-line); border-radius: 0.75rem; background: var(--color-surface-sunken); }
	.scope-summary { display: grid; gap: 0.75rem; }
	.scope-summary span { display: block; color: var(--color-ink-2); font-size: 0.75rem; }
	.scope-summary strong { color: var(--color-ink-0); font-size: 0.875rem; }
	.scopes { display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.actions { display: flex; flex-direction: column-reverse; gap: 0.5rem; margin-top: 1rem; }
	.actions :global(.decision-activity) { align-self: center; }
	@media (min-width: 640px) {
		.scope-summary { align-items: center; grid-template-columns: 1fr auto; }
		.actions { flex-direction: row; justify-content: flex-end; }
		.actions :global(.decision-activity) { margin-right: auto; }
	}
</style>
