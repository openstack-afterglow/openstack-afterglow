<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-settings';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import ChatVault from './ChatVault.svelte';
	import ChatExtensionsManager from './ChatExtensionsManager.svelte';
	import ChatApiKeysManager from './ChatApiKeysManager.svelte';
	import ChatUsagePanel from './ChatUsagePanel.svelte';
	import type { ChatUsage } from '$lib/api/chatTree';
	import { displayDomainCredit } from '$lib/api/chatDomainBilling';
	import Alert from '$lib/components/ui/Alert.svelte';

	export type ChatSettingsSection = 'usage' | 'apikeys' | 'memory' | 'mcp' | 'tools' | 'skills';

	interface Props {
		initialSection?: ChatSettingsSection;
	}
	let { initialSection = 'usage' }: Props = $props();
	let section = $state<ChatSettingsSection>('usage');

	$effect(() => {
		section = initialSection;
	});

	const sections: { key: ChatSettingsSection; label: string }[] = [
		{ key: 'usage', get label() { return t('settings.sections.usage'); } },
		{ key: 'apikeys', get label() { return t('settings.sections.apiKeys'); } },
		{ key: 'memory', get label() { return t('settings.sections.memory'); } },
		{ key: 'mcp', get label() { return t('settings.sections.mcp'); } },
		{ key: 'tools', get label() { return t('settings.sections.tools'); } },
		{ key: 'skills', get label() { return t('settings.sections.skills'); } }
	];

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	let usage = $state<ChatUsage | null>(null);
	let usageGeneration = 0;

	async function loadUsage(
		expectedToken: string,
		expectedProjectId: string | undefined,
		generation: number
	) {
		try {
			const nextUsage = await api.get<ChatUsage>(
				'/api/v1/chat/usage',
				expectedToken,
				expectedProjectId
			);
			if (generation === usageGeneration) usage = nextUsage;
		} catch {
			if (generation === usageGeneration) usage = null;
		}
	}

	function selectSection(nextSection: ChatSettingsSection) {
		section = nextSection;
		void goto(`/dashboard/chat/settings?section=${nextSection}`, {
			replaceState: true,
			keepFocus: true,
			noScroll: true
		});
	}

	$effect(() => {
		const currentToken = token;
		const currentProjectId = projectId;
		const generation = ++usageGeneration;
		usage = null;
		if (currentToken) void loadUsage(currentToken, currentProjectId, generation);
	});

	// --- 사용량 ---
	const monthTokens = $derived(
		(usage?.month_prompt_tokens ?? 0) + (usage?.month_completion_tokens ?? 0)
	);
	const credit = $derived(usage?.month_credited_cost ?? 0);
	const requests = $derived(usage?.month_request_count ?? 0);
	const quotaMax = $derived(usage?.quota_max ?? 0);
	const quotaUsed = $derived(usage?.quota_used ?? 0);
	const domainUsage = $derived(usage?.billing_scope === 'domain' && !!$auth.domainId && usage.payer_domain_id === $auth.domainId ? usage : null);
	const domainInsufficient = $derived(domainUsage?.balance_credits != null && domainUsage.reserved_credits != null &&
		Number(domainUsage.balance_credits) <= Number(domainUsage.reserved_credits));
	function fmt(n: number): string {
		return n.toLocaleString('en-US');
	}
	function fmtCredit(n: number): string {
		return n.toLocaleString('en-US', { maximumFractionDigits: 2 });
	}

</script>

