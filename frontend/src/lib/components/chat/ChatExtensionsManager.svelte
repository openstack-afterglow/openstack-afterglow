<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import Button from '$lib/components/ui/Button.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';

	// base: '/api/v1/chat/admin' (관리자 global) 또는 '/api/v1/chat' (사용자 본인)
	// only: 특정 섹션만 렌더('mcp' | 'tools' | 'skills'). 미지정 시 전부.
	let { base, only }: { base: string; only?: 'mcp' | 'tools' | 'skills' } = $props();

	interface McpServer {
		id: number;
		scope: string;
		name: string;
		transport: string;
		url: string | null;
		has_headers?: boolean;
		auth_mode?: 'none' | 'oauth' | 'admin';
		oauth_scopes?: string[];
		has_oauth_client?: boolean;
		has_oauth_client_secret?: boolean;
		load_policy?: 'preloaded' | 'on_demand';
		is_active: boolean;
	}
	interface McpOAuthStatus {
		required: boolean;
		connected: boolean;
		expires_at: string | null;
	}
	interface CustomTool {
		id: number;
		scope: string;
		name: string;
		description: string;
		method: string;
		url: string;
		load_policy?: 'preloaded' | 'on_demand';
		is_active: boolean;
	}
	interface Skill {
		id: number;
		scope: string;
		name: string;
		description: string | null;
		instructions: string;
		is_active: boolean;
	}

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let mcps = $state<McpServer[]>([]);
	let tools = $state<CustomTool[]>([]);
	let skills = $state<Skill[]>([]);
	let loading = $state(true);

	const isAdmin = $derived(base.includes('/admin'));

	let mName = $state('');
	let mTransport = $state('http');
	let mUrl = $state('');
	let mHeaders = $state(''); // admin-only `Header-Name: value` lines → dict
	let mAuthMode = $state<'none' | 'oauth' | 'admin'>('none');
	let mOAuthScopes = $state('');
	let mOAuthClientId = $state('');
	let mOAuthClientSecret = $state('');
	let mLoadPolicy = $state<'preloaded' | 'on_demand'>('on_demand');
	let addingMcp = $state(false);

	let oauthStatus = $state<Record<number, McpOAuthStatus>>({});
	let connectingOAuthId = $state<number | null>(null);

	/** 'Header-Name: value' 형식 줄들을 dict 로 파싱. 빈 줄/':' 없는 줄 무시. */
	function parseHeaders(text: string): Record<string, string> {
		const out: Record<string, string> = {};
		for (const line of text.split('\n')) {
			const idx = line.indexOf(':');
			if (idx <= 0) continue;
			const k = line.slice(0, idx).trim();
			const v = line.slice(idx + 1).trim();
			if (k && v) out[k] = v;
		}
		return out;
	}



	async function connectOAuth(m: McpServer) {
		connectingOAuthId = m.id;
		try {
			const result = await api.post<{ authorization_url: string }>(
				`${base}/mcp-servers/${m.id}/oauth/start`,
				{},
				token,
				projectId
			);
			if (!result.authorization_url) throw new Error('missing authorization URL');
			window.location.assign(result.authorization_url);
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : 'OAuth 연결을 시작하지 못했습니다');
		} finally {
			connectingOAuthId = null;
		}
	}

	async function disconnectOAuth(m: McpServer) {
		if (!(await confirmDialog(`${m.name} OAuth 연결을 해제하시겠습니까?`))) return;
		try {
			await api.delete(`${base}/mcp-servers/${m.id}/oauth`, token, projectId);
			await load();
			toast.success('OAuth 연결을 해제했습니다');
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : 'OAuth 연결 해제 실패');
		}
	}
	let tName = $state('');
	let tDesc = $state('');
	let tMethod = $state('GET');
	let tUrl = $state('');
	let tLoadPolicy = $state<'preloaded' | 'on_demand'>('on_demand');
	let addingTool = $state(false);

	let sName = $state('');
	let sDesc = $state('');
	let sInstructions = $state('');
	let addingSkill = $state(false);

	async function load() {
		if (!token) return;
		loading = true;
		try {
			const [ms, ts, ss] = await Promise.all([
				api.get<McpServer[]>(`${base}/mcp-servers`, token, projectId),
				api.get<CustomTool[]>(`${base}/custom-tools`, token, projectId),
				api.get<Skill[]>(`${base}/skills`, token, projectId)
			]);
			mcps = ms;
			tools = ts;
			skills = ss;
			oauthStatus = isAdmin
				? {}
				: Object.fromEntries(
						await Promise.all(
							ms
								.filter((mcp) => mcp.auth_mode === 'oauth')
								.map(async (mcp) => [
									mcp.id,
									await api.get<McpOAuthStatus>(`${base}/mcp-servers/${mcp.id}/oauth`, token, projectId)
								] as const)
						)
					);
		} catch {
			toast.error('목록을 불러오지 못했습니다');
		} finally {
			loading = false;
		}
	}

	async function addSkill() {
		if (!sName.trim() || !sInstructions.trim()) {
			toast.error('이름과 지침을 입력하세요');
			return;
		}
		addingSkill = true;
		try {
			await api.post(
				`${base}/skills`,
				{ name: sName.trim(), description: sDesc.trim() || null, instructions: sInstructions.trim() },
				token,
				projectId
			);
			sName = '';
			sDesc = '';
			sInstructions = '';
			await load();
			toast.success('스킬이 추가되었습니다');
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : '추가 실패');
		} finally {
			addingSkill = false;
		}
	}

	async function addMcp() {
		if (!mName.trim()) {
			toast.error('이름을 입력하세요');
			return;
		}
		if (!mUrl.trim()) {
			toast.error('원격 MCP 서버는 URL이 필요합니다');
			return;
		}
		addingMcp = true;
		try {
			const headers = parseHeaders(mHeaders);
			const oauthScopes = mOAuthScopes.split(/[\s,]+/).filter(Boolean);
			await api.post(
				`${base}/mcp-servers`,
				{
					name: mName.trim(),
					transport: mTransport,
					url: mUrl.trim(),
					...(isAdmin
						? {
								auth_mode: mAuthMode,
								...(Object.keys(headers).length ? { headers } : {}),
								...(oauthScopes.length ? { oauth_scopes: oauthScopes } : {}),
								...(mOAuthClientId.trim() ? { oauth_client_id: mOAuthClientId.trim() } : {}),
								...(mOAuthClientSecret ? { oauth_client_secret: mOAuthClientSecret } : {}),
								load_policy: mLoadPolicy
							}
						: {})
				},
				token,
				projectId
			);
			mName = '';
			mUrl = '';
			mHeaders = '';
			mAuthMode = 'none';
			mOAuthScopes = '';
			mOAuthClientId = '';
			mOAuthClientSecret = '';
			mLoadPolicy = 'on_demand';
			await load();
			toast.success('MCP 서버가 추가되었습니다');
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : '추가 실패');
		} finally {
			addingMcp = false;
		}
	}

	async function addTool() {
		if (!tName.trim() || !tUrl.trim()) {
			toast.error('이름과 URL을 입력하세요');
			return;
		}
		addingTool = true;
		try {
			await api.post(
				`${base}/custom-tools`,
				{
					name: tName.trim(),
					description: tDesc.trim() || tName.trim(),
					method: tMethod,
					url: tUrl.trim(),
					...(isAdmin ? { load_policy: tLoadPolicy } : {})
				},
				token,
				projectId
			);
			tName = '';
			tDesc = '';
			tUrl = '';
			await load();
			tLoadPolicy = 'on_demand';
			toast.success('커스텀 툴이 추가되었습니다');
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : '추가 실패');
		} finally {
			addingTool = false;
		}
	}

	async function removeItem(
		kind: 'mcp-servers' | 'custom-tools' | 'skills',
		id: number,
		name: string
	) {
		const kindLabel = { 'mcp-servers': 'MCP 서버', 'custom-tools': '커스텀 툴', skills: '스킬' }[kind];
		const ok = await confirmDialog(
			`${kindLabel} "${name}"을(를) 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`,
			{ confirmLabel: '삭제' }
		);
		if (!ok) return;
		try {
			await api.delete(`${base}/${kind}/${id}`, token, projectId);
			await load();
		} catch {
			toast.error(`${kindLabel} "${name}" 삭제 실패`);
		}
	}

	async function toggle(kind: 'mcp-servers' | 'custom-tools' | 'skills', id: number, isActive: boolean) {
		try {
			await api.patch(`${base}/${kind}/${id}`, { is_active: !isActive }, token, projectId);
			await load();
		} catch {
			toast.error('변경 실패');
		}
	}

	async function setLoadPolicy(
		kind: 'mcp-servers' | 'custom-tools',
		id: number,
		loadPolicy: 'preloaded' | 'on_demand'
	) {
		try {
			await api.patch(`${base}/${kind}/${id}`, { load_policy: loadPolicy }, token, projectId);
			await load();
		} catch {
			toast.error('로딩 정책을 변경하지 못했습니다');
		}
	}

	$effect(() => {
		if (token) void load();
	});

	const inputCls =
		'w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] px-3 py-2 text-sm text-[var(--color-ink-1)] focus:outline-none focus:border-[var(--color-accent)]';
	const cardCls = 'rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-raised)]';
	const badge = (active: boolean) =>
		`rounded px-1.5 py-0.5 text-xs ${active ? 'bg-[var(--color-state-success)]/15 text-[var(--color-state-success)]' : 'bg-[var(--color-line)] text-[var(--color-ink-3)]'}`;
