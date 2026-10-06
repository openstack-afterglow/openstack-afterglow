<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { setAuth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import type { LoginResponse } from '$lib/types/auth';
	import { resolvePostLoginProject } from '$lib/utils/authFlow';
	import { postAuthDestination } from '$lib/utils/mcpConsent';
	import { t } from '$lib/i18n/ns/public-entry';

	let error = $state('');
	let loading = $state(true);

	onMount(async () => {
		const code = $page.url.searchParams.get('code');
		const state = $page.url.searchParams.get('state');

		if (!code || !state) {
			error = t('gitlabCallback.invalidRequest');
			loading = false;
			return;
		}

		// 동일 code 재사용 방지 (HMR/remount/reload 시 onMount 재실행 대응)
		const guardKey = `gitlab-callback-consumed:${code}`;
		if (sessionStorage.getItem(guardKey)) {
			return;
		}
		sessionStorage.setItem(guardKey, '1');
		// URL에서 code/state를 즉시 제거하여 reload 시 재호출되지 않게 함
		try {
			history.replaceState(null, '', '/auth/gitlab/callback');
		} catch {
			/* noop */
		}

		try {
			const data = await api.post<LoginResponse>('/api/v1/auth/gitlab/callback', { code, state });
			const resolution = resolvePostLoginProject(data);
			const scopedProjectId = data.project_id?.trim() || null;

			setAuth({
				token: data.token,
				refreshToken: data.refresh_token ?? null,
				accessExpiresAt: data.expires_at
					? Math.floor(new Date(data.expires_at).getTime() / 1000)
					: null,
				userId: data.user_id,
				username: data.username,
				projectId: resolution.projectId,
				projectName: resolution.projectId === scopedProjectId ? (data.project_name || null) : null,
				roles: data.roles ?? [],
				isSystemAdmin: data.is_system_admin ?? false,
				canWrite: data.can_write,
				federated: true,
			});
			await goto(postAuthDestination(resolution.target));
		} catch (e) {
			error = e instanceof ApiError ? t('gitlabCallback.authError', { status: e.status, message: e.message }) : t('gitlabCallback.authFailed');
			loading = false;
		}
	});
</script>

<main id="main-content" tabindex="-1" class="min-h-screen bg-surface-canvas flex items-center justify-center">
	<div class="w-full max-w-md px-4 text-center">
		{#if loading}
			<div class="motion-fade">
				<ActivityIndicator size="lg" label={t('gitlabCallback.processing')} />
			</div>
		{:else if error}
			<div class="bg-surface-base rounded-xl border border-line-2 p-8 space-y-4 text-left motion-enter">
				<Alert tone="danger">{error}</Alert>
				<a href="/login" class="block w-full text-center bg-surface-sunken hover:bg-surface-selected text-ink-2 font-medium rounded-lg py-2.5 text-sm transition-colors">
					{t('gitlabCallback.backToLogin')}
				</a>
			</div>
		{/if}
	</div>
</main>