<section class="settings-page">
	<header class="page-head">
		<h1>{t('settings.title')}</h1>
		<p>{t('settings.description')}</p>
	</header>

	<div class="panel">
		<div class="split">
			<nav class="nav" aria-label={t('settings.title')}>
				{#each sections as s (s.key)}
					<button
						type="button"
						class="nav-item"
						class:active={section === s.key}
						aria-current={section === s.key ? 'page' : undefined}
						onclick={() => selectSection(s.key)}
					>
						{s.label}
					</button>
				{/each}
			</nav>

			<div class="content">
				{#if section === 'usage'}
					<section class="sec">
						<h2 class="sec-title">{t('settings.usage.title')}</h2>
						<div class="stats">
							<div class="stat">
								<span class="stat-val">{fmt(monthTokens)}</span>
								<span class="stat-lbl">{t('settings.usage.tokens')}</span>
							</div>
							<div class="stat">
								<span class="stat-val">{fmtCredit(credit)}</span>
								<span class="stat-lbl">{t('settings.usage.credits')}</span>
							</div>
							<div class="stat">
								<span class="stat-val">{fmt(requests)}</span>
								<span class="stat-lbl">{t('settings.usage.requests')}</span>
							</div>
						</div>
						{#if domainUsage}
							<div class="space-y-2 py-3">
								<h3 class="text-sm font-semibold text-ink-1">{t('domainBilling.title')}</h3>
								<p class="text-xs text-ink-2">{t('domainBilling.memberDescription')}</p>
								<dl class="grid grid-cols-2 gap-3 text-sm tabular-nums">
									<div><dt class="text-xs text-ink-2">{t('domainBilling.balance')}</dt><dd>{displayDomainCredit(domainUsage.balance_credits)}</dd></div>
									<div><dt class="text-xs text-ink-2">{t('domainBilling.reserved')}</dt><dd>{displayDomainCredit(domainUsage.reserved_credits)}</dd></div>
									{#if domainUsage.monthly_used_credits !== undefined}
										<div><dt class="text-xs text-ink-2">{t('domainBilling.monthlyUsed')}</dt><dd>{displayDomainCredit(domainUsage.monthly_used_credits)}</dd></div>
									{/if}
									{#if domainUsage.effective_monthly_limit_credits !== undefined}
										<div>
											<dt class="text-xs text-ink-2">{t('apiKeys.monthlyLimit')}</dt>
											<dd>{domainUsage.effective_monthly_limit_credits === null ? t('domainBilling.noLimit') : displayDomainCredit(domainUsage.effective_monthly_limit_credits)}</dd>
										</div>
									{/if}
								</dl>
								{#if domainUsage.is_active === false}<Alert flat tone="warning">{t('domainBilling.inactive')}</Alert>{/if}
								{#if domainInsufficient}<Alert flat tone="warning">{t('domainBilling.insufficient')}</Alert>{/if}
							</div>
						{/if}
						{#if !domainUsage && quotaMax > 0}
							<p class="sec-desc quota">
								{t('settings.usage.monthlyQuota', { used: fmt(quotaUsed), limit: fmt(quotaMax) })}
							</p>
						{/if}
						{#if (usage?.quota_weekly_max ?? 0) > 0}
							<p class="sec-desc quota">
								{t('settings.usage.weeklyQuota', { used: fmt(usage?.week_credited_cost ?? 0), limit: fmt(usage?.quota_weekly_max ?? 0) })}
							</p>
						{/if}
						<div class="mt-4">
							<ChatUsagePanel />
						</div>
					</section>
				{:else if section === 'apikeys'}
					<section class="sec">
						<h2 class="sr-only">{t('settings.sections.apiKeys')}</h2>
						<ChatApiKeysManager />
					</section>
				{:else if section === 'memory'}
					<ChatVault />
				{:else if section === 'mcp'}
					<section class="sec">
						<ChatExtensionsManager base="/api/v1/chat" only="mcp" />
					</section>
				{:else if section === 'tools'}
					<section class="sec">
						<ChatExtensionsManager base="/api/v1/chat" only="tools" />
					</section>
				{:else if section === 'skills'}
					<section class="sec">
						<ChatExtensionsManager base="/api/v1/chat" only="skills" />
					</section>
				{/if}
			</div>
		</div>
	</div>
</section>


<style>
	.settings-page {
		width: 100%;
		height: 100%;
		min-height: 0;
		display: flex;
		flex-direction: column;
	}
	.page-head {
		margin-bottom: 1rem;
	}
	.page-head h1 {
		margin: 0;
		font-size: clamp(1.45rem, 3vw, 2rem);
		font-weight: 700;
		letter-spacing: -0.025em;
		color: var(--color-ink-0);
	}
	.page-head p {
		margin: 0.35rem 0 0;
		color: var(--color-ink-2);
		font-size: 0.875rem;
	}
	.panel {
		display: flex;
		min-height: 0;
		flex: 1;
		flex-direction: column;
		border-radius: 0.9rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
		overflow: hidden;
	}
	.split {
		display: flex;
		flex: 1;
		min-height: 0;
	}
	.nav {
		width: 11rem;
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		padding: 0.75rem;
		border-right: 1px solid var(--color-line);
		background: var(--color-surface-sunken);
		overflow-y: auto;
	}
	.nav-item {
		text-align: left;
		display: block;
		padding: 0.5rem 0.65rem;
		border: none;
		border-radius: 0.55rem;
		background: transparent;
		color: var(--color-ink-2);
		font-size: 0.8125rem;
		font-weight: 550;
		text-decoration: none;
		cursor: pointer;
		transition:
			background var(--motion-duration-fast) var(--motion-ease-standard),
			color var(--motion-duration-fast) var(--motion-ease-standard);
	}
	.nav-item:hover {
		background: var(--color-surface-base);
		color: var(--color-ink-0);
	}
	.nav-item.active {
		background: var(--color-surface-selected);
		color: var(--color-ink-0);
	}
	.content {
		flex: 1;
		min-width: 0;
		padding: 1.2rem 1.3rem;
		overflow-y: auto;
	}
	.sec {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.sec-title {
		margin: 0;
		font-size: 0.9rem;
		font-weight: 650;
		color: var(--color-ink-0);
	}
	.sec-desc {
		margin: 0;
		font-size: 0.78rem;
		color: var(--color-ink-2);
	}
	.stats {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
		gap: 0.6rem;
		margin-top: 0.4rem;
	}
	.stat {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		padding: 0.8rem 0;
		border-bottom: 1px solid var(--color-line);
	}
	.stat-val {
		font-size: 1.05rem;
		font-weight: 650;
		color: var(--color-ink-0);
		font-variant-numeric: tabular-nums;
	}
	.stat-lbl {
		font-size: 0.72rem;
		color: var(--color-ink-2);
	}
	.quota {
		margin-top: 0.5rem;
		font-variant-numeric: tabular-nums;
	}
	@media (max-width: 767px) {
		.split {
			flex-direction: column;
		}
		.nav {
			width: 100%;
			flex-direction: row;
			overflow-x: auto;
			border-right: none;
			border-bottom: 1px solid var(--color-line);
		}
		.nav-item {
			flex-shrink: 0;
			white-space: nowrap;
		}
		.content {
			padding: 1rem;
		}
	}
</style>
