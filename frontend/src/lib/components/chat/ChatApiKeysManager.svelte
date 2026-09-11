<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import { formatCredit, isCreditInput } from '$lib/api/chatQuotas';
	import type { ApiKey } from '$lib/api/chatUsage';
	import type { ChatUsage } from '$lib/api/chatTree';

	let { usage = null }: { usage?: ChatUsage | null } = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let keys = $state<ApiKey[]>([]);
	let loading = $state(true);
	let name = $state('');
	let creating = $state(false);
	// 발급 직후 평문 키(1회만). 모달로 표시 후 목록 새로고침.
	let issued = $state<{ key: string; key_prefix: string } | null>(null);
	let editingId = $state<number | null>(null);
	let editing = $state<'name' | 'limits' | null>(null);
	let nameDraft = $state('');
	let monthlyDraft = $state('');
	let weeklyDraft = $state('');
	let nameError = $state('');
	let monthlyError = $state('');
	let weeklyError = $state('');
	let savingEdit = $state(false);

	interface CompatDiscovery {
		endpoints: {
			openai: { sdk_base_url: string };
			anthropic: { sdk_base_url: string };
		};
	}
	let sdkBases = $state<{ openai: string; anthropic: string } | null>(null);
	let guideLoading = $state(false);
	let guideError = $state('');
	let guideGeneration = 0;

	function sdkBaseUrl(value: unknown): string {
		if (typeof value !== 'string' || !value.trim()) throw new Error('Missing SDK URL');
		const url = new URL(value);
		if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
			throw new Error('Invalid SDK URL');
		}
		return value;
	}

	async function loadConnectionGuide(requestToken = token, requestProjectId = projectId) {
		const generation = ++guideGeneration;
		sdkBases = null;
		guideError = '';
		guideLoading = Boolean(requestToken);
		if (!requestToken) return;
		try {
			const discovery = await api.get<CompatDiscovery>('/api/v1/chat/compat', requestToken, requestProjectId);
			if (generation !== guideGeneration) return;
			sdkBases = {
				openai: sdkBaseUrl(discovery.endpoints?.openai?.sdk_base_url),
				anthropic: sdkBaseUrl(discovery.endpoints?.anthropic?.sdk_base_url)
			};
		} catch {
			if (generation !== guideGeneration) return;
			guideError = 'Lumen 연결 정보를 불러오지 못했습니다. 서비스 연결 및 공개 API 주소 설정을 확인해 주세요.';
		} finally {
			if (generation === guideGeneration) guideLoading = false;
		}
	}

	const openaiExample = $derived(sdkBases ? `import os

from openai import OpenAI

with OpenAI(
    base_url=${JSON.stringify(sdkBases.openai)},
    api_key=os.environ["LUMEN_API_KEY"],
) as client:
    response = client.chat.completions.create(
        model=os.environ["LUMEN_MODEL"],
        extra_body=(
            {"provider": os.environ["LUMEN_PROVIDER"]}
            if os.environ.get("LUMEN_PROVIDER")
            else None
        ),
        messages=[
            {"role": "user", "content": "Write a short poem about the ocean."}
        ],
    )
    print(response.choices[0].message.content)` : '');

	const anthropicExample = $derived(sdkBases ? `import os

from anthropic import Anthropic

with Anthropic(
    base_url=${JSON.stringify(sdkBases.anthropic)},
    api_key=os.environ["LUMEN_API_KEY"],
) as client:
    response = client.messages.create(
        model=os.environ["LUMEN_MODEL"],
        max_tokens=1024,
        extra_body=(
            {"provider": os.environ["LUMEN_PROVIDER"]}
            if os.environ.get("LUMEN_PROVIDER")
            else None
        ),
        messages=[
            {"role": "user", "content": "Write a short poem about the ocean."}
        ],
    )
    for block in response.content:
        if block.type == "text":
            print(block.text)` : '');

	async function load() {
		if (!token) return;
		loading = true;
		try {
			keys = await api.get<ApiKey[]>('/api/v1/chat/api-keys', token, projectId);
		} catch {
			toast.error('API 키 목록을 불러오지 못했습니다');
		} finally {
			loading = false;
		}
	}

	async function create() {
		creating = true;
		try {
			const res = await api.post<{ key: string; key_prefix: string }>(
				'/api/v1/chat/api-keys',
				{ name: name.trim() },
				token,
				projectId
			);
			issued = { key: res.key, key_prefix: res.key_prefix };
			name = '';
			await load();
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : '발급 실패');
		} finally {
			creating = false;
		}
	}

	async function revoke(id: number) {
		if (!(await confirmDialog('이 API 키를 폐기하시겠습니까? 이 키를 쓰는 연동은 즉시 중단됩니다.'))) return;
		try {
			await api.delete(`/api/v1/chat/api-keys/${id}`, token, projectId);
			await load();
		} catch {
			toast.error('폐기 실패');
		}
	}

	function stopEditing() {
		editingId = null;
		editing = null;
		nameDraft = '';
		monthlyDraft = '';
		weeklyDraft = '';
		nameError = '';
		monthlyError = '';
		weeklyError = '';
	}

	function editName(key: ApiKey) {
		stopEditing();
		editingId = key.id;
		editing = 'name';
		nameDraft = key.name;
	}

	function editLimits(key: ApiKey) {
		stopEditing();
		editingId = key.id;
		editing = 'limits';
		monthlyDraft = key.owner_monthly_credit_limit ?? '';
		weeklyDraft = key.owner_weekly_credit_limit ?? '';
	}

	interface Ceiling {
		limit: number;
		label: string;
	}

	/** Lumen `_owner_ceilings`와 같은 규칙: 후보 중 가장 낮은 양수 한도가 상한이고, 없으면 무제한. */
	function tightestCeiling(candidates: Array<[string | null, string]>): Ceiling | null {
		let tightest: Ceiling | null = null;
		for (const [raw, label] of candidates) {
			if (raw === null) continue;
			const limit = Number(raw);
			if (!Number.isFinite(limit) || limit <= 0) continue;
			if (!tightest || limit < tightest.limit) tightest = { limit, label };
		}
		return tightest;
	}

	function limitError(value: string, ceiling: Ceiling | null): string {
		if (!value) return '';
		if (!isCreditInput(value)) return '0보다 큰 숫자(소수 8자리 이하)를 입력하세요';
		if (ceiling && Number(value) > ceiling.limit) {
			return `${ceiling.label}(${formatCredit(String(ceiling.limit))})를 초과할 수 없습니다`;
		}
		return '';
	}

	async function saveName(key: ApiKey) {
		const nextName = nameDraft.trim();
		nameError = nextName ? '' : '이름을 입력하세요';
		if (!token || nameError) return;
		savingEdit = true;
		try {
			await api.patch(`/api/v1/chat/api-keys/${key.id}`, { name: nextName }, token, projectId);
			toast.success('이름을 변경했습니다');
			stopEditing();
			await load();
		} catch (error) {
			toast.error(error instanceof ApiError ? error.message : '이름 변경 실패');
		} finally {
			savingEdit = false;
		}
	}

	async function saveLimits(key: ApiKey) {
		const monthlyCeiling = tightestCeiling([
			[key.system_monthly_credit_limit, '사용자 쿼터'],
			[key.admin_monthly_credit_limit, '관리자 한도']
		]);
		const weeklyCeiling = tightestCeiling([
			[key.system_weekly_credit_limit, '사용자 주간 쿼터'],
			[key.system_monthly_credit_limit, '사용자 쿼터'],
			[key.admin_monthly_credit_limit, '관리자 한도']
		]);
		monthlyError = limitError(monthlyDraft, monthlyCeiling);
		weeklyError = limitError(weeklyDraft, weeklyCeiling);
		if (!token || monthlyError || weeklyError) return;
		savingEdit = true;
		try {
			await api.patch(
				`/api/v1/chat/api-keys/${key.id}/limits`,
				{
					monthly_credit_limit: monthlyDraft || null,
					weekly_credit_limit: weeklyDraft || null
				},
				token,
				projectId
			);
			toast.success('한도를 저장했습니다');
			stopEditing();
			await load();
		} catch (error) {
			toast.error(error instanceof ApiError ? error.message : '한도 저장 실패');
		} finally {
			savingEdit = false;
		}
	}

	async function copyText(value: string, successMessage = '복사되었습니다') {
		try {
			await navigator.clipboard.writeText(value);
			toast.success(successMessage);
		} catch {
			toast.error('복사 실패 — 수동으로 선택해 복사하세요');
		}
	}

	async function copyKey() {
		if (issued) await copyText(issued.key);
	}

	$effect(() => {
		if (token) void load();
	});

	$effect(() => {
		void loadConnectionGuide(token, projectId);
		return () => { guideGeneration += 1; };
	});

	const inputCls =
		'w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] px-3 py-2 text-sm text-[var(--color-ink-1)] focus:outline-none focus:border-[var(--color-accent)]';
	const cardCls = 'rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-raised)]';
	const codeCls = 'block overflow-x-auto rounded-lg bg-[var(--color-surface-sunken)] p-3 font-mono text-xs text-[var(--color-ink-2)]';
