<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth, isLoggedIn } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import type { InvitationInfo } from '$lib/types/project';
	import { t } from '$lib/i18n/ns/public-entry';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import RichText from '$lib/i18n/RichText.svelte';

	const token = $derived(($page.params as Record<string, string>)['token'] ?? '');

	let info = $state<InvitationInfo | null>(null);
	let loading = $state(true);
	let loadError = $state('');
	let actionDone = $state('');
	let actionError = $state('');
	let acting = $state(false);

	$effect(() => {
		if (token) loadInfo();
	});

	async function loadInfo() {
		loading = true;
		loadError = '';
		try {
			info = await api.get<InvitationInfo>(`/api/v1/invitations/${token}`);
		} catch (e) {
			loadError = e instanceof ApiError ? e.message : t('invitations.error.loadFailed');
		} finally {
			loading = false;
		}
	}

	async function accept() {
		if (acting) return;
		acting = true;
		actionError = '';
		try {
			await api.post(`/api/v1/invitations/${token}/accept`, {}, $auth.token ?? undefined);
			actionDone = 'accepted';
		} catch (e) {
			actionError = e instanceof ApiError ? e.message : t('invitations.error.acceptFailed');
		} finally {
			acting = false;
		}
	}

	async function decline() {
		if (acting) return;
		acting = true;
		actionError = '';
		try {
			await api.post(`/api/v1/invitations/${token}/decline`, {});
			actionDone = 'declined';
		} catch (e) {
			actionError = e instanceof ApiError ? e.message : t('invitations.error.declineFailed');
		} finally {
			acting = false;
		}
	}

	function loginAndAccept() {
		goto(`/?next=/invitations/${token}`);
	}

	function fmtDate(iso: string): string {
		return new Date(iso).toLocaleDateString(intlLocale(), {
			year: 'numeric',
			month: 'long',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit',
		});
	}

	const isExpiredOrHandled = $derived(
		info && ['accepted', 'declined', 'revoked', 'expired'].includes(info.status)
	);
</script>

<main id="main-content" tabindex="-1" class="min-h-screen bg-surface-canvas flex items-center justify-center px-4">
	<div class="w-full max-w-md">
		<!-- 로고 헤더 -->
		<div class="text-center mb-8 motion-enter">
			<div class="text-2xl font-bold text-ink-0 mb-1">{t('invitations.brand')}</div>
			<div class="text-sm text-ink-2">{t('invitations.title')}</div>
		</div>

		{#if loading}
			<div class="bg-surface-base border border-line rounded-xl p-8 text-center motion-enter" style="--motion-index: 1">
				<ActivityIndicator label={t('invitations.loading')} />
			</div>
		{:else if loadError}
			<div class="bg-surface-base border border-state-danger/40 rounded-xl p-8 text-center motion-enter" style="--motion-index: 1">
				<div class="text-state-danger-text text-sm">{loadError}</div>
			</div>
		{:else if actionDone === 'accepted'}
			<div class="bg-surface-base border border-state-success/40 rounded-xl p-8 text-center motion-enter" style="--motion-index: 1">
				<div class="w-12 h-12 bg-state-success/15 rounded-full flex items-center justify-center mx-auto mb-4 motion-pop" style="--motion-index: 2">
					<svg class="w-6 h-6 text-state-success-text" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
						<path class="motion-draw" pathLength="1" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
					</svg>
				</div>
				<div class="text-ink-0 font-medium mb-1">{t('invitations.accepted.title')}</div>
				<div class="text-ink-2 text-sm mb-5"><RichText segments={t.rich('invitations.accepted.body', { projectName: info?.project_name })} classes={{ strong: 'text-ink-2' }} /></div>
				<a href="/select-project" class="inline-block px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg transition-colors">
					{t('invitations.actions.selectProject')}
				</a>
			</div>
		{:else if actionDone === 'declined'}
			<div class="bg-surface-base border border-line-2 rounded-xl p-8 text-center motion-enter" style="--motion-index: 1">
				<div class="text-ink-2 text-sm">{t('invitations.declined')}</div>
			</div>
		{:else if info}
			<div class="bg-surface-base border border-line rounded-xl p-6 motion-enter" style="--motion-index: 1">
				<!-- 초대 정보 -->
				<div class="mb-6">
					<div class="text-xs text-ink-2 uppercase tracking-wide mb-1">{t('invitations.details.project')}</div>
					<div class="text-ink-0 font-semibold text-lg">{info.project_name}</div>
				</div>

				<div class="space-y-3 text-sm mb-6">
					<div class="flex justify-between">
						<span class="text-ink-2">{t('invitations.details.inviter')}</span>
						<span class="text-ink-1">{info.inviter_name || t('invitations.details.unknownInviter')}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-ink-2">{t('invitations.details.email')}</span>
						<span class="text-ink-1">{info.invited_email}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-ink-2">{t('invitations.details.expiresAt')}</span>
						<span class="text-ink-1">{fmtDate(info.expires_at)}</span>
					</div>
				</div>

				{#if isExpiredOrHandled}
					<div class="text-center py-2 text-sm text-ink-2">
						{#if info.status === 'accepted'}
							{t('invitations.status.accepted')}
						{:else if info.status === 'declined'}
							{t('invitations.status.declined')}
						{:else if info.status === 'expired'}
							{t('invitations.status.expired')}
						{:else}
							{t('invitations.status.revoked')}
						{/if}
					</div>
				{:else if !$isLoggedIn}
					<button
						onclick={loginAndAccept}
						class="w-full py-2.5 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg transition-colors"
					>
						{t('invitations.actions.signInAndAccept')}
					</button>
					<p class="text-center text-xs text-ink-2 mt-2">{t('invitations.signInHelp')}</p>
				{:else}
					{#if actionError}
						<div class="mb-3 text-xs text-state-danger-text motion-fade">{actionError}</div>
					{/if}
					<div class="flex gap-2">
						<button
							onclick={decline}
							disabled={acting}
							class="flex-1 py-2.5 border border-line-2 hover:border-line-2 text-ink-2 hover:text-ink-0 text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
						>
							{t('invitations.actions.decline')}
						</button>
						<button
							onclick={accept}
							disabled={acting}
							class="flex-1 py-2.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-action-warm/40 text-action-on-warm text-sm font-medium rounded-lg transition-colors"
						>
							{t('invitations.actions.accept')}
						</button>
					</div>
					{#if acting}
						<ActivityIndicator label={t('invitations.actions.processing')} size="xs" class="mt-3" />
					{/if}
				{/if}
			</div>
		{/if}
	</div>
</main>
