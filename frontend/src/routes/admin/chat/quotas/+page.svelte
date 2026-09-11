<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import type { User } from '$lib/types/common';
	import {
		formatCredit,
		isCreditInput,
		type UserQuota,
		type UserQuotaList
	} from '$lib/api/chatQuotas';
	import UserUsageDetailModal from '$lib/components/admin/chat/UserUsageDetailModal.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';

	interface DisplayUser {
		id: string;
		name: string;
		email: string;
	}

	interface QuotaRow {
		user: DisplayUser;
		quota: UserQuota | null;
		orphan: boolean;
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

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	let users = $state<User[]>([]);
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

	const rows = $derived.by(() => {
		const quotaByUser = new Map(quotaList.items.map((quota) => [quota.user_id, quota]));
		const merged: QuotaRow[] = users.map((user) => ({
			user,
			quota: quotaByUser.get(user.id) ?? null,
			orphan: false
		}));
		const knownIds = new Set(users.map((user) => user.id));
		for (const quota of quotaList.items) {
			if (!knownIds.has(quota.user_id)) {
				merged.push({
					user: { id: quota.user_id, name: quota.user_id, email: '' },
					quota,
					orphan: true
				});
			}
		}
		const query = search.trim().toLowerCase();
		return merged
			.filter((row) => !query || [row.user.id, row.user.name, row.user.email].some((value) => value.toLowerCase().includes(query)))
			.sort((left, right) => left.user.name.localeCompare(right.user.name));
	});

	function monthlyLimit(row: QuotaRow): string | null {
		return row.quota?.monthly_credit_limit ?? quotaList.default_monthly_credit_limit;
	}

	function weeklyLabel(row: QuotaRow): string {
		const weekly = row.quota?.weekly_credit_limit ?? quotaList.default_weekly_credit_limit;
		if (weekly !== null && Number(weekly) > 0) return formatCredit(weekly);
		return monthlyLimit(row) !== null ? '월 한도 내 무제한' : '무제한';
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

	async function loadUsers(): Promise<User[]> {
		let marker: string | null = null;
		const collected: User[] = [];
		do {
			let url = '/api/v1/admin/users?limit=100';
			if (marker) url += `&marker=${encodeURIComponent(marker)}`;
			const response = await api.get<{ items: User[]; next_marker: string | null }>(
				url,
				token,
				projectId
			);
			collected.push(...(response.items ?? []));
			marker = response.next_marker ?? null;
		} while (marker);
		return collected;
	}

	async function loadAll() {
		if (!token) return;
		const generation = ++loadGeneration;
		loading = true;
		error = '';
		try {
			const [nextUsers, nextQuotas] = await Promise.all([
				loadUsers(),
				api.get<UserQuotaList>('/api/v1/chat/admin/quotas', token, projectId)
			]);
			if (generation !== loadGeneration) return;
			users = nextUsers;
			quotaList = nextQuotas;
			defaultDraft = nextQuotas.default_monthly_credit_limit ?? '';
		} catch (caught) {
			if (generation === loadGeneration) {
				error = caught instanceof ApiError ? caught.message : '쿼터 조회 실패';
				users = [];
				quotaList = emptyQuotaList();
				defaultDraft = '';
			}
		} finally {
			if (generation === loadGeneration) loading = false;
		}
	}

	async function saveDefaultQuota() {
		if (!token) return;
		defaultError = defaultDraft && !isCreditInput(defaultDraft)
			? '0보다 큰 숫자(소수 8자리 이하)를 입력하세요'
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
			await loadAll();
			toast.success('시스템 기본 월 한도를 저장했습니다');
		} catch (caught) {
			toast.error(caught instanceof ApiError ? caught.message : '기본 한도 저장 실패');
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
		if (!editingRow || !token) return;
		monthlyError = monthlyDraft && !isCreditInput(monthlyDraft)
			? '0보다 큰 숫자(소수 8자리 이하)를 입력하세요'
			: '';
		weeklyError = weeklyDraft && !isCreditInput(weeklyDraft)
			? '0보다 큰 숫자(소수 8자리 이하)를 입력하세요'
			: '';
		if (!monthlyError && monthlyDraft && weeklyDraft && Number(weeklyDraft) > Number(monthlyDraft)) {
			weeklyError = '주간 한도는 월 한도를 초과할 수 없습니다';
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
			quotaList = {
				...quotaList,
				items: [...quotaList.items.filter((quota) => quota.user_id !== updated.user_id), updated]
			};
			editingRow = null;
			toast.success('개인 쿼터를 저장했습니다');
		} catch (caught) {
			toast.error(caught instanceof ApiError ? caught.message : '쿼터 저장 실패');
		} finally {
			saving = false;
		}
	}

	async function resetQuota(row: QuotaRow) {
		if (!token || !canReset(row)) return;
		if (!(await confirmDialog(`${row.user.name} 사용자의 개인 쿼터를 시스템 기본값으로 되돌리시겠습니까?`))) return;
		resettingUserId = row.user.id;
		try {
			const updated = await api.delete<UserQuota>(
				`/api/v1/chat/admin/quotas/${encodeURIComponent(row.user.id)}`,
				token,
				projectId
			);
			quotaList = {
				...quotaList,
				items: [...quotaList.items.filter((quota) => quota.user_id !== updated.user_id), updated]
			};
			toast.success('시스템 기본값으로 되돌렸습니다');
		} catch (caught) {
			toast.error(caught instanceof ApiError ? caught.message : '기본값 복원 실패');
		} finally {
			resettingUserId = null;
		}
	}

	$effect(() => {
		void token;
		void projectId;
		untrack(() => void loadAll());
		return () => { loadGeneration += 1; };
	});
</script>

<div class="mx-auto min-w-0 max-w-7xl p-4 md:p-6">
	<PageHeader
		breadcrumb="AI 채팅 / 사용자 쿼터"
		title="사용자 쿼터"
		subtitle="시스템 기본 월 한도와 사용자별 월·주간 한도를 독립적으로 관리합니다. 주간 무제한도 월 한도를 벗어나지 않습니다."
	/>

	<Alert tone="info" title="크레딧 비용 산정" class="mb-4">
		<p>
			<strong>1 USD = {Number(quotaList.credit_policy.credit_per_usd).toLocaleString('en-US')} 크레딧</strong>
			<span class="text-[var(--color-ink-3)]"> · 1 크레딧 = ${quotaList.credit_policy.usd_per_credit}</span>
		</p>
		<p class="mt-1 text-sm">
			모델 원가 = 입력 토큰 × 입력 단가 + 출력 토큰 × 출력 단가 + 지원 도구 원가.
			차감 크레딧 = 모델 원가(USD) × 프로바이더 마진 배수 × 크레딧/USD.
		</p>
	</Alert>

	{#if error}
		<Alert class="mb-4">{error}</Alert>
	{/if}

	<section class="mb-5 rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-base)] p-4" aria-labelledby="default-quota-title">
		<div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
			<div class="max-w-2xl">
				<h2 id="default-quota-title" class="text-base font-semibold text-[var(--color-ink-1)]">시스템 전체 기본 한도</h2>
				<p class="mt-1 break-keep text-sm text-[var(--color-ink-3)]">개인 월 한도를 지정하지 않은 모든 사용자에게 즉시 적용됩니다. 비워두면 시스템 월 한도가 무제한입니다.</p>
			</div>
			<form class="flex w-full flex-col gap-2 sm:flex-row lg:w-auto lg:min-w-[28rem]" onsubmit={(event) => { event.preventDefault(); void saveDefaultQuota(); }}>
				<Field label="기본 월 한도(크레딧)" for="default-monthly-quota" error={defaultError || undefined} class="min-w-0 flex-1">
					<TextInput id="default-monthly-quota" inputmode="decimal" placeholder="비우면 무제한" bind:value={defaultDraft} />
				</Field>
				<Button type="submit" variant="accent" disabled={savingDefault || loading}>{savingDefault ? '저장 중…' : '기본값 저장'}</Button>
			</form>
		</div>
	</section>

	<div class="mb-4 max-w-xl">
		<Field label="사용자 검색" for="quota-user-search" help="이름, 이메일 또는 사용자 ID로 검색합니다.">
			<TextInput id="quota-user-search" type="search" placeholder="사용자 검색" bind:value={search} />
		</Field>
	</div>

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else}
		<TableShell>
			<table class="quota-table">
				<thead>
					<tr>
						<th>사용자</th>
						<th>월 한도</th>
						<th>이번 달 사용</th>
						<th>주간 한도</th>
						<th>이번 주 사용</th>
						<th>작업</th>
					</tr>
				</thead>
				<tbody>
					{#each rows as row (row.user.id)}
						<tr data-user-id={row.user.id}>
							<td class="user-cell" title={row.user.id}>
								<div class="flex items-center gap-2">
									<span class="font-medium text-[var(--color-ink-1)]">{row.user.name}</span>
									{#if row.orphan}<Pill tone="warning" size="xs">미확인 사용자</Pill>{/if}
								</div>
								{#if row.user.email}<div class="text-xs text-[var(--color-ink-3)]">{row.user.email}</div>{/if}
							</td>
							<td data-label="월 한도">
								<div class="flex items-center gap-2 tabular-nums">
									{formatCredit(monthlyLimit(row))}
									{#if monthlyUsesDefault(row)}<Pill tone="neutral" size="xs">기본값</Pill>{:else}<Pill tone="info" size="xs">개인</Pill>{/if}
								</div>
							</td>
							<td data-label="이번 달 사용">
								<button type="button" class="tabular-nums text-[var(--color-accent)] hover:underline" onclick={() => (usageRow = row)} aria-label={`${row.user.name} 월 사용량 보기`}>
									{formatCredit(row.quota?.month_credited_cost ?? '0', '0')}
								</button>
							</td>
							<td data-label="주간 한도">
								<div class="flex items-center gap-2">
									<span class="tabular-nums">{weeklyLabel(row)}</span>
									{#if weeklyUsesDefault(row)}<Pill tone="neutral" size="xs">기본값</Pill>{:else}<Pill tone="info" size="xs">개인</Pill>{/if}
								</div>
							</td>
							<td data-label="이번 주 사용">
								<button type="button" class="tabular-nums text-[var(--color-accent)] hover:underline" onclick={() => (usageRow = row)} aria-label={`${row.user.name} 주간 사용량 보기`}>
									{formatCredit(row.quota?.week_credited_cost ?? '0', '0')}
								</button>
							</td>
							<td class="actions-cell" data-label="작업">
								<div class="flex flex-wrap gap-2">
									<Button size="sm" variant="secondary" onclick={() => (usageRow = row)}>사용량</Button>
									<Button size="sm" variant="secondary" onclick={() => openEditor(row)}>편집</Button>
									<Button size="sm" variant="ghost" disabled={!canReset(row) || resettingUserId === row.user.id} onclick={() => void resetQuota(row)}>{resettingUserId === row.user.id ? '복원 중…' : '기본값 복원'}</Button>
								</div>
							</td>
						</tr>
					{/each}
					{#if rows.length === 0}
						<tr><td colspan="6" class="text-center text-[var(--color-ink-3)]">표시할 사용자가 없습니다.</td></tr>
					{/if}
				</tbody>
			</table>
		</TableShell>
	{/if}
</div>

<Modal open={editingRow !== null} onClose={closeEditor} dismissible={!saving} ariaLabel="사용자 쿼터 편집">
	{#if editingRow}
		<form
			class="max-h-[calc(100dvh-2rem)] w-[min(30rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-5 shadow-[var(--shadow-restraint)]"
			onsubmit={(event) => {
				event.preventDefault();
				void saveQuota();
			}}
		>
			<h2 class="text-base font-semibold text-[var(--color-ink-1)]">개인 쿼터 편집</h2>
			<p class="mt-1 text-sm text-[var(--color-ink-2)]">{editingRow.user.name}</p>
			<div class="mt-5 space-y-4">
				<Field label="개인 월 한도(크레딧)" for="user-monthly-quota" help="비워두면 개인 월 한도가 무제한입니다. 시스템 기본값을 다시 따르려면 기본값 복원을 사용하세요." error={monthlyError || undefined}>
					<TextInput id="user-monthly-quota" inputmode="decimal" placeholder="비우면 무제한" bind:value={monthlyDraft} />
				</Field>
				<Field label="개인 주간 한도(크레딧)" for="user-weekly-quota" help="비워두면 별도 주간 제한 없이 월 한도 내에서 사용할 수 있습니다." error={weeklyError || undefined}>
					<TextInput id="user-weekly-quota" inputmode="decimal" placeholder="비우면 월 한도 내 무제한" bind:value={weeklyDraft} />
				</Field>
			</div>
			<div class="mt-5 flex justify-end gap-2">
				<Button type="button" variant="ghost" onclick={closeEditor} disabled={saving}>취소</Button>
				<Button type="submit" variant="accent" disabled={saving}>{saving ? '저장 중…' : '저장'}</Button>
			</div>
		</form>
	{/if}
</Modal>

<UserUsageDetailModal open={usageRow !== null} user={usageRow?.user ?? null} onClose={() => (usageRow = null)} />

<style>
	@media (max-width: 1023px) {
		.quota-table,
		.quota-table tbody,
		.quota-table tr,
		.quota-table td {
			display: block;
			width: 100%;
		}
		.quota-table thead {
			display: none;
		}
		.quota-table tbody {
			display: grid;
			gap: 0.75rem;
		}
		.quota-table tr {
			overflow: hidden;
			border: 1px solid var(--color-line);
			border-radius: 0.75rem;
			background: var(--color-surface-base);
		}
		.quota-table td {
			display: flex;
			align-items: center;
			justify-content: space-between;
			gap: 1rem;
			border: 0;
			border-top: 1px solid var(--color-line);
		}
		.quota-table td::before {
			content: attr(data-label);
			flex-shrink: 0;
			color: var(--color-ink-3);
			font-size: 0.75rem;
			font-weight: 600;
		}
		.quota-table .user-cell {
			border-top: 0;
		}
		.quota-table .user-cell::before {
			display: none;
		}
		.quota-table .actions-cell {
			align-items: flex-start;
		}
	}
</style>
