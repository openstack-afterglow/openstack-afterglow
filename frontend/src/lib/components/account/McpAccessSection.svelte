<script lang="ts">
	import { untrack } from 'svelte';
	import { api, ApiError, getBaseUrl } from '$lib/api/client';
	import { siteConfig } from '$lib/config/site';
	import { auth } from '$lib/stores/auth';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';

	interface McpAccessRecord {
		id: string;
		grant_id: string;
		name: string;
		source: string;
		access_level: string;
		status: string;
		visible_prefix: string | null;
		issued_at: string | null;
		expires_at: string;
		last_used_at: string | null;
		revoked_at: string | null;
		is_lumen_default: boolean;
	}

	interface IssuedToken extends McpAccessRecord {
		token: string;
	}

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const mcpEnabled = $derived($siteConfig.services.mcp);
	const mcpUrl = $derived($siteConfig.mcp_url || `${getBaseUrl().replace(/\/+$/, '')}/api/v1/mcp`);

	let tokens = $state<McpAccessRecord[]>([]);
	let oauthGrants = $state<McpAccessRecord[]>([]);
	let loading = $state(false);
	let loadError = $state('');
	let actionError = $state('');
	let creating = $state(false);
	let mutatingId = $state<string | null>(null);
	let tokenName = $state('Lumen');
	let accessLevel = $state<'read' | 'manage'>('read');
	let expiresAt = $state('');
	let issuedToken = $state<string | null>(null);
	let showIssuedToken = $state(false);
	let copied = $state(false);

	function errorMessage(error: unknown, fallback: string) {
		return error instanceof ApiError ? error.message : fallback;
	}

	function reset() {
		tokens = [];
		oauthGrants = [];
		loadError = '';
		actionError = '';
	}

	async function loadAccess() {
		if (!mcpEnabled || !token || !projectId) return;
		loading = true;
		try {
			const [personalTokens, grants] = await Promise.all([
				api.get<McpAccessRecord[]>('/api/v1/auth/mcp-tokens', token, projectId),
				api.get<McpAccessRecord[]>('/api/v1/auth/mcp-oauth/grants', token, projectId),
			]);
			tokens = personalTokens;
			oauthGrants = grants;
			loadError = '';
		} catch (error) {
			loadError = errorMessage(error, 'MCP 접근 권한을 불러오지 못했습니다.');
		} finally {
			loading = false;
		}
	}

	async function createToken() {
		if (!token || !projectId || !tokenName.trim()) return;
		creating = true;
		actionError = '';
		try {
			const issued = await api.post<IssuedToken>(
				'/api/v1/auth/mcp-tokens',
				{
					name: tokenName.trim(),
					access_level: accessLevel,
					expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
				},
				token,
				projectId,
			);
			issuedToken = issued.token;
			showIssuedToken = true;
			tokenName = 'Lumen';
			expiresAt = '';
			await loadAccess();
		} catch (error) {
			actionError = errorMessage(error, 'MCP 토큰을 만들지 못했습니다.');
		} finally {
			creating = false;
		}
	}

	function dismissIssuedToken() {
		issuedToken = null;
		showIssuedToken = false;
		copied = false;
	}

	async function copyIssuedToken() {
		if (!issuedToken) return;
		try {
			await navigator.clipboard.writeText(issuedToken);
			copied = true;
		} catch {
			actionError = '클립보드에 복사하지 못했습니다. 직접 복사하세요.';
		}
	}

	async function selectLumenDefault(record: McpAccessRecord) {
		if (!token || !projectId) return;
		mutatingId = record.id;
		actionError = '';
		try {
			await api.put(`/api/v1/auth/mcp-tokens/${encodeURIComponent(record.id)}/lumen-default`, {}, token, projectId);
			await loadAccess();
		} catch (error) {
			actionError = errorMessage(error, 'Lumen 기본 토큰을 변경하지 못했습니다.');
		} finally {
			mutatingId = null;
		}
	}

	async function clearLumenDefault() {
		if (!token || !projectId) return;
		mutatingId = 'lumen-default';
		actionError = '';
		try {
			await api.delete('/api/v1/auth/mcp-tokens/lumen-default', token, projectId);
			await loadAccess();
		} catch (error) {
			actionError = errorMessage(error, 'Lumen 기본 토큰을 해제하지 못했습니다.');
		} finally {
			mutatingId = null;
		}
	}

	async function revokeToken(record: McpAccessRecord) {
		if (!token || !projectId) return;
		if (!(await confirmDialog(`MCP 토큰 “${record.name}”을 폐기하시겠습니까? 연결된 Lumen 접근도 즉시 해제됩니다.`))) return;
		mutatingId = record.id;
		actionError = '';
		try {
			await api.delete(`/api/v1/auth/mcp-tokens/${encodeURIComponent(record.id)}`, token, projectId);
			await loadAccess();
		} catch (error) {
			actionError = errorMessage(error, 'MCP 토큰을 폐기하지 못했습니다.');
		} finally {
			mutatingId = null;
		}
	}

	async function revokeOAuthGrant(record: McpAccessRecord) {
		if (!token || !projectId) return;
		if (!(await confirmDialog(`“${record.name}”의 OAuth 권한을 철회하시겠습니까?`))) return;
		mutatingId = record.id;
		actionError = '';
		try {
			await api.delete(`/api/v1/auth/mcp-oauth/grants/${encodeURIComponent(record.grant_id)}`, token, projectId);
			await loadAccess();
		} catch (error) {
			actionError = errorMessage(error, 'OAuth 권한을 철회하지 못했습니다.');
		} finally {
			mutatingId = null;
		}
	}

	function formatDate(value: string | null) {
		if (!value) return '—';
		return new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
	}

	$effect(() => {
		if (!mcpEnabled || !token || !projectId) {
			reset();
			return;
		}
		untrack(() => void loadAccess());
	});