</script>

<section>
	<h3 class="mb-1 text-sm font-semibold text-[var(--color-ink-1)]">API 키</h3>
	<p class="mb-2 text-xs text-[var(--color-ink-3)]">
		외부 프로그램(OpenAI/Anthropic SDK)에서 이 채팅에 접속할 때 쓰는 키입니다. 사용량은 내 지갑의 월·주간 쿼터에서
		차감되며, 웹과 분리된 API 통계로 집계됩니다.
	</p>
	{#if usage}
		<p class="mb-3 text-xs tabular-nums text-[var(--color-ink-2)]">
			내 쿼터: 월 {formatCredit(String(usage.quota_max))} · 주간 {formatCredit(String(usage.quota_weekly_max))}
		</p>
	{/if}

	<div class="{cardCls} mb-4 p-5">
		<div class="flex flex-col gap-3 sm:flex-row">
			<input class={inputCls} placeholder="키 이름 (예: 내 노트북 CLI)" bind:value={name} />
			<Button onclick={create} disabled={creating}>{creating ? '발급 중…' : '+ 새 API 키 발급'}</Button>
		</div>
	</div>

	{#if loading}
		<div class="{cardCls} h-16 animate-pulse"></div>
	{:else if keys.length === 0}
		<p class="px-1 text-sm text-[var(--color-ink-3)]">발급된 API 키가 없습니다.</p>
	{:else}
		<div class="space-y-2">
			{#each keys as k (k.id)}
				<div class="{cardCls} px-4 py-3">
					<div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
						<div class="min-w-0">
							<div class="flex items-center gap-2">
								<span class="truncate text-sm font-medium text-[var(--color-ink-1)]">{k.name || '(이름 없음)'}</span>
								{#if !k.is_active}<span class="rounded bg-[var(--color-line)] px-1.5 py-0.5 text-xs text-[var(--color-ink-3)]">폐기됨</span>{/if}
							</div>
							<div class="mt-0.5 font-mono text-xs text-[var(--color-ink-3)]">
								{k.key_prefix}…{#if k.last_used_at} · 마지막 사용 {new Date(k.last_used_at).toLocaleString()}{:else} · 미사용{/if}
							</div>
							<div class="mt-1 text-xs tabular-nums text-[var(--color-ink-2)]">
								이번 달 {formatCredit(k.month_credited_cost, '0')} / {formatCredit(k.effective_monthly_credit_limit)}
								· 이번 주 {formatCredit(k.week_credited_cost, '0')} / {formatCredit(k.effective_weekly_credit_limit)}
							</div>
						</div>
						{#if k.is_active}
							<div class="flex shrink-0 flex-wrap gap-1">
								<Button variant="ghost" size="sm" onclick={() => editName(k)}>이름 변경</Button>
								<Button variant="ghost" size="sm" onclick={() => editLimits(k)}>한도 설정</Button>
								<Button variant="danger-outline" size="sm" onclick={() => revoke(k.id)}>폐기</Button>
							</div>
						{/if}
					</div>

					{#if editingId === k.id && editing === 'name'}
						<form
							class="mt-3 border-t border-[var(--color-line)] pt-3"
							onsubmit={(event) => {
								event.preventDefault();
								void saveName(k);
							}}
						>
							<div class="flex flex-col gap-2 sm:flex-row">
								<TextInput ariaLabel="API 키 이름" maxlength={100} bind:value={nameDraft} />
								<div class="flex justify-end gap-2">
									<Button variant="accent" size="sm" type="submit" disabled={savingEdit}>저장</Button>
									<Button variant="ghost" size="sm" type="button" onclick={stopEditing}>취소</Button>
								</div>
							</div>
							{#if nameError}<p class="mt-1 text-xs text-[var(--color-state-danger)]" role="alert">{nameError}</p>{/if}
						</form>
					{:else if editingId === k.id && editing === 'limits'}
						<form
							class="mt-3 border-t border-[var(--color-line)] pt-3"
							onsubmit={(event) => {
								event.preventDefault();
								void saveLimits(k);
							}}
						>
							<div class="grid gap-3 md:grid-cols-2">
								<Field
									label="월 한도(크레딧)"
									for="api-key-{k.id}-monthly-limit"
									help="비워두면 해제"
									error={monthlyError || undefined}
								>
									<TextInput
										id="api-key-{k.id}-monthly-limit"
										inputmode="decimal"
										bind:value={monthlyDraft}
									/>
								</Field>
								<Field
									label="주간 한도(크레딧)"
									for="api-key-{k.id}-weekly-limit"
									help="비워두면 해제"
									error={weeklyError || undefined}
								>
									<TextInput
										id="api-key-{k.id}-weekly-limit"
										inputmode="decimal"
										bind:value={weeklyDraft}
									/>
								</Field>
							</div>
							<div class="mt-3 flex justify-end gap-2">
								<Button variant="accent" size="sm" type="submit" disabled={savingEdit}>저장</Button>
								<Button variant="ghost" size="sm" type="button" onclick={stopEditing}>취소</Button>
							</div>
						</form>
					{/if}
				</div>
			{/each}
		</div>
	{/if}

	<!-- SDK 사용 예시 -->
	<div class="{cardCls} mt-5 min-w-0 p-5">
		<h4 class="mb-2 text-xs font-semibold text-[var(--color-ink-1)]">연결 방법</h4>
		{#if guideLoading}
			<p class="text-xs text-ink-2" role="status">Lumen 연결 정보를 불러오는 중입니다.</p>
		{:else if guideError}
			<Alert>{guideError}</Alert>
			<Button variant="secondary" size="sm" class="mt-3" onclick={() => loadConnectionGuide()}>
				연결 정보 다시 불러오기
			</Button>
		{:else if sdkBases}
			<p class="mb-2 text-xs text-ink-2">
				Lumen이 제공한 공개 API 주소입니다. 대시보드 주소와 다를 수 있으며, SDK별 base_url을 그대로 사용하세요.
			</p>
			<p class="mb-2 text-xs text-ink-2">
				<code>LUMEN_API_KEY</code> 환경 변수에 발급한 키를,
				<code>LUMEN_MODEL</code>에 모델 선택창의 <strong>ID 복사</strong>로 복사한 API ID를 설정하세요.
				동일한 API ID가 여러 프로바이더에 등록된 경우에만 <code>LUMEN_PROVIDER</code>에 표시된 provider 값을 설정하세요.
				아래 예제는 실제 요청을 보내며 API 사용량이 차감됩니다.
			</p>
			<p class="mb-3 text-xs text-ink-2">패키지 설치: <code>python -m pip install openai anthropic</code></p>
			<div class="mb-1 flex items-center justify-between gap-2">
				<p class="text-xs text-ink-2">OpenAI SDK (Python)</p>
				<Button variant="ghost" size="sm" onclick={() => copyText(openaiExample, 'OpenAI 예제를 복사했습니다')}>
					예제 복사
				</Button>
			</div>
			<pre class="{codeCls} max-w-full whitespace-pre" role="region" aria-label="OpenAI SDK Python 예제"><code>{openaiExample}</code></pre>
			<div class="mb-1 mt-3 flex items-center justify-between gap-2">
				<p class="text-xs text-ink-2">Anthropic SDK (Python)</p>
				<Button variant="ghost" size="sm" onclick={() => copyText(anthropicExample, 'Anthropic 예제를 복사했습니다')}>
					예제 복사
				</Button>
			</div>
			<pre class="{codeCls} max-w-full whitespace-pre" role="region" aria-label="Anthropic SDK Python 예제"><code>{anthropicExample}</code></pre>
		{:else}
			<p class="text-xs text-ink-2">로그인 후 Lumen 연결 정보를 확인할 수 있습니다.</p>
		{/if}
	</div>
</section>

<!-- 발급 직후 평문 키 1회 표시 모달 -->
{#if issued}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-surface-scrim/50 p-4" role="dialog" aria-modal="true">
		<div class="{cardCls} w-full max-w-lg p-6">
			<h3 class="mb-1 text-sm font-semibold text-[var(--color-ink-1)]">API 키가 발급되었습니다</h3>
			<p class="mb-3 text-xs text-[var(--color-state-danger)]">
				이 키는 지금 한 번만 표시됩니다. 안전한 곳에 저장하세요. 창을 닫으면 다시 볼 수 없습니다.
			</p>
			<code class={codeCls}>{issued.key}</code>
			<div class="mt-4 flex justify-end gap-2">
				<Button variant="ghost" onclick={copyKey}>복사</Button>
				<Button onclick={() => (issued = null)}>완료</Button>
			</div>
		</div>
	</div>
{/if}
