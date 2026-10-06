<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { UserUsageDetail } from '$lib/api/chatQuotas';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { t } from '$lib/i18n/ns/admin-chat-usage';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	interface UsageUser {
		id: string;
		name: string;
		email: string;
	}

	let {
		open,
		user,
		onClose
	}: {
		open: boolean;
		user: UsageUser | null;
		onClose: () => void;
	} = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const scopeKey = $derived(open && user && token ? `${user.id}:${token}:${projectId ?? ''}` : '');
	let range = $state<'7d' | '30d' | '90d' | '1y' | 'all'>('30d');
	let source = $state<'' | 'web' | 'api'>('');
	let detail = $state<UserUsageDetail | null>(null);
	let loading = $state(false);
	let loadingMore = $state(false);
	let error = $state('');
	let generation = 0;

	function formatNumber(value: number): string {
		return value.toLocaleString(intlLocale());
	}

	function formatDecimal(value: string, maximumFractionDigits = 6): string {
		return Number(value).toLocaleString(intlLocale(), { maximumFractionDigits });
	}

	function formatDate(value: string): string {
		return new Intl.DateTimeFormat(intlLocale(), {
			year: 'numeric',
			month: '2-digit',
			day: '2-digit',
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		}).format(new Date(value));
	}

	function sourceLabel(value: 'web' | 'api' | undefined): string {
		return value === 'api' ? t('source.api') : t('source.web');
	}

	async function load(reset: boolean) {
		if (!user || !token) return;
		const currentGeneration = reset ? ++generation : generation;
		if (reset) {
			loading = true;
			error = '';
		} else {
			loadingMore = true;
		}
		try {
			const params = new URLSearchParams({ range, limit: '50' });
			if (source) params.set('source', source);
			if (!reset && detail?.next_before_id) params.set('before_id', String(detail.next_before_id));
			const next = await api.get<UserUsageDetail>(
				`/api/v1/chat/admin/stats/users/${encodeURIComponent(user.id)}?${params}`,
				token,
				projectId
			);
			if (currentGeneration !== generation) return;
			detail = reset || !detail
				? next
				: { ...next, records: [...detail.records, ...next.records] };
		} catch (caught) {
			if (currentGeneration === generation) {
				error = caught instanceof ApiError ? caught.message : t('loadFailed');
			}
		} finally {
			if (currentGeneration === generation) {
				loading = false;
				loadingMore = false;
			}
		}
	}

	$effect(() => {
		const key = scopeKey;
		if (!key) return;
		untrack(() => {
			range = '30d';
			source = '';
			detail = null;
			void load(true);
		});
		return () => {
			generation += 1;
		};
	});
</script>

