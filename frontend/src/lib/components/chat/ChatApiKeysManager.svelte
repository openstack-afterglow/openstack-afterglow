<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import { formatCredit, isCreditInput } from '$lib/api/chatQuotas';
	import type { ApiKey } from '$lib/api/chatUsage';
	import type { ChatUsage } from '$lib/api/chatTree';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import { t } from '$lib/i18n/ns/chat-settings';
	import RichText from '$lib/i18n/RichText.svelte';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

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
		clients: {
			codex: { base_url: string };
		};
	}
	type ClientGuide = 'codex' | 'claude-code' | 'openai' | 'claude';
	const clientGuideTabs: Array<{ value: ClientGuide; label: string; panelId: string }> = [
		{ value: 'codex', label: 'Codex', panelId: 'api-key-guide-codex-panel' },
		{ value: 'claude-code', label: 'Claude Code', panelId: 'api-key-guide-claude-code-panel' },
		{ value: 'openai', label: 'OpenAI', panelId: 'api-key-guide-openai-panel' },
		{ value: 'claude', label: 'Claude', panelId: 'api-key-guide-claude-panel' }
	];
	let activeGuide = $state<ClientGuide>('codex');
	let sdkBases = $state<{ openai: string; anthropic: string; codex: string } | null>(null);
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
				anthropic: sdkBaseUrl(discovery.endpoints?.anthropic?.sdk_base_url),
				codex: sdkBaseUrl(discovery.clients?.codex?.base_url)
			};
		} catch {
			if (generation !== guideGeneration) return;
			guideError = t('apiKeys.guide.loadFailed');
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

	const codexConfigExample = $derived(sdkBases ? `[model_providers.lumen]
name = "Lumen Responses"
base_url = ${JSON.stringify(sdkBases.codex)}
env_key = "LUMEN_API_KEY"
wire_api = "responses"
requires_openai_auth = false
supports_websockets = false

# ${t('apiKeys.codex.providerComment')}
# http_headers = { "X-Lumen-Provider" = "provider-id" }` : '');
	const keyPromptExample = `printf 'Lumen API key: '; read -rs LUMEN_API_KEY; printf '\\n'; export LUMEN_API_KEY`;
	const codexShellExample = `codex --strict-config -c model_provider=lumen -m "replace-with-active-Responses-model-ID"`;
	const claudeCodeExample = $derived(sdkBases ? `export LUMEN_MODEL="replace-with-active-Anthropic-model-ID"
export ANTHROPIC_BASE_URL=${JSON.stringify(sdkBases.anthropic)}
export ANTHROPIC_AUTH_TOKEN="$LUMEN_API_KEY"
export ANTHROPIC_MODEL="$LUMEN_MODEL"
export ANTHROPIC_DEFAULT_SONNET_MODEL="$LUMEN_MODEL"
export ANTHROPIC_DEFAULT_OPUS_MODEL="$LUMEN_MODEL"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="$LUMEN_MODEL"

# ${t('apiKeys.claude.providerComment')}
# export LUMEN_PROVIDER="replace-with-provider-id"
# export ANTHROPIC_CUSTOM_HEADERS="X-Lumen-Provider: $LUMEN_PROVIDER"
claude` : '');

	async function load() {
		if (!token) return;
		loading = true;
		try {
			keys = await api.get<ApiKey[]>('/api/v1/chat/api-keys', token, projectId);
		} catch {
			toast.error(t('apiKeys.toast.loadFailed'));
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
			toast.error(e instanceof ApiError ? e.message : t('apiKeys.toast.createFailed'));
		} finally {
			creating = false;
		}
	}

	async function revoke(id: number) {
		if (!(await confirmDialog(t('apiKeys.revokeConfirm')))) return;
		try {
			await api.delete(`/api/v1/chat/api-keys/${id}`, token, projectId);
			await load();
		} catch {
			toast.error(t('apiKeys.toast.revokeFailed'));
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
		if (!isCreditInput(value)) return t('apiKeys.validation.positiveCredit');
		if (ceiling && Number(value) > ceiling.limit) {
			return t('apiKeys.validation.exceedsCeiling', { label: ceiling.label, limit: formatCredit(String(ceiling.limit)) });
		}
		return '';
	}

	async function saveName(key: ApiKey) {
		const nextName = nameDraft.trim();
		nameError = nextName ? '' : t('apiKeys.validation.nameRequired');
		if (!token || nameError) return;
		savingEdit = true;
		try {
			await api.patch(`/api/v1/chat/api-keys/${key.id}`, { name: nextName }, token, projectId);
			toast.success(t('apiKeys.toast.nameSaved'));
			stopEditing();
			await load();
		} catch (error) {
			toast.error(error instanceof ApiError ? error.message : t('apiKeys.toast.nameFailed'));
		} finally {
			savingEdit = false;
		}
	}

	async function saveLimits(key: ApiKey) {
		const monthlyCeiling = tightestCeiling([
			[key.system_monthly_credit_limit, t('apiKeys.ceiling.userQuota')],
			[key.admin_monthly_credit_limit, t('apiKeys.ceiling.adminLimit')]
		]);
		const weeklyCeiling = tightestCeiling([
			[key.system_weekly_credit_limit, t('apiKeys.ceiling.userWeeklyQuota')],
			[key.system_monthly_credit_limit, t('apiKeys.ceiling.userQuota')],
			[key.admin_monthly_credit_limit, t('apiKeys.ceiling.adminLimit')]
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
			toast.success(t('apiKeys.toast.limitsSaved'));
			stopEditing();
			await load();
		} catch (error) {
			toast.error(error instanceof ApiError ? error.message : t('apiKeys.toast.limitsFailed'));
		} finally {
			savingEdit = false;
		}
	}

	async function copyText(value: string, successMessage = t('apiKeys.toast.copied')) {
		try {
			await navigator.clipboard.writeText(value);
			toast.success(successMessage);
		} catch {
			toast.error(t('apiKeys.toast.copyFailed'));
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
	<h3 class="mb-1 text-sm font-semibold text-[var(--color-ink-1)]">{t('apiKeys.title')}</h3>
	<p class="mb-2 text-xs text-[var(--color-ink-3)]">
		{t('apiKeys.description')}
	</p>
	{#if usage}
		<p class="mb-3 text-xs tabular-nums text-[var(--color-ink-2)]">
			{t('apiKeys.quota', { monthly: formatCredit(String(usage.quota_max)), weekly: formatCredit(String(usage.quota_weekly_max)) })}
		</p>
	{/if}

	<div class="{cardCls} mb-4 p-5">
		<div class="flex flex-col gap-3 sm:flex-row">
			<input class={inputCls} placeholder={t('apiKeys.namePlaceholder')} bind:value={name} />
			<Button onclick={create} disabled={creating}>{creating ? t('apiKeys.creating') : t('apiKeys.create')}</Button>
		</div>
	</div>

	{#if loading}
		<div class="{cardCls} h-16 animate-pulse"></div>
	{:else if keys.length === 0}
		<p class="px-1 text-sm text-[var(--color-ink-3)]">{t('apiKeys.empty')}</p>
	{:else}
		<div class="space-y-2">
			{#each keys as k (k.id)}
				<div class="{cardCls} px-4 py-3">
					<div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
						<div class="min-w-0">
							<div class="flex items-center gap-2">
								<span class="truncate text-sm font-medium text-[var(--color-ink-1)]">{k.name || t('apiKeys.unnamed')}</span>
								{#if !k.is_active}<span class="rounded bg-[var(--color-line)] px-1.5 py-0.5 text-xs text-[var(--color-ink-3)]">{t('apiKeys.revoked')}</span>{/if}
							</div>
							<div class="mt-0.5 font-mono text-xs text-[var(--color-ink-3)]">
								{k.key_prefix}…{#if k.last_used_at} · {t('apiKeys.lastUsed', { date: new Date(k.last_used_at).toLocaleString(intlLocale()) })}{:else} · {t('apiKeys.unused')}{/if}
							</div>
							<div class="mt-1 text-xs tabular-nums text-[var(--color-ink-2)]">
								{t('apiKeys.usage', { monthlyUsed: formatCredit(k.month_credited_cost, '0'), monthlyLimit: formatCredit(k.effective_monthly_credit_limit), weeklyUsed: formatCredit(k.week_credited_cost, '0'), weeklyLimit: formatCredit(k.effective_weekly_credit_limit) })}
							</div>
						</div>
						{#if k.is_active}
							<div class="flex shrink-0 flex-wrap gap-1">
								<Button variant="ghost" size="sm" onclick={() => editName(k)}>{t('apiKeys.rename')}</Button>
								<Button variant="ghost" size="sm" onclick={() => editLimits(k)}>{t('apiKeys.setLimits')}</Button>
								<Button variant="danger-outline" size="sm" onclick={() => revoke(k.id)}>{t('apiKeys.revoke')}</Button>
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
								<TextInput ariaLabel={t('apiKeys.nameLabel')} maxlength={100} bind:value={nameDraft} />
								<div class="flex justify-end gap-2">
									<Button variant="accent" size="sm" type="submit" disabled={savingEdit}>{t('apiKeys.save')}</Button>
									<Button variant="ghost" size="sm" type="button" onclick={stopEditing}>{t('apiKeys.cancel')}</Button>
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
									label={t('apiKeys.monthlyLimit')}
									for="api-key-{k.id}-monthly-limit"
									help={t('apiKeys.limitHelp')}
									error={monthlyError || undefined}
								>
									<TextInput
										id="api-key-{k.id}-monthly-limit"
										inputmode="decimal"
										bind:value={monthlyDraft}
									/>
								</Field>
								<Field
									label={t('apiKeys.weeklyLimit')}
									for="api-key-{k.id}-weekly-limit"
									help={t('apiKeys.limitHelp')}
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
								<Button variant="accent" size="sm" type="submit" disabled={savingEdit}>{t('apiKeys.save')}</Button>
								<Button variant="ghost" size="sm" type="button" onclick={stopEditing}>{t('apiKeys.cancel')}</Button>
							</div>
						</form>
					{/if}
				</div>
			{/each}
		</div>
	{/if}

	<!-- SDK 사용 예시 -->
	<div class="{cardCls} mt-5 min-w-0 p-5">
		<h4 class="mb-2 text-xs font-semibold text-[var(--color-ink-1)]">{t('apiKeys.guide.title')}</h4>
		{#if guideLoading}
			<p class="text-xs text-ink-2" role="status">{t('apiKeys.guide.loading')}</p>
		{:else if guideError}
			<Alert>{guideError}</Alert>
			<Button variant="secondary" size="sm" class="mt-3" onclick={() => loadConnectionGuide()}>
				{t('apiKeys.guide.reload')}
			</Button>
		{:else if sdkBases}
			<p class="mb-4 text-sm leading-6 text-ink-2">
				{t('apiKeys.guide.prerequisites')}
			</p>
			<Tabs
				id="api-key-client-guides"
				value={activeGuide}
				items={clientGuideTabs}
				onchange={(value) => { activeGuide = value as ClientGuide; }}
				ariaLabel={t('apiKeys.guide.clientsLabel')}
				class="mb-4"
			/>
			<div
				id={`api-key-guide-${activeGuide}-panel`}
				role="tabpanel"
				aria-labelledby={`api-key-client-guides-${activeGuide}`}
				tabindex="0"
				class="min-w-0"
			>
				{#if activeGuide === 'codex'}
					<div class="mb-2 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
						<div>
							<p class="text-sm font-medium text-ink-1">{t('apiKeys.codex.title')}</p>
							<p class="mt-1 text-sm leading-6 text-ink-2">
								<RichText segments={t.rich('apiKeys.codex.introduction', { providerHeader: 'X-Lumen-Provider' })} />
							</p>
						</div>
						<Button variant="ghost" size="sm" onclick={() => copyText(codexConfigExample, t('apiKeys.toast.codexConfigCopied'))}>
							{t('apiKeys.codex.copyConfig')}
						</Button>
					</div>
					<p class="mb-2 text-sm leading-6 text-ink-2">
						<RichText segments={t.rich('apiKeys.codex.configHelp', { configPath: '~/.codex/config.toml', model: 'model', modelProvider: 'model_provider' })} />
					</p>
					<pre class="{codeCls} max-w-full whitespace-pre" role="region" aria-label={t('apiKeys.codex.configLabel')}><code>{codexConfigExample}</code></pre>
					<p class="mt-3 text-sm leading-6 text-ink-2">
						{t('apiKeys.codex.keyPromptHelp')}
					</p>
					<pre class="{codeCls} mt-2 max-w-full whitespace-pre" role="region" aria-label={t('apiKeys.guide.keyPromptLabel')}><code>{keyPromptExample}</code></pre>
					<p class="mt-3 text-sm leading-6 text-ink-2">
						<RichText segments={t.rich('apiKeys.codex.runHelp', { modelId: 'replace-with-active-Responses-model-ID' })} />
					</p>
					<pre class="{codeCls} mt-2 max-w-full whitespace-pre" role="region" aria-label={t('apiKeys.codex.runLabel')}><code>{codexShellExample}</code></pre>
					<p class="mt-2 text-sm leading-6 text-ink-2">
						<RichText segments={t.rich('apiKeys.codex.tlsHelp', { requestError: 'error sending request', certificateVariable: 'CODEX_CA_CERTIFICATE', certificateCommand: 'export CODEX_CA_CERTIFICATE="/private/etc/ssl/cert.pem"' })} />
					</p>
				{:else if activeGuide === 'claude-code'}
					<div class="mb-2 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
						<div>
							<p class="text-sm font-medium text-ink-1">{t('apiKeys.claudeCode.title')}</p>
							<p class="mt-1 text-sm leading-6 text-ink-2">
								{t('apiKeys.claudeCode.introduction')}
							</p>
						</div>
						<Button variant="ghost" size="sm" onclick={() => copyText(claudeCodeExample, t('apiKeys.toast.claudeCodeCopied'))}>
							{t('apiKeys.claudeCode.copyCommand')}
						</Button>
					</div>
					<pre class="{codeCls} max-w-full whitespace-pre" role="region" aria-label={t('apiKeys.guide.keyPromptLabel')}><code>{keyPromptExample}</code></pre>
					<p class="mt-3 text-sm leading-6 text-ink-2">
						<RichText segments={t.rich('apiKeys.claudeCode.runHelp', { modelId: 'replace-with-active-Anthropic-model-ID' })} />
					</p>
					<pre class="{codeCls} max-w-full whitespace-pre" role="region" aria-label={t('apiKeys.claudeCode.commandLabel')}><code>{claudeCodeExample}</code></pre>
				{:else if activeGuide === 'openai'}
					<div class="mb-2 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
						<div>
							<p class="text-sm font-medium text-ink-1">{t('apiKeys.openai.title')}</p>
							<p class="mt-1 text-sm leading-6 text-ink-2">
								<RichText segments={t.rich('apiKeys.openai.installHelp', { installCommand: 'python -m pip install openai', apiKey: 'LUMEN_API_KEY', model: 'LUMEN_MODEL', provider: 'LUMEN_PROVIDER' })} />
							</p>
						</div>
						<Button variant="ghost" size="sm" onclick={() => copyText(openaiExample, t('apiKeys.toast.openaiCopied'))}>
							{t('apiKeys.openai.copyExample')}
						</Button>
					</div>
					<pre class="{codeCls} max-w-full whitespace-pre" role="region" aria-label={t('apiKeys.openai.exampleLabel')}><code>{openaiExample}</code></pre>
				{:else}
					<div class="mb-2 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
						<div>
							<p class="text-sm font-medium text-ink-1">{t('apiKeys.claude.title')}</p>
							<p class="mt-1 text-sm leading-6 text-ink-2">
								<RichText segments={t.rich('apiKeys.claude.installHelp', { installCommand: 'python -m pip install anthropic', apiKey: 'LUMEN_API_KEY', model: 'LUMEN_MODEL', provider: 'LUMEN_PROVIDER' })} />
							</p>
						</div>
						<Button variant="ghost" size="sm" onclick={() => copyText(anthropicExample, t('apiKeys.toast.claudeCopied'))}>
							{t('apiKeys.claude.copyExample')}
						</Button>
					</div>
					<pre class="{codeCls} max-w-full whitespace-pre" role="region" aria-label={t('apiKeys.claude.exampleLabel')}><code>{anthropicExample}</code></pre>
				{/if}
			</div>
		{:else}
			<p class="text-xs text-ink-2">{t('apiKeys.guide.signIn')}</p>
		{/if}
	</div>
</section>

<!-- 발급 직후 평문 키 1회 표시 모달 -->
{#if issued}
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => (issued = null) }}
		class="fixed inset-0 z-50 flex items-center justify-center bg-surface-scrim/50 p-4"
		role="dialog"
		aria-modal="true"
		aria-labelledby="issued-key-title"
		tabindex="-1"
	>
		<div class="{cardCls} w-full max-w-lg p-6">
			<h3 id="issued-key-title" class="mb-1 text-sm font-semibold text-[var(--color-ink-1)]">{t('apiKeys.issued.title')}</h3>
			<p class="mb-3 text-xs text-[var(--color-state-danger)]">
				{t('apiKeys.issued.warning')}
			</p>
			<code class={codeCls}>{issued.key}</code>
			<div class="mt-4 flex justify-end gap-2">
				<Button variant="ghost" onclick={copyKey}>{t('apiKeys.copy')}</Button>
				<Button onclick={() => (issued = null)}>{t('apiKeys.done')}</Button>
			</div>
		</div>
	</div>
{/if}

<style>
	/* The shared scrollable Tabs row also gains a 1px vertical scrollbar from its tab borders. */
	section :global(#api-key-client-guides) {
		flex-wrap: wrap;
		overflow: visible;
	}

	@media (max-width: 767px) {
		section :global(#api-key-client-guides) {
			display: grid;
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}

		section :global(#api-key-client-guides > button) {
			min-width: 0;
			margin-bottom: 0;
			padding-inline: 0.5rem;
			white-space: normal;
		}
	}
</style>
