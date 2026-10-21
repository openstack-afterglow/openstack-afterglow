<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { onDestroy, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import type { PagedResponse, User } from '$lib/types/common';
	import {
		formatCredit,
		isCreditInput,
		type UserQuota,
		type UserQuotaList
	} from '$lib/api/chatQuotas';
	import UserUsageDetailModal from '$lib/components/admin/chat/UserUsageDetailModal.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { t } from '$lib/i18n/ns/chat-studio';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
	import { t as domainT } from '$lib/i18n/ns/domain-admin';
	let { domainId }: { domainId: string } = $props();
	let alive = true;

	interface DisplayUser {
		id: string;
		name: string;
		email: string;
	}

	interface QuotaRow {
		user: DisplayUser;
		quota: UserQuota | null;
	}

	function emptyQuotaList(): UserQuotaList {
		return {
			default_monthly_credit_limit: null,
			default_weekly_credit_limit: null,
			credit_policy: {
				credit_per_usd: '1000',
				usd_per_credit: '0.001',
				formula: ''
			},
			items: []
		};
	}

	const USER_PAGE_SIZE = 20;

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const userId = $derived($auth.userId ?? undefined);
	let users = $state<User[]>([]);
	let userMarker = $state<string | null>(null);
	let userMarkerStack = $state<(string | null)[]>([]);
	let nextUserMarker = $state<string | null>(null);
	let quotaList = $state<UserQuotaList>(emptyQuotaList());
	let loading = $state(true);
	let error = $state('');
	let search = $state('');
	let editingRow = $state<QuotaRow | null>(null);
	let usageRow = $state<QuotaRow | null>(null);
	let monthlyDraft = $state('');
	let weeklyDraft = $state('');
	let monthlyError = $state('');
	let weeklyError = $state('');
	let saving = $state(false);
	let defaultDraft = $state('');
	let defaultError = $state('');
	let savingDefault = $state(false);
	let resettingUserId = $state<string | null>(null);
	let loadGeneration = 0;
	let loadScopeKey = '';

	const rows = $derived.by(() => {
		const quotaByUser = new Map(quotaList.items.map((quota) => [quota.user_id, quota]));
		const query = search.trim().toLowerCase();
		return users
			.map((user): QuotaRow => ({
				user,
				quota: quotaByUser.get(user.id) ?? null
			}))
			.filter((row) => !query || [row.user.id, row.user.name, row.user.email].some((value) => value.toLowerCase().includes(query)))
			.sort((left, right) => left.user.name.localeCompare(right.user.name));
	});

	function monthlyLimit(row: QuotaRow): string | null {
		return row.quota?.monthly_credit_limit ?? quotaList.default_monthly_credit_limit;
	}

	function weeklyLabel(row: QuotaRow): string {
		const weekly = row.quota?.weekly_credit_limit ?? quotaList.default_weekly_credit_limit;
		if (weekly !== null && Number(weekly) > 0) return formatCredit(weekly);
		return monthlyLimit(row) !== null ? t('adminQuotas.weeklyWithinMonthly') : t('adminQuotas.unlimited');
	}

	function monthlyUsesDefault(row: QuotaRow): boolean {
		return !row.quota || row.quota.monthly_limit_source === 'default';
	}

	function weeklyUsesDefault(row: QuotaRow): boolean {
		return !row.quota || row.quota.weekly_limit_source === 'default';
	}

	function canReset(row: QuotaRow): boolean {
		return Boolean(row.quota && (!monthlyUsesDefault(row) || !weeklyUsesDefault(row)));
	}

	async function loadUsers(marker: string | null): Promise<PagedResponse<User>> {
		let url = `/api/v1/admin/users?domain_id=${encodeURIComponent(domainId)}&limit=${USER_PAGE_SIZE}`;
		if (marker) url += `&marker=${encodeURIComponent(marker)}`;
		return api.get<PagedResponse<User>>(url, token, projectId);
	}

	async function loadAll(marker: string | null = userMarker): Promise<boolean> {
		const generation = ++loadGeneration;
		if (!alive || !token || !domainId) {
			loading = false;
			return false;
		}
		loading = true;
		error = '';
		try {
			const [nextUsers, nextQuotas] = await Promise.all([
				loadUsers(marker),
				api.get<UserQuotaList>('/api/v1/chat/admin/quotas', token, projectId)
			]);
			if (generation !== loadGeneration) return false;
			if (nextUsers.items.some(user => user.domain_id !== domainId)) throw new Error(domainT('users.loadFailed'));
			users = nextUsers.items ?? [];
			userMarker = marker;
			nextUserMarker = nextUsers.next_marker ?? null;
			quotaList = nextQuotas;
			defaultDraft = nextQuotas.default_monthly_credit_limit ?? '';
			return true;
		} catch (caught) {
			if (generation === loadGeneration) {
				error = caught instanceof ApiError ? caught.message : t('adminQuotas.loadFailed');
			}
			return false;
		} finally {
			if (generation === loadGeneration) loading = false;
		}
	}

	async function nextPage() {
		if (!nextUserMarker || loading) return;
		const previousMarker = userMarker;
		if (await loadAll(nextUserMarker)) {
			userMarkerStack = [...userMarkerStack, previousMarker];
		}
	}

	async function previousPage() {
		if (userMarkerStack.length === 0 || loading) return;
		const previousMarker = userMarkerStack.at(-1) ?? null;
		if (await loadAll(previousMarker)) {
			userMarkerStack = userMarkerStack.slice(0, -1);
		}
	}

	async function saveDefaultQuota() {
		if (!alive || !token || savingDefault) return;
		defaultError = defaultDraft && !isCreditInput(defaultDraft)
			? t('adminQuotas.invalidCredit')
			: '';
		if (defaultError) return;
		savingDefault = true;
		try {
			await api.put(
				'/api/v1/chat/admin/quotas/defaults',
				{ monthly_credit_limit: defaultDraft || null },
				token,
				projectId
			);
			if (!alive) return;
			await loadAll();
			if (alive) toast.success(t('adminQuotas.defaultSaved'));
		} catch (caught) {
			if (alive) toast.error(caught instanceof ApiError ? caught.message : t('adminQuotas.defaultSaveFailed'));
		} finally {
			savingDefault = false;
		}
	}

	function openEditor(row: QuotaRow) {
		editingRow = row;
		if (row.quota?.monthly_limit_source === 'user') {
			monthlyDraft = row.quota.configured_monthly_credit_limit ?? '';
		} else {
			monthlyDraft = monthlyLimit(row) ?? '';
		}
		weeklyDraft = row.quota?.weekly_limit_source === 'user'
			? row.quota.configured_weekly_credit_limit ?? ''
			: '';
		monthlyError = '';
		weeklyError = '';
	}

	function closeEditor() {
		if (saving) return;
		editingRow = null;
		monthlyError = '';
		weeklyError = '';
	}

	async function saveQuota() {
		if (!alive || !editingRow || !token || saving) return;
		monthlyError = monthlyDraft && !isCreditInput(monthlyDraft)
			? t('adminQuotas.invalidCredit')
			: '';
		weeklyError = weeklyDraft && !isCreditInput(weeklyDraft)
			? t('adminQuotas.invalidCredit')
			: '';
		if (!monthlyError && monthlyDraft && weeklyDraft && Number(weeklyDraft) > Number(monthlyDraft)) {
			weeklyError = t('adminQuotas.weeklyExceedsMonthly');
		}
		if (monthlyError || weeklyError) return;

		saving = true;
		try {
			const updated = await api.put<UserQuota>(
				`/api/v1/chat/admin/quotas/${encodeURIComponent(editingRow.user.id)}`,
				{
					monthly_credit_limit: monthlyDraft || null,
					weekly_credit_limit: weeklyDraft || null
				},
				token,
				projectId
			);
			if (!alive) return;
			quotaList = {
				...quotaList,
				items: [...quotaList.items.filter((quota) => quota.user_id !== updated.user_id), updated]
			};
			editingRow = null;
			toast.success(t('adminQuotas.saved'));
		} catch (caught) {
			if (alive) toast.error(caught instanceof ApiError ? caught.message : t('adminQuotas.saveFailed'));
		} finally {
			saving = false;
		}
	}

	async function resetQuota(row: QuotaRow) {
		if (!alive || !token || !canReset(row) || resettingUserId !== null) return;
		if (!(await confirmDialog(t('adminQuotas.resetConfirm', { name: row.user.name })))) return;
		if (!alive) return;
		resettingUserId = row.user.id;
		try {
			const updated = await api.delete<UserQuota>(
				`/api/v1/chat/admin/quotas/${encodeURIComponent(row.user.id)}`,
				token,
				projectId
			);
			if (!alive) return;
			quotaList = {
				...quotaList,
				items: [...quotaList.items.filter((quota) => quota.user_id !== updated.user_id), updated]
			};
			toast.success(t('adminQuotas.resetSuccess'));
		} catch (caught) {
			if (alive) toast.error(caught instanceof ApiError ? caught.message : t('adminQuotas.resetFailed'));
		} finally {
			resettingUserId = null;
		}
	}

	$effect(() => {
		void token;
		const nextScopeKey = JSON.stringify([userId ?? null, projectId ?? null, domainId]);
		const scopeChanged = loadScopeKey !== nextScopeKey;
		if (scopeChanged) {
			loadScopeKey = nextScopeKey;
			untrack(() => {
				userMarker = null;
				userMarkerStack = [];
				nextUserMarker = null;
				users = [];
				quotaList = emptyQuotaList();
				defaultDraft = '';
			});
		}
		const marker = scopeChanged ? null : untrack(() => userMarker);
		if (scopeChanged || !untrack(() => loading)) {
			void untrack(() => loadAll(marker));
		}
	});
	onDestroy(() => { alive = false; loadGeneration += 1; });
</script>

	{#snippet creditRateSecondary(text: string)}<span class="text-[var(--color-ink-3)]">{text}</span>{/snippet}
<PageShell>
	<PageHeader
		breadcrumb={t('adminQuotas.breadcrumb')}
		title={t('adminQuotas.title')}
		subtitle={t('adminQuotas.subtitle')}
	/>

	<Alert tone="info" title={t('adminQuotas.creditCostTitle')} class="mb-4">
		<p>
			<RichText segments={t.rich('adminQuotas.creditRate', { credits: Number(quotaList.credit_policy.credit_per_usd).toLocaleString(intlLocale()), usd: Number(quotaList.credit_policy.usd_per_credit).toLocaleString(intlLocale(), { maximumFractionDigits: 8 }) })} tags={{ secondary: creditRateSecondary }} />
		</p>
		<p class="mt-1 text-sm">
			{t('adminQuotas.creditFormula')}
		</p>
	</Alert>

	{#if error}
		<Alert class="mb-4">{error}</Alert>
	{/if}

	<section class="mb-5 rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-base)] p-4" aria-labelledby="default-quota-title">
		<div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
			<div class="max-w-2xl">
				<h2 id="default-quota-title" class="text-base font-semibold text-[var(--color-ink-1)]">{t('adminQuotas.defaultTitle')}</h2>
				<p class="mt-1 break-keep text-sm text-[var(--color-ink-3)]">{t('adminQuotas.defaultHelp')}</p>
			</div>
			<form class="flex w-full flex-col gap-2 sm:flex-row lg:w-auto lg:min-w-[28rem]" onsubmit={(event) => { event.preventDefault(); void saveDefaultQuota(); }}>
				<Field label={t('adminQuotas.defaultMonthlyLabel')} for="default-monthly-quota" error={defaultError || undefined} class="min-w-0 flex-1">
					<TextInput id="default-monthly-quota" inputmode="decimal" placeholder={t('adminQuotas.unlimitedPlaceholder')} bind:value={defaultDraft} />
				</Field>
				<Button type="submit" variant="accent" disabled={savingDefault || loading} ariaBusy={savingDefault}>{#if savingDefault}<ActivityIndicator size="xs" tone="ink" />{/if}{savingDefault ? t('adminQuotas.saving') : t('adminQuotas.saveDefault')}</Button>
			</form>
		</div>
	</section>

	<div class="mb-4 max-w-xl">
		<Field label={t('adminQuotas.searchLabel')} for="quota-user-search" help={t('adminQuotas.searchHelp')}>
			<TextInput id="quota-user-search" type="search" placeholder={t('adminQuotas.searchPlaceholder')} bind:value={search} />
		</Field>
	</div>

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else}
		<ResponsiveTable>
			{#snippet cards()}
				{#each rows as row (row.user.id)}
					<CompactResourceCard>
						<div data-user-id={row.user.id}><p class="font-medium">{row.user.name}</p>{#if row.user.email}<p class="text-xs text-ink-2">{row.user.email}</p>{/if}</div>
						<dl class="grid grid-cols-2 gap-2 tabular-nums"><div><dt>{t('adminQuotas.monthlyUsage')}</dt><dd>{formatCredit(row.quota?.month_credited_cost ?? '0', '0')}</dd></div><div><dt>{t('adminQuotas.monthlyLimit')}</dt><dd>{formatCredit(monthlyLimit(row), t('adminQuotas.unlimited'))}</dd><dd><Pill tone={monthlyUsesDefault(row) ? 'neutral' : 'info'} size="xs">{t(monthlyUsesDefault(row) ? 'adminQuotas.default' : 'adminQuotas.personal')}</Pill></dd></div></dl>
						{#snippet details()}<p class="font-mono break-all">{row.user.id}</p><dl class="grid grid-cols-2 gap-2 tabular-nums"><div><dt>{t('adminQuotas.weeklyUsage')}</dt><dd>{formatCredit(row.quota?.week_credited_cost ?? '0', '0')}</dd></div><div><dt>{t('adminQuotas.weeklyLimit')}</dt><dd>{weeklyLabel(row)}</dd><dd><Pill tone={weeklyUsesDefault(row) ? 'neutral' : 'info'} size="xs">{t(weeklyUsesDefault(row) ? 'adminQuotas.default' : 'adminQuotas.personal')}</Pill></dd></div></dl>{/snippet}
						{#snippet actions()}<Button size="sm" variant="secondary" onclick={() => (usageRow = row)}>{t('adminQuotas.usage')}</Button><Button size="sm" variant="secondary" onclick={() => openEditor(row)}>{t('adminQuotas.edit')}</Button><Button size="sm" variant="ghost" disabled={!canReset(row) || resettingUserId === row.user.id} ariaBusy={resettingUserId === row.user.id} onclick={() => void resetQuota(row)}>{#if resettingUserId === row.user.id}<ActivityIndicator size="xs" tone="ink" />{/if}{resettingUserId === row.user.id ? t('adminQuotas.resetting') : t('adminQuotas.resetDefault')}</Button>{/snippet}
					</CompactResourceCard>
				{:else}<EmptyState headline={t('adminQuotas.empty')} class="py-4 [&_.motion-enter]:animate-none" />{/each}
			{/snippet}
		<TableShell>
			<table class="quota-table">
				<thead>
					<tr>
						<th>{t('adminQuotas.user')}</th>
						<th>{t('adminQuotas.monthlyLimit')}</th>
						<th>{t('adminQuotas.monthlyUsage')}</th>
						<th>{t('adminQuotas.weeklyLimit')}</th>
						<th>{t('adminQuotas.weeklyUsage')}</th>
						<th>{t('adminQuotas.actions')}</th>
					</tr>
				</thead>
				<tbody>
					{#each rows as row (row.user.id)}
						<tr data-user-id={row.user.id}>
							<td class="user-cell" title={row.user.id}>
								<div class="flex items-center gap-2">
									<span class="font-medium text-[var(--color-ink-1)]">{row.user.name}</span>
								</div>
								{#if row.user.email}<div class="text-xs text-[var(--color-ink-3)]">{row.user.email}</div>{/if}
							</td>
							<td data-label={t('adminQuotas.monthlyLimit')}>
								<div class="flex items-center gap-2 tabular-nums">
									{formatCredit(monthlyLimit(row), t('adminQuotas.unlimited'))}
									{#if monthlyUsesDefault(row)}<Pill tone="neutral" size="xs">{t('adminQuotas.default')}</Pill>{:else}<Pill tone="info" size="xs">{t('adminQuotas.personal')}</Pill>{/if}
								</div>
							</td>
							<td data-label={t('adminQuotas.monthlyUsage')}>
								<button type="button" class="tabular-nums text-[var(--color-accent)] hover:underline" onclick={() => (usageRow = row)} aria-label={t('adminQuotas.viewMonthlyUsage', { name: row.user.name })}>
									{formatCredit(row.quota?.month_credited_cost ?? '0', '0')}
								</button>
							</td>
							<td data-label={t('adminQuotas.weeklyLimit')}>
								<div class="flex items-center gap-2">
									<span class="tabular-nums">{weeklyLabel(row)}</span>
									{#if weeklyUsesDefault(row)}<Pill tone="neutral" size="xs">{t('adminQuotas.default')}</Pill>{:else}<Pill tone="info" size="xs">{t('adminQuotas.personal')}</Pill>{/if}
								</div>
							</td>
							<td data-label={t('adminQuotas.weeklyUsage')}>
								<button type="button" class="tabular-nums text-[var(--color-accent)] hover:underline" onclick={() => (usageRow = row)} aria-label={t('adminQuotas.viewWeeklyUsage', { name: row.user.name })}>
									{formatCredit(row.quota?.week_credited_cost ?? '0', '0')}
								</button>
							</td>
							<td class="actions-cell" data-label={t('adminQuotas.actions')}>
								<div class="flex flex-wrap gap-2">
									<Button size="sm" variant="secondary" onclick={() => (usageRow = row)}>{t('adminQuotas.usage')}</Button>
									<Button size="sm" variant="secondary" onclick={() => openEditor(row)}>{t('adminQuotas.edit')}</Button>
									<Button size="sm" variant="ghost" disabled={!canReset(row) || resettingUserId === row.user.id} ariaBusy={resettingUserId === row.user.id} onclick={() => void resetQuota(row)}>{#if resettingUserId === row.user.id}<ActivityIndicator size="xs" tone="ink" />{/if}{resettingUserId === row.user.id ? t('adminQuotas.resetting') : t('adminQuotas.resetDefault')}</Button>
								</div>
							</td>
						</tr>
					{/each}
					{#if rows.length === 0}
						<tr><td colspan="6"><EmptyState headline={t('adminQuotas.empty')} class="py-4 [&_.motion-enter]:animate-none" /></td></tr>
					{/if}
				</tbody>
			</table>
		</TableShell>
		</ResponsiveTable>
		<Pagination
			page={userMarkerStack.length + 1}
			hasPrev={userMarkerStack.length > 0}
			hasNext={nextUserMarker !== null}
			onPrev={() => void previousPage()}
			onNext={() => void nextPage()}
			note={t('adminQuotas.usersShown', { count: users.length })}
		/>
	{/if}
</PageShell>

<Modal open={editingRow !== null} onClose={closeEditor} dismissible={!saving} ariaLabel={t('adminQuotas.editorAriaLabel')}>
	{#if editingRow}
		<form
			class="max-h-[calc(100dvh-2rem)] w-[min(30rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-5 shadow-[var(--shadow-restraint)]"
			onsubmit={(event) => {
				event.preventDefault();
				void saveQuota();
			}}
		>
			<h2 class="text-base font-semibold text-[var(--color-ink-1)]">{t('adminQuotas.editorTitle')}</h2>
			<p class="mt-1 text-sm text-[var(--color-ink-2)]">{editingRow.user.name}</p>
			<div class="mt-5 space-y-4">
				<Field label={t('adminQuotas.personalMonthlyLabel')} for="user-monthly-quota" help={t('adminQuotas.personalMonthlyHelp')} error={monthlyError || undefined}>
					<TextInput id="user-monthly-quota" inputmode="decimal" placeholder={t('adminQuotas.unlimitedPlaceholder')} bind:value={monthlyDraft} />
				</Field>
				<Field label={t('adminQuotas.personalWeeklyLabel')} for="user-weekly-quota" help={t('adminQuotas.personalWeeklyHelp')} error={weeklyError || undefined}>
					<TextInput id="user-weekly-quota" inputmode="decimal" placeholder={t('adminQuotas.weeklyPlaceholder')} bind:value={weeklyDraft} />
				</Field>
			</div>
			<div class="mt-5 flex justify-end gap-2">
				<Button type="button" variant="ghost" onclick={closeEditor} disabled={saving}>{t('adminQuotas.cancel')}</Button>
				<Button type="submit" variant="accent" disabled={saving} ariaBusy={saving}>{#if saving}<ActivityIndicator size="xs" tone="ink" />{/if}{saving ? t('adminQuotas.saving') : t('adminQuotas.save')}</Button>
			</div>
		</form>
	{/if}
</Modal>

<UserUsageDetailModal open={usageRow !== null} user={usageRow?.user ?? null} onClose={() => (usageRow = null)} />