<Modal {open} {onClose} ariaLabel={t('modalLabel')}>
	<div class="flex max-h-[calc(100dvh-2rem)] w-[min(72rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] shadow-[var(--shadow-restraint)]">
		<header class="flex items-start justify-between gap-3 border-b border-[var(--color-line)] p-4 sm:p-5">
			<div class="min-w-0">
				<h2 class="truncate text-lg font-semibold text-[var(--color-ink-1)]">{t('title', { name: user?.name ?? '' })}</h2>
				<p class="truncate text-xs text-[var(--color-ink-3)]">{user?.email || user?.id}</p>
			</div>
			<Button variant="ghost" size="sm" onclick={onClose}>{t('close')}</Button>
		</header>

		<div class="min-h-0 overflow-y-auto p-4 sm:p-5">
			<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,12rem)_minmax(0,12rem)_1fr] lg:items-end">
				<label class="text-sm text-[var(--color-ink-2)]">
					<span class="mb-1 block">{t('period')}</span>
					<SelectInput bind:value={range} onchange={() => void load(true)} ariaLabel={t('periodLabel')}>
						<option value="7d">{t('range.7d')}</option>
						<option value="30d">{t('range.30d')}</option>
						<option value="90d">{t('range.90d')}</option>
						<option value="1y">{t('range.1y')}</option>
						<option value="all">{t('range.all')}</option>
					</SelectInput>
				</label>
				<label class="text-sm text-[var(--color-ink-2)]">
					<span class="mb-1 block">{t('sourceLabel')}</span>
					<SelectInput bind:value={source} onchange={() => void load(true)} ariaLabel={t('sourceLabel')}>
						<option value="">{t('source.all')}</option>
						<option value="web">{t('source.web')}</option>
						<option value="api">{t('source.api')}</option>
					</SelectInput>
				</label>
				{#if detail}
					<p class="text-xs text-[var(--color-ink-3)] lg:text-right">
						{detail.period_start ? formatDate(detail.period_start) : t('firstRecord')} – {formatDate(detail.period_end)}
					</p>
				{/if}
			</div>

			{#if error}
				<Alert class="mt-4">{error}</Alert>
			{/if}

			{#if loading}
				<div class="mt-5"><LoadingSkeleton variant="table" rows={5} /></div>
			{:else if detail}
				<div class="mt-5 grid grid-cols-2 gap-2 md:grid-cols-4">
					<div class="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] p-3">
						<p class="text-xs text-[var(--color-ink-3)]">{t('totalTokens')}</p>
						<p class="mt-1 text-lg font-semibold tabular-nums text-[var(--color-ink-1)]">{formatNumber(detail.overview.total_tokens)}</p>
					</div>
					<div class="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] p-3">
						<p class="text-xs text-[var(--color-ink-3)]">{t('requests')}</p>
						<p class="mt-1 text-lg font-semibold tabular-nums text-[var(--color-ink-1)]">{formatNumber(detail.overview.request_count)}</p>
					</div>
					<div class="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] p-3">
						<p class="text-xs text-[var(--color-ink-3)]">{t('chargedCredits')}</p>
						<p class="mt-1 text-lg font-semibold tabular-nums text-[var(--color-ink-1)]">{formatDecimal(detail.overview.credited_cost, 2)}</p>
					</div>
					<div class="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] p-3">
						<p class="text-xs text-[var(--color-ink-3)]">{t('modelCost')}</p>
						<p class="mt-1 text-lg font-semibold tabular-nums text-[var(--color-ink-1)]">${formatDecimal(detail.overview.raw_cost)}</p>
					</div>
				</div>

				<section class="mt-6" aria-labelledby="usage-source-title">
					<h3 id="usage-source-title" class="text-sm font-semibold text-[var(--color-ink-1)]">{t('sourceLabel')}</h3>
					<div class="mt-2 flex flex-wrap gap-2">
						{#each detail.by_source as item (item.source)}
							<div class="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] px-3 py-2 text-sm">
								<Pill tone="neutral" size="xs">{sourceLabel(item.source)}</Pill>
								<span class="ml-2 tabular-nums text-[var(--color-ink-2)]">{t('sourceSummary', { tokens: formatNumber(item.total_tokens), credits: formatDecimal(item.credited_cost, 2) })}</span>
							</div>
						{/each}
						{#if detail.by_source.length === 0}<EmptyState headline={t('noRecords')} class="py-4 [&_.motion-enter]:animate-none" />{/if}
					</div>
				</section>

				<section class="mt-6" aria-labelledby="usage-model-title">
					<h3 id="usage-model-title" class="mb-2 text-sm font-semibold text-[var(--color-ink-1)]">{t('modelUsage')}</h3>
					<div class="hidden md:block">
						<TableShell density="compact">
							<table>
								<thead><tr><th>{t('model')}</th><th>{t('input')}</th><th>{t('output')}</th><th>{t('total')}</th><th>{t('credits')}</th><th>{t('cost')}</th><th>{t('requests')}</th></tr></thead>
								<tbody>
									{#each detail.by_model as item (`${item.provider ?? ''}:${item.model_name}`)}
										<tr>
											<td><div class="font-medium text-[var(--color-ink-1)]">{item.model_name}</div><div class="text-xs text-[var(--color-ink-3)]">{item.provider ?? t('unknown')}</div></td>
											<td class="tabular-nums">{formatNumber(item.prompt_tokens)}</td>
											<td class="tabular-nums">{formatNumber(item.completion_tokens)}</td>
											<td class="tabular-nums">{formatNumber(item.total_tokens)}</td>
											<td class="tabular-nums">{formatDecimal(item.credited_cost, 2)}</td>
											<td class="tabular-nums">${formatDecimal(item.raw_cost)}</td>
											<td class="tabular-nums">{formatNumber(item.request_count)}</td>
										</tr>
									{/each}
									{#if detail.by_model.length === 0}<tr><td colspan="7"><EmptyState headline={t('noRecords')} class="py-4 [&_.motion-enter]:animate-none" /></td></tr>{/if}
								</tbody>
							</table>
						</TableShell>
					</div>
					<div class="grid gap-2 md:hidden">
						{#each detail.by_model as item (`mobile:${item.provider ?? ''}:${item.model_name}`)}
							<article class="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] p-3">
								<div class="flex items-start justify-between gap-3">
									<div class="min-w-0"><h4 class="truncate text-sm font-medium text-[var(--color-ink-1)]">{item.model_name}</h4><p class="text-xs text-[var(--color-ink-3)]">{item.provider ?? t('unknown')}</p></div>
									<span class="shrink-0 text-sm font-semibold tabular-nums text-[var(--color-ink-1)]">{t('tokenCount', { tokens: formatNumber(item.total_tokens) })}</span>
								</div>
								<dl class="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
									<div><dt class="text-[var(--color-ink-3)]">{t('inputOutput')}</dt><dd class="mt-0.5 tabular-nums text-[var(--color-ink-2)]">{formatNumber(item.prompt_tokens)} / {formatNumber(item.completion_tokens)}</dd></div>
									<div><dt class="text-[var(--color-ink-3)]">{t('requests')}</dt><dd class="mt-0.5 tabular-nums text-[var(--color-ink-2)]">{formatNumber(item.request_count)}</dd></div>
									<div><dt class="text-[var(--color-ink-3)]">{t('credits')}</dt><dd class="mt-0.5 tabular-nums text-[var(--color-ink-2)]">{formatDecimal(item.credited_cost, 2)}</dd></div>
									<div><dt class="text-[var(--color-ink-3)]">{t('cost')}</dt><dd class="mt-0.5 tabular-nums text-[var(--color-ink-2)]">${formatDecimal(item.raw_cost)}</dd></div>
								</dl>
							</article>
						{/each}
						{#if detail.by_model.length === 0}<EmptyState headline={t('noRecords')} class="py-4 [&_.motion-enter]:animate-none" />{/if}
					</div>
				</section>

				<section class="mt-6" aria-labelledby="usage-ledger-title">
					<h3 id="usage-ledger-title" class="mb-2 text-sm font-semibold text-[var(--color-ink-1)]">{t('ledger')}</h3>
					<div class="hidden md:block">
						<TableShell density="compact">
							<table>
								<thead><tr><th>{t('time')}</th><th>{t('source')}</th><th>{t('model')}</th><th>{t('input')}</th><th>{t('output')}</th><th>{t('total')}</th><th>{t('credits')}</th><th>{t('cost')}</th></tr></thead>
								<tbody>
									{#each detail.records as record (record.id)}
										<tr>
											<td class="whitespace-nowrap">{formatDate(record.created_at)}</td>
											<td><Pill tone="neutral" size="xs">{sourceLabel(record.source)}</Pill></td>
											<td><div class="font-medium text-[var(--color-ink-1)]">{record.model_name}</div><div class="text-xs text-[var(--color-ink-3)]">{record.provider ?? t('unknown')}{record.api_key_id ? t('apiKeySuffix', { id: String(record.api_key_id) }) : ''}</div></td>
											<td class="tabular-nums">{formatNumber(record.prompt_tokens)}</td>
											<td class="tabular-nums">{formatNumber(record.completion_tokens)}</td>
											<td class="tabular-nums">{formatNumber(record.total_tokens)}</td>
											<td class="tabular-nums">{formatDecimal(record.credited_cost, 2)}</td>
											<td class="tabular-nums">${formatDecimal(record.raw_cost)}</td>
										</tr>
									{/each}
									{#if detail.records.length === 0}<tr><td colspan="8"><EmptyState headline={t('noRecords')} class="py-4 [&_.motion-enter]:animate-none" /></td></tr>{/if}
								</tbody>
							</table>
						</TableShell>
					</div>
					<div class="grid gap-2 md:hidden">
						{#each detail.records as record (record.id)}
							<article class="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] p-3">
								<div class="flex items-start justify-between gap-3">
									<div class="min-w-0"><h4 class="truncate text-sm font-medium text-[var(--color-ink-1)]">{record.model_name}</h4><p class="truncate text-xs text-[var(--color-ink-3)]">{record.provider ?? t('unknown')}{record.api_key_id ? t('apiKeySuffix', { id: String(record.api_key_id) }) : ''}</p></div>
									<Pill tone="neutral" size="xs">{sourceLabel(record.source)}</Pill>
								</div>
								<p class="mt-2 text-xs text-[var(--color-ink-3)]">{formatDate(record.created_at)}</p>
								<dl class="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
									<div><dt class="text-[var(--color-ink-3)]">{t('inputOutput')}</dt><dd class="mt-0.5 tabular-nums text-[var(--color-ink-2)]">{formatNumber(record.prompt_tokens)} / {formatNumber(record.completion_tokens)}</dd></div>
									<div><dt class="text-[var(--color-ink-3)]">{t('totalTokens')}</dt><dd class="mt-0.5 tabular-nums text-[var(--color-ink-2)]">{formatNumber(record.total_tokens)}</dd></div>
									<div><dt class="text-[var(--color-ink-3)]">{t('credits')}</dt><dd class="mt-0.5 tabular-nums text-[var(--color-ink-2)]">{formatDecimal(record.credited_cost, 2)}</dd></div>
									<div><dt class="text-[var(--color-ink-3)]">{t('cost')}</dt><dd class="mt-0.5 tabular-nums text-[var(--color-ink-2)]">${formatDecimal(record.raw_cost)}</dd></div>
								</dl>
							</article>
						{/each}
						{#if detail.records.length === 0}<EmptyState headline={t('noRecords')} class="py-4 [&_.motion-enter]:animate-none" />{/if}
					</div>
					{#if detail.next_before_id}
						<div class="mt-3 flex justify-center"><Button variant="secondary" size="sm" disabled={loadingMore} ariaBusy={loadingMore} onclick={() => void load(false)}>{#if loadingMore}<ActivityIndicator size="xs" tone="ink" />{/if}{loadingMore ? t('loadingMore') : t('moreRecords')}</Button></div>
					{/if}
				</section>
			{/if}
		</div>
	</div>
</Modal>
