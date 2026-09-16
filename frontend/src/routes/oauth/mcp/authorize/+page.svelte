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
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';

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
		return new Intl.DateTimeFormat('ko-KR', { dateStyle: 'long', timeStyle: 'short' }).format(new Date(value));
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
			error = message(errorValue, 'OAuth 승인 요청을 불러오지 못했습니다.');
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
			error = message(errorValue, decision === 'approve' ? '권한을 승인하지 못했습니다.' : '권한을 거절하지 못했습니다.');
		} finally {
			deciding = false;
		}
	}

	onMount(() => {
		const queryTicket = $page.url.searchParams.get('ticket');
		if (queryTicket) {
			if (!storeMcpConsentTicket(queryTicket)) {
				clearMcpConsentTicket();
				error = 'OAuth 승인 요청이 유효하지 않습니다.';
			}
			try {
				history.replaceState(null, '', '/oauth/mcp/authorize');
			} catch {
				// URL cleanup is defense in depth; the backend still validates the ticket.
			}
		}
		ticket.value = pendingMcpConsentTicket();
		ready = true;
		if (!ticket.value && !error) error = 'OAuth 승인 요청이 없거나 만료되었습니다.';
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
	<Card surface="raised" padding="lg" class="consent-card">
		<header>
			<p class="eyebrow">Afterglow OAuth</p>
			<h1>외부 AI 접근 승인</h1>
			<p>이 요청은 현재 선택한 프로젝트에만 적용됩니다. 외부 클라이언트의 이름과 권한을 확인하세요.</p>
		</header>

		{#if error}
			<Alert tone="danger" title="승인 요청을 처리할 수 없습니다.">
				{#snippet children()}{error}{/snippet}
			</Alert>
		{:else if loading}
			<p class="loading">승인 요청을 확인하는 중입니다.</p>
		{:else if consent}
			{@const requestsManage = consent.scopes.includes('mcp:write')}
			<section aria-labelledby="consent-client-heading" class="details">
				<div><span>클라이언트</span><strong id="consent-client-heading">{consent.client_name}</strong></div>
				<div><span>Client ID</span><code>{consent.client_id}</code></div>
				<div><span>돌아갈 주소</span><code>{consent.redirect_uri}</code></div>
				<div><span>권한</span><div class="scopes">{#each consent.scopes as scope}<StatusChip status={scope === 'mcp:write' ? 'manage' : 'read'} />{/each}</div></div>
				<div><span>서버가 정한 만료</span><strong>{formatDeadline(consent.grant_deadline)}</strong></div>
			</section>
			<Alert tone={requestsManage ? 'warning' : 'info'} title={requestsManage ? '관리 권한 요청' : '읽기 권한 요청'}>
				{#snippet children()}{requestsManage ? '이 클라이언트는 리소스를 변경할 수 있습니다. 승인 전 요청 주체를 확인하세요.' : '이 클라이언트는 현재 프로젝트의 안전한 조회 도구만 사용할 수 있습니다.'}{/snippet}
			</Alert>
			<div class="actions">
				<Button variant="danger-outline" onclick={() => decide('deny')} disabled={deciding}>거절</Button>
				<Button onclick={() => decide('approve')} disabled={deciding}>{deciding ? '처리 중…' : requestsManage ? '관리 권한 허용' : '읽기 권한 허용'}</Button>
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
	.loading { margin: 0; color: var(--color-ink-2); }
	.details { display: grid; gap: 0.75rem; padding: 1rem; border: 1px solid var(--color-line); border-radius: 0.75rem; background: var(--color-surface-sunken); }
	.details > div { display: grid; gap: 0.25rem; }
	.details span { color: var(--color-ink-2); font-size: 0.75rem; }
	.details strong, .details code { color: var(--color-ink-0); font-size: 0.875rem; overflow-wrap: anywhere; }
	.scopes { display: flex; gap: 0.5rem; flex-wrap: wrap; }
	.actions { display: flex; justify-content: flex-end; gap: 0.5rem; }
</style>