</script>

<!-- MCP 서버 -->
{#if !only || only === 'mcp'}
<section class="mb-8">
	<h3 class="mb-1 text-sm font-semibold text-[var(--color-ink-1)]">원격 MCP 서버</h3>
	<p class="mb-3 text-xs text-[var(--color-ink-3)]">HTTPS streamable HTTP MCP 서버를 연결합니다. 스코프: {isAdmin ? '전체 공용' : '내 전용'}</p>
	<div class="{cardCls} mb-4 p-5">
		<div class="grid grid-cols-1 gap-3 md:grid-cols-3">
			<input class={inputCls} placeholder="이름" bind:value={mName} />
			<select class={inputCls} bind:value={mTransport}>
				<option value="http">http (streamable)</option>
			</select>
			<input class={inputCls} placeholder="URL (예: https://mcp.example/mcp)" bind:value={mUrl} />
		</div>
		{#if isAdmin}
			<div class="mt-3">
				<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="mcp-auth-mode">인증 정책</label>
				<select id="mcp-auth-mode" class={inputCls} bind:value={mAuthMode}>
					<option value="none">공개</option>
					<option value="oauth">OAuth</option>
					<option value="admin">관리자 승인 정적 인증</option>
				</select>
			</div>
			<div class="mt-3">
				<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="mcp-load-policy">초기 로딩 정책</label>
				<select id="mcp-load-policy" class={inputCls} bind:value={mLoadPolicy}>
					<option value="on_demand">필요할 때 로드</option>
					<option value="preloaded">응답 시작 시 미리 로드</option>
				</select>
			</div>
			{#if mAuthMode === 'oauth'}
				<div class="mt-3">
					<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="mcp-oauth-scopes">OAuth scopes (선택, 공백 또는 쉼표로 구분)</label>
					<input id="mcp-oauth-scopes" class={inputCls} placeholder="read write" bind:value={mOAuthScopes} />
				</div>
				<div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
					<div>
						<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="mcp-oauth-client-id">OAuth client ID (DCR 미지원 서버만)</label>
						<input id="mcp-oauth-client-id" class={inputCls} autocomplete="off" bind:value={mOAuthClientId} />
					</div>
					<div>
						<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="mcp-oauth-client-secret">OAuth client secret (저장 후 표시되지 않음)</label>
						<input id="mcp-oauth-client-secret" class={inputCls} type="password" autocomplete="new-password" bind:value={mOAuthClientSecret} />
					</div>
				</div>
			{:else if mAuthMode === 'admin'}
				<div class="mt-3">
					<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="mcp-headers">승인된 정적 인증 헤더 — 한 줄에 하나, <code>이름: 값</code></label>
					<textarea id="mcp-headers" class="{inputCls} font-mono" rows="2" placeholder={'Authorization: Bearer <token>\nX-Api-Key: <key>'} bind:value={mHeaders}></textarea>
				</div>
			{/if}
		{:else}
			<p class="mt-3 text-xs text-[var(--color-ink-3)]">공개 MCP는 바로 연결됩니다. OAuth가 감지되면 로그인 연결을 안내합니다. API key·특수 인증 서버는 관리자 승인이 필요합니다.</p>
		{/if}
		<div class="mt-3 flex justify-end">
			<Button onclick={addMcp} disabled={addingMcp}>{addingMcp ? '추가 중…' : '+ MCP 서버 추가'}</Button>
		</div>
	</div>
	{#if loading}
		<div class="{cardCls} h-16 animate-pulse"></div>
	{:else if mcps.length === 0}
		<p class="px-1 text-sm text-[var(--color-ink-3)]">등록된 MCP 서버가 없습니다.</p>
	{:else}
		<div class="space-y-2">
			{#each mcps as m (m.id)}
				<div class={cardCls}>
					<div class="flex items-center justify-between gap-3 px-4 py-3">
						<div class="min-w-0">
							<div class="flex items-center gap-2">
								<span class="truncate text-sm font-medium text-[var(--color-ink-1)]">{m.name}</span>
								<span class={badge(m.is_active)}>{m.is_active ? '활성' : '비활성'}</span>
								<span class="text-xs text-[var(--color-ink-3)]">{m.transport}</span>
								{#if m.has_headers}<span class="text-xs text-[var(--color-ink-3)]" title="공용 인증 헤더 설정됨">🔒</span>{/if}
								{#if m.auth_mode === 'oauth'}
									<span title="사용자별 OAuth 연결 필요"><Pill tone="neutral" size="xs">OAuth</Pill></span>
								{/if}
							</div>
							{#if m.url}<div class="mt-0.5 truncate text-xs text-[var(--color-ink-3)]">{m.url}</div>{/if}
						</div>
						<div class="flex shrink-0 items-center gap-3 text-xs">
							{#if !isAdmin && m.auth_mode === 'oauth'}
								{#if oauthStatus[m.id]?.connected}
									<button class="text-[var(--color-state-success)] hover:opacity-80" onclick={() => disconnectOAuth(m)}>OAuth 연결됨</button>
								{:else}
									<button class="text-[var(--color-accent)] hover:opacity-80" disabled={connectingOAuthId === m.id} onclick={() => connectOAuth(m)}>
										{connectingOAuthId === m.id ? '연결 준비 중…' : `${m.name} OAuth 연결`}
									</button>
								{/if}
							{/if}
							{#if isAdmin}
								<select
									class="rounded border border-[var(--color-line)] bg-[var(--color-surface-sunken)] px-1 py-0.5 text-xs text-[var(--color-ink-2)]"
									aria-label={`${m.name} 로딩 정책`}
									value={m.load_policy ?? 'on_demand'}
									onchange={(event) =>
										void setLoadPolicy(
											'mcp-servers',
											m.id,
											(event.currentTarget as HTMLSelectElement).value as 'preloaded' | 'on_demand'
										)}
								>
									<option value="on_demand">필요 시</option>
									<option value="preloaded">미리 로드</option>
								</select>
							{/if}
							<button class="text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)]" onclick={() => toggle('mcp-servers', m.id, m.is_active)}>{m.is_active ? '비활성화' : '활성화'}</button>
							<button class="text-[var(--color-state-danger)] hover:opacity-80" onclick={() => removeItem('mcp-servers', m.id, m.name)}>삭제</button>
						</div>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</section>
{/if}

<!-- 커스텀 HTTP 툴 -->
{#if !only || only === 'tools'}
<section>
	<h3 class="mb-1 text-sm font-semibold text-[var(--color-ink-1)]">커스텀 HTTP 툴</h3>
	<p class="mb-3 text-xs text-[var(--color-ink-3)]">LLM 이 호출할 수 있는 외부 HTTP 엔드포인트. 스코프: {base.includes('/admin') ? '전체 공용' : '내 전용'}</p>
	<div class="{cardCls} mb-4 p-5">
		<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
			<input class={inputCls} placeholder="툴 이름 (영숫자/_)" bind:value={tName} />
			<input class={inputCls} placeholder="설명" bind:value={tDesc} />
			<select class={inputCls} bind:value={tMethod}>
				<option value="GET">GET</option>
				<option value="POST">POST</option>
			</select>
			<input class={inputCls} placeholder="URL" bind:value={tUrl} />
		</div>
		{#if isAdmin}
			<div class="mt-3">
				<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="tool-load-policy">초기 로딩 정책</label>
				<select id="tool-load-policy" class={inputCls} bind:value={tLoadPolicy}>
					<option value="on_demand">필요할 때 로드</option>
					<option value="preloaded">응답 시작 시 미리 로드</option>
				</select>
			</div>
		{/if}
		<div class="mt-3 flex justify-end">
			<Button onclick={addTool} disabled={addingTool}>{addingTool ? '추가 중…' : '+ 커스텀 툴 추가'}</Button>
		</div>
	</div>
	{#if loading}
		<div class="{cardCls} h-16 animate-pulse"></div>
	{:else if tools.length === 0}
		<p class="px-1 text-sm text-[var(--color-ink-3)]">등록된 커스텀 툴이 없습니다.</p>
	{:else}
		<div class="space-y-2">
			{#each tools as t (t.id)}
				<div class="{cardCls} flex items-center justify-between gap-3 px-4 py-3">
					<div class="min-w-0">
						<div class="flex items-center gap-2">
							<span class="truncate text-sm font-medium text-[var(--color-ink-1)]">{t.name}</span>
							<span class={badge(t.is_active)}>{t.is_active ? '활성' : '비활성'}</span>
							<span class="text-xs text-[var(--color-ink-3)]">{t.method}</span>
						</div>
						<div class="mt-0.5 truncate text-xs text-[var(--color-ink-3)]">{t.description} · {t.url}</div>
					</div>
					<div class="flex shrink-0 items-center gap-3 text-xs">
						{#if isAdmin}
							<select
								class="rounded border border-[var(--color-line)] bg-[var(--color-surface-sunken)] px-1 py-0.5 text-xs text-[var(--color-ink-2)]"
								aria-label={`${t.name} 로딩 정책`}
								value={t.load_policy ?? 'on_demand'}
								onchange={(event) =>
									void setLoadPolicy(
										'custom-tools',
										t.id,
										(event.currentTarget as HTMLSelectElement).value as 'preloaded' | 'on_demand'
									)}
							>
								<option value="on_demand">필요 시</option>
								<option value="preloaded">미리 로드</option>
							</select>
						{/if}
						<button class="text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)]" onclick={() => toggle('custom-tools', t.id, t.is_active)}>{t.is_active ? '비활성화' : '활성화'}</button>
						<button class="text-[var(--color-state-danger)] hover:opacity-80" onclick={() => removeItem('custom-tools', t.id, t.name)}>삭제</button>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</section>
{/if}

<!-- 스킬 (선택 시 채팅 지침으로 주입) -->
{#if !only || only === 'skills'}
<section class="mt-8">
	<h3 class="mb-1 text-sm font-semibold text-[var(--color-ink-1)]">스킬</h3>
	<p class="mb-3 text-xs text-[var(--color-ink-3)]">채팅에서 선택하면 지침(SKILL.md)이 대화에 주입됩니다(모든 모델). 스코프: {base.includes('/admin') ? '전체 공용' : '내 전용'}</p>
	<div class="{cardCls} mb-4 p-5">
		<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
			<input class={inputCls} placeholder="스킬 이름" bind:value={sName} />
			<input class={inputCls} placeholder="설명 (선택)" bind:value={sDesc} />
		</div>
		<div class="mt-3">
			<label class="mb-1 block text-xs text-[var(--color-ink-3)]" for="skill-instructions">
				지침 (instructions) — 선택 시 system 프리앰블에 주입됩니다. 암호화 저장.
			</label>
			<textarea
				id="skill-instructions"
				class={inputCls}
				rows="5"
				placeholder="예: 당신은 코드 리뷰 전문가입니다. 항상 보안·성능·가독성 순으로 검토하고…"
				bind:value={sInstructions}
			></textarea>
		</div>
		<div class="mt-3 flex justify-end">
			<Button onclick={addSkill} disabled={addingSkill}>{addingSkill ? '추가 중…' : '+ 스킬 추가'}</Button>
		</div>
	</div>
	{#if loading}
		<div class="{cardCls} h-16 animate-pulse"></div>
	{:else if skills.length === 0}
		<p class="px-1 text-sm text-[var(--color-ink-3)]">등록된 스킬이 없습니다.</p>
	{:else}
		<div class="space-y-2">
			{#each skills as s (s.id)}
				<div class="{cardCls} flex items-center justify-between gap-3 px-4 py-3">
					<div class="min-w-0">
						<div class="flex items-center gap-2">
							<span class="truncate text-sm font-medium text-[var(--color-ink-1)]">{s.name}</span>
							<span class={badge(s.is_active)}>{s.is_active ? '활성' : '비활성'}</span>
						</div>
						{#if s.description}<div class="mt-0.5 truncate text-xs text-[var(--color-ink-3)]">{s.description}</div>{/if}
					</div>
					<div class="flex shrink-0 items-center gap-3 text-xs">
						<button class="text-[var(--color-ink-2)] hover:text-[var(--color-ink-0)]" onclick={() => toggle('skills', s.id, s.is_active)}>{s.is_active ? '비활성화' : '활성화'}</button>
						<button class="text-[var(--color-state-danger)] hover:opacity-80" onclick={() => removeItem('skills', s.id, s.name)}>삭제</button>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</section>
{/if}
