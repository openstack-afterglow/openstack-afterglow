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
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import AuthStudioShell from '$lib/components/auth/AuthStudioShell.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import { t } from '$lib/i18n/ns/public-entry';
	import { derived } from 'svelte/store';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { beginAuthExperience, observedAuthText, type AuthExperience } from '$lib/components/auth/authExperience';

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let ready = $state(false);
	let code = $state('');
	let deciding = $state(false);
	let error = $state('');
	let outcome = $state<'approved' | 'denied' | null>(null);
	let mounted = false;
	let ownerEpoch = 0;
	let outcomeExperience = $state.raw<AuthExperience>();

	function errorMessage(value: unknown, observation: AuthExperience): string {
		if (value instanceof ApiError) { observation.unknownMessage(); return value.message; }
		return observedAuthText(observation, 'public-entry', t)('claudeConsent.error.requestFailed');
	}

	async function decide(action: 'approve' | 'deny') {
		if (!token || !projectId || deciding) return;
		const epoch = ownerEpoch;
		const observation = beginAuthExperience('mcp.consent', action, () => mounted && epoch === ownerEpoch, 'mcp');
		const text = observedAuthText(observation, 'public-entry', t);
		if (!storeClaudeGatewayUserCode(code)) {
			error = text('claudeConsent.error.checkCode');
			observation.validation('format'); observation.state('error'); void observation.applied();
			return;
		}

		deciding = true;
		observation.state('loading');
		error = '';
		try {
			const normalizedCode = pendingClaudeGatewayUserCode();
			if (!normalizedCode) throw new Error('Missing normalized device code');
			await api.post(
				'/api/v1/chat/claude-gateway/authorize',
				{ user_code: normalizedCode, action },
				token,
				projectId,
				observation.options,
			);
			outcome = action === 'approve' ? 'approved' : 'denied';
			clearClaudeGatewayAuthorization();
			// The source response confirms only this browser decision, not a remote client session.
			outcomeExperience = observation;
			observation.state('ready');
		} catch (value) {
			error = errorMessage(value, observation);
			observation.state('error');
		} finally {
			deciding = false;
			void observation.applied();
		}
	}

	function leave() {
		clearClaudeGatewayAuthorization();
		beginAuthExperience('mcp.consent', 'navigate', () => mounted, 'mcp').state('loading');
		void goto('/dashboard/chat/settings');
	}

	onMount(() => {
		mounted = true;
		const observation = beginAuthExperience('mcp.consent', 'load', () => mounted, 'mcp');
		const text = observedAuthText(observation, 'public-entry', t);
		let previous = '';
		const unsubscribe = derived(auth, state => sessionScopeKey(state)).subscribe(key => {
			if (previous && previous !== key) ownerEpoch++;
			previous = key;
		});
		beginClaudeGatewayAuthorization();
		const queryCode = $page.url.searchParams.get('user_code');
		if (queryCode && !storeClaudeGatewayUserCode(queryCode)) {
			error = text('claudeConsent.error.invalidUrlCode'); observation.validation('format');
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
		observation.state(error ? 'error' : 'ready'); void observation.applied();
		return () => { mounted = false; ownerEpoch++; unsubscribe(); };
	});

	$effect(() => {
		if (!ready || outcome) return;
		if (!token) {
			void goto('/login');
			return;
		}
		if (!projectId) void goto('/select-project');
	});

	$effect(() => {
		if (!outcome || !outcomeExperience) return;
		const key = outcome === 'approved' ? 'claudeConsent.approved.body' : 'claudeConsent.denied.body';
		t(key); outcomeExperience.message('public-entry', key, outcome === 'approved' ? 'success' : 'info');
	});
</script>

<svelte:head>
	<title>{t('claudeConsent.pageTitle')}</title>
	<meta name="referrer" content="no-referrer" />
</svelte:head>

<AuthStudioShell
	variant="consent"
	wide
	localeId="claude-consent-locale"
	themeId="claude-consent-theme"
	footerNote={t('claudeConsent.eyebrow')}
>
	<div class="auth-flow">
		<header class="auth-flow-heading">
			<h1>{t('claudeConsent.title')}</h1>
			<p>{t('claudeConsent.description')}</p>
		</header>

		{#if outcome === 'approved'}
			<Alert tone="success" title={t('claudeConsent.approved.title')}>
				{#snippet children()}{t('claudeConsent.approved.body')}{/snippet}
			</Alert>
			<div class="auth-flow-actions"><Button onclick={leave}>{t('claudeConsent.actions.chatSettings')}</Button></div>
		{:else if outcome === 'denied'}
			<Alert tone="info" title={t('claudeConsent.denied.title')}>
				{#snippet children()}{t('claudeConsent.denied.body')}{/snippet}
			</Alert>
			<div class="auth-flow-actions"><Button variant="secondary" onclick={leave}>{t('claudeConsent.actions.chatSettings')}</Button></div>
		{:else}
			{#if error}<Alert tone="danger" title={t('claudeConsent.error.title')}>{#snippet children()}{error}{/snippet}</Alert>{/if}

			<section class="gateway-consent" aria-labelledby="gateway-code-heading">
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
					class="gateway-form"
					onsubmit={(event) => {
						event.preventDefault();
						void decide('approve');
					}}
				>
					<div class="auth-flow-fields">
						<Field label={t('claudeConsent.code.label')} for="gateway-code" help={t('claudeConsent.code.help', { example: 'ABCD-2345' })}>
							<TextInput
								id="gateway-code"
								ariaLabel={t('claudeConsent.code.label')}
								maxlength={9}
								placeholder="ABCD-2345"
								bind:value={code}
							/>
						</Field>
					</div>
					<div class="auth-flow-actions">
						{#if deciding}
							<LoadingState variant="inline" label={t('claudeConsent.actions.processing')} class="decision-activity" />
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
	</div>
</AuthStudioShell>

<style>
	.gateway-consent, .gateway-form { display: grid; gap: 1.25rem; min-width: 0; }
	.scope-summary { display: grid; gap: 0.75rem; padding-bottom: 1rem; border-bottom: 1px solid var(--color-line); min-width: 0; }
	.scope-summary span { display: block; color: var(--color-ink-2); font-size: var(--type-identifier); }
	.scope-summary strong { display: block; margin-top: 0.25rem; color: var(--color-ink-0); font-size: var(--type-body); font-weight: 500; overflow-wrap: anywhere; }
	.scopes { display: flex; flex-wrap: wrap; gap: 0.5rem; min-width: 0; }
	.scopes :global(.chip .label) { white-space: normal; overflow-wrap: anywhere; }
	.auth-flow-actions :global(button) { max-width: 100%; white-space: normal; overflow-wrap: anywhere; }
	.auth-flow-actions :global(.decision-activity) { flex-basis: 100%; }
</style>
