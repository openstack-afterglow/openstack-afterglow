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
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let ready = $state(false);
	let code = $state('');
	let deciding = $state(false);
	let error = $state('');
	let outcome = $state<'approved' | 'denied' | null>(null);

	function errorMessage(value: unknown): string {
		return value instanceof ApiError ? value.message : 'Claude Code 연결 요청을 처리하지 못했습니다.';
	}

	async function decide(action: 'approve' | 'deny') {
		if (!token || !projectId || deciding) return;
		if (!storeClaudeGatewayUserCode(code)) {
			error = 'Claude Code에 표시된 8자리 연결 코드를 확인하세요.';
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
			error = '연결 URL의 Claude Code 인증 코드가 유효하지 않습니다. 코드를 직접 입력할 수 있습니다.';
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
	<title>Claude Code 연결 승인 | Afterglow</title>
	<meta name="referrer" content="no-referrer" />
</svelte:head>

<main class="authorization-page">
	<Card surface="raised" padding="lg" class="authorization-card">
		<header>
			<p class="eyebrow">Lumen Claude Gateway</p>
			<h1>Claude Code 연결 승인</h1>
			<p>Claude Code에 표시된 코드를 확인한 뒤 현재 Afterglow 프로젝트에 연결하세요.</p>
		</header>

		{#if outcome === 'approved'}
			<Alert tone="success" title="Claude Code 연결을 승인했습니다.">
				{#snippet children()}Claude Code로 돌아가세요. 24시간 후에는 다시 연결해야 합니다.{/snippet}
			</Alert>
			<div class="actions"><Button onclick={leave}>채팅 설정으로 이동</Button></div>
		{:else if outcome === 'denied'}
			<Alert tone="info" title="Claude Code 연결을 거절했습니다.">
				{#snippet children()}이 인증 요청으로는 Lumen API 키가 발급되지 않습니다.{/snippet}
			</Alert>
			<div class="actions"><Button variant="secondary" onclick={leave}>채팅 설정으로 이동</Button></div>
		{:else}
			{#if error}<Alert tone="danger" title="연결 요청을 처리할 수 없습니다.">{#snippet children()}{error}{/snippet}</Alert>{/if}

			<section class="details" aria-labelledby="gateway-code-heading">
				<div class="scope-summary">
					<div>
						<span>권한 범위</span>
						<strong id="gateway-code-heading">모델 조회 및 Claude Code 추론</strong>
					</div>
					<div class="scopes" aria-label="발급 권한">
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
					<Field label="Claude Code 연결 코드" for="gateway-code" help="예: ABCD-2345">
						<TextInput
							id="gateway-code"
							ariaLabel="Claude Code 연결 코드"
							maxlength={9}
							placeholder="ABCD-2345"
							bind:value={code}
						/>
					</Field>
					<div class="actions">
						<Button variant="danger-outline" type="button" onclick={() => decide('deny')} disabled={deciding || !code.trim()}>거절</Button>
						<Button type="submit" disabled={deciding || !code.trim()}>{deciding ? '처리 중…' : '연결 승인'}</Button>
					</div>
				</form>
			</section>

			<Alert tone="warning" title="본인이 시작한 요청만 승인하세요.">
				{#snippet children()}승인하면 현재 사용자와 프로젝트에 묶인 24시간짜리 Lumen 자격 증명이 한 번만 발급됩니다. 비밀번호나 기존 API 키는 Claude Code에 전달되지 않습니다.{/snippet}
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
	@media (min-width: 640px) {
		.scope-summary { align-items: center; grid-template-columns: 1fr auto; }
		.actions { flex-direction: row; justify-content: flex-end; }
	}
</style>