</script>

{#if mcpEnabled}
	<Card class="mcp-access" surface="raised" padding="lg">
		<div class="section-heading">
			<div>
				<h2>외부 AI 접근</h2>
				<p>개인 토큰과 OAuth 연결은 현재 프로젝트에만 권한을 갖습니다.</p>
			</div>
			<Button variant="ghost" size="sm" onclick={loadAccess} disabled={loading}>
				{loading ? '불러오는 중…' : '새로고침'}
			</Button>
		</div>

		<p class="endpoint"><span>MCP URL</span><code>{mcpUrl}</code></p>

		<Alert tone="warning" title="토큰은 한 번만 표시됩니다.">
			{#snippet children()}토큰을 만든 직후 안전한 비밀 저장소에 복사하세요. 이후에는 접두사와 상태만 확인할 수 있습니다.{/snippet}
		</Alert>

		{#if loadError}
			<Alert tone="danger" title="조회 실패">
				{#snippet children()}{loadError}{/snippet}
			</Alert>
		{/if}
		{#if actionError}
			<Alert tone="danger" title="작업 실패">
				{#snippet children()}{actionError}{/snippet}
			</Alert>
		{/if}

		<form class="token-form" onsubmit={(event) => { event.preventDefault(); void createToken(); }}>
			<Field label="이름" for="mcp-token-name" required>
				{#snippet children()}
					<input id="mcp-token-name" class="control" bind:value={tokenName} maxlength="100" autocomplete="off" />
				{/snippet}
			</Field>
			<Field label="권한" for="mcp-token-access" help="읽기는 조회 전용입니다. 관리는 변경 작업 승인에 사용합니다.">
				{#snippet children()}
					<select id="mcp-token-access" class="control" bind:value={accessLevel}>
						<option value="read">읽기</option>
						<option value="manage">관리</option>
					</select>
				{/snippet}
			</Field>
			<Field label="만료 시각" for="mcp-token-expiry" help="비워두면 서버 정책의 기본 만료 시각을 사용합니다.">
				{#snippet children()}
					<input id="mcp-token-expiry" class="control" type="datetime-local" bind:value={expiresAt} />
				{/snippet}
			</Field>
			<div class="token-submit"><Button type="submit" disabled={creating || !tokenName.trim()}>{creating ? '만드는 중…' : '토큰 만들기'}</Button></div>
		</form>

		<section aria-labelledby="mcp-personal-tokens-heading">
			<div class="subheading">
				<h3 id="mcp-personal-tokens-heading">개인 토큰</h3>
				<span>{tokens.length}개</span>
			</div>
			{#if loading}
				<p class="empty">접근 권한을 불러오는 중입니다.</p>
			{:else if tokens.length === 0}
				<p class="empty">발급된 개인 토큰이 없습니다.</p>
			{:else}
				<div class="records">
					{#each tokens as record (record.id)}
						<div class="record">
							<div class="record-main">
								<div class="record-title"><strong>{record.name}</strong><StatusChip status={record.status} /></div>
								<p>{record.visible_prefix ?? '접두사 없음'} · {record.access_level === 'manage' ? '관리' : '읽기'} · 마지막 사용 {formatDate(record.last_used_at)} · 만료 {formatDate(record.expires_at)}</p>
								{#if record.is_lumen_default}<p class="default-note">Lumen 기본 토큰</p>{/if}
							</div>
							<div class="record-actions">
								{#if record.is_lumen_default}
									<Button variant="subtle" size="xs" onclick={clearLumenDefault} disabled={mutatingId !== null}>Lumen 해제</Button>
								{:else}
									<Button variant="outline" size="xs" onclick={() => selectLumenDefault(record)} disabled={mutatingId !== null || record.status !== 'active'}>Lumen 기본</Button>
								{/if}
								<Button variant="danger-outline" size="xs" onclick={() => revokeToken(record)} disabled={mutatingId !== null}>폐기</Button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</section>

		<section aria-labelledby="mcp-oauth-grants-heading">
			<div class="subheading"><h3 id="mcp-oauth-grants-heading">OAuth 연결</h3><span>{oauthGrants.length}개</span></div>
			{#if !loading && oauthGrants.length === 0}
				<p class="empty">승인된 외부 MCP 클라이언트가 없습니다.</p>
			{:else if oauthGrants.length > 0}
				<div class="records">
					{#each oauthGrants as record (record.id)}
						<div class="record">
							<div class="record-main"><div class="record-title"><strong>{record.name}</strong><StatusChip status={record.status} /></div><p>{record.access_level === 'manage' ? '관리' : '읽기'} · 만료 {formatDate(record.expires_at)}</p></div>
							<Button variant="danger-outline" size="xs" onclick={() => revokeOAuthGrant(record)} disabled={mutatingId !== null}>권한 철회</Button>
						</div>
					{/each}
				</div>
			{/if}
		</section>
	</Card>

	<Modal bind:open={showIssuedToken} onClose={dismissIssuedToken} ariaLabel="새 MCP 토큰">
		<Card surface="modal" padding="lg" class="issued-token-dialog">
			<h2>새 MCP 토큰</h2>
			<p>이 값은 지금만 표시됩니다. 복사 후 이 창을 닫으면 메모리에서도 제거됩니다.</p>
			{#if issuedToken}<pre>{issuedToken}</pre>{/if}
			<div class="dialog-actions"><Button variant="outline" onclick={copyIssuedToken}>{copied ? '복사됨' : '복사'}</Button><Button onclick={dismissIssuedToken}>완료</Button></div>
		</Card>
	</Modal>
{/if}

<style>
	:global(.mcp-access) { display: grid; gap: 1rem; }
	.section-heading, .subheading, .record, .record-title, .record-actions, .dialog-actions { display: flex; align-items: center; }
	.section-heading, .subheading, .record { justify-content: space-between; gap: 1rem; }
	.section-heading h2, .subheading h3, :global(.issued-token-dialog h2) { margin: 0; color: var(--color-ink-0); }
	.section-heading h2 { font-size: 1rem; }
	.section-heading p, .record p, .empty, :global(.issued-token-dialog p) { margin: 0.25rem 0 0; color: var(--color-ink-2); font-size: 0.8125rem; line-height: 1.5; }
	.endpoint { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.5rem; margin: 0; color: var(--color-ink-2); font-size: 0.75rem; }
	.endpoint span { font-weight: 600; }
	.endpoint code { color: var(--color-ink-1); overflow-wrap: anywhere; }
	.token-form { display: grid; grid-template-columns: minmax(0, 1fr) minmax(9rem, 0.7fr) minmax(10rem, 0.8fr) auto; gap: 0.75rem; align-items: end; padding: 1rem; border: 1px solid var(--color-line); border-radius: 0.75rem; background: var(--color-surface-sunken); }
	.control { box-sizing: border-box; width: 100%; min-height: 2.5rem; padding: 0.5rem 0.625rem; border: 1px solid var(--color-line-2); border-radius: 0.5rem; background: var(--color-surface-base); color: var(--color-ink-0); font: inherit; }
	.control:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }
	.token-submit { padding-bottom: 0.0625rem; }
	.subheading { margin-bottom: 0.5rem; }
	.subheading h3 { font-size: 0.875rem; }
	.subheading span { color: var(--color-ink-2); font-size: 0.75rem; }
	.records { display: grid; gap: 0.5rem; }
	.record { padding: 0.75rem; border: 1px solid var(--color-line); border-radius: 0.625rem; background: var(--color-surface-base); }
	.record-main { min-width: 0; }
	.record-title { gap: 0.5rem; flex-wrap: wrap; }
	.record-title strong { color: var(--color-ink-0); font-size: 0.875rem; }
	.record-actions { flex-wrap: wrap; justify-content: flex-end; }
	.default-note { color: var(--color-state-info) !important; }
	:global(.issued-token-dialog) { width: min(32rem, calc(100vw - 2rem)); display: grid; gap: 0.875rem; }
	:global(.issued-token-dialog pre) { margin: 0; max-height: 12rem; overflow: auto; padding: 0.75rem; border: 1px solid var(--color-line); border-radius: 0.5rem; background: var(--color-surface-sunken); color: var(--color-ink-0); font-size: 0.75rem; white-space: pre-wrap; word-break: break-all; }
	.dialog-actions { justify-content: flex-end; gap: 0.5rem; }
	@media (max-width: 56rem) { .token-form { grid-template-columns: 1fr 1fr; } .token-submit { grid-column: 1 / -1; } }
	@media (max-width: 38rem) { .token-form { grid-template-columns: 1fr; } .record { align-items: flex-start; flex-direction: column; } .record-actions { justify-content: flex-start; } }
</style>
