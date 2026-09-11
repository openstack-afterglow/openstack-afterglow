<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth, isLoggedIn } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { InvitationInfo } from '$lib/types/project';

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
			loadError = e instanceof ApiError ? e.message : '초대 정보를 불러오지 못했습니다';
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
			actionError = e instanceof ApiError ? e.message : '수락 중 오류가 발생했습니다';
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
			actionError = e instanceof ApiError ? e.message : '거절 중 오류가 발생했습니다';
		} finally {
			acting = false;
		}
	}

	function loginAndAccept() {
		goto(`/?next=/invitations/${token}`);
	}

	function fmtDate(iso: string): string {
		return new Date(iso).toLocaleDateString('ko-KR', {
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
		<div class="text-center mb-8">
			<div class="text-2xl font-bold text-ink-0 mb-1">Afterglow</div>
			<div class="text-sm text-ink-3">프로젝트 초대</div>
		</div>

		{#if loading}
			<div class="bg-surface-base border border-line rounded-xl p-8 text-center">
				<div class="text-ink-3 text-sm">초대 정보를 불러오는 중...</div>
			</div>
		{:else if loadError}
			<div class="bg-surface-base border border-red-800/50 rounded-xl p-8 text-center">
				<div class="text-red-400 text-sm">{loadError}</div>
			</div>
		{:else if actionDone === 'accepted'}
			<div class="bg-surface-base border border-green-800/50 rounded-xl p-8 text-center">
				<div class="w-12 h-12 bg-green-500/15 rounded-full flex items-center justify-center mx-auto mb-4">
					<svg class="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
					</svg>
				</div>
				<div class="text-ink-0 font-medium mb-1">초대를 수락했습니다</div>
				<div class="text-ink-3 text-sm mb-5">이제 <strong class="text-ink-2">{info?.project_name}</strong> 프로젝트에 접근할 수 있습니다.</div>
				<a href="/select-project" class="inline-block px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg transition-colors">
					프로젝트 선택
				</a>
			</div>
		{:else if actionDone === 'declined'}
			<div class="bg-surface-base border border-line-2 rounded-xl p-8 text-center">
				<div class="text-ink-2 text-sm">초대를 거절했습니다.</div>
			</div>
		{:else if info}
			<div class="bg-surface-base border border-line rounded-xl p-6">
				<!-- 초대 정보 -->
				<div class="mb-6">
					<div class="text-xs text-ink-3 uppercase tracking-wide mb-1">프로젝트</div>
					<div class="text-ink-0 font-semibold text-lg">{info.project_name}</div>
				</div>

				<div class="space-y-3 text-sm mb-6">
					<div class="flex justify-between">
						<span class="text-ink-3">초대한 사람</span>
						<span class="text-ink-1">{info.inviter_name || '알 수 없음'}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-ink-3">초대받은 이메일</span>
						<span class="text-ink-1">{info.invited_email}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-ink-3">만료일</span>
						<span class="text-ink-1">{fmtDate(info.expires_at)}</span>
					</div>
				</div>

				{#if isExpiredOrHandled}
					<div class="text-center py-2 text-sm text-ink-3">
						{#if info.status === 'accepted'}
							이미 수락된 초대입니다.
						{:else if info.status === 'declined'}
							이미 거절된 초대입니다.
						{:else if info.status === 'expired'}
							만료된 초대입니다.
						{:else}
							취소된 초대입니다.
						{/if}
					</div>
				{:else if !$isLoggedIn}
					<button
						onclick={loginAndAccept}
						class="w-full py-2.5 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg transition-colors"
					>
						로그인 후 수락
					</button>
					<p class="text-center text-xs text-ink-3 mt-2">로그인 후 이 초대를 수락하거나 거절할 수 있습니다.</p>
				{:else}
					{#if actionError}
						<div class="mb-3 text-xs text-red-400">{actionError}</div>
					{/if}
					<div class="flex gap-2">
						<button
							onclick={decline}
							disabled={acting}
							class="flex-1 py-2.5 border border-line-2 hover:border-line-2 text-ink-2 hover:text-ink-0 text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
						>
							거절
						</button>
						<button
							onclick={accept}
							disabled={acting}
							class="flex-1 py-2.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-action-warm/40 text-action-on-warm text-sm font-medium rounded-lg transition-colors"
						>
							{acting ? '처리 중...' : '수락'}
						</button>
					</div>
				{/if}
			</div>
		{/if}
	</div>
</main>
