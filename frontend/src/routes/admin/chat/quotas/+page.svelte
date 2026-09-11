<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { toast } from '$lib/stores/toast';
	import type { User } from '$lib/types/common';
	import {
		formatCredit,
		isCreditInput,
		type UserQuota,
		type UserQuotaList
	} from '$lib/api/chatQuotas';
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

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	let users = $state<User[]>([]);
	let quotaList = $state<UserQuotaList>({ default_monthly_credit_limit: '0', items: [] });
	let loading = $state(true);
	let error = $state('');
	let search = $state('');
	let editingRow = $state<QuotaRow | null>(null);
	let monthlyDraft = $state('');
	let weeklyDraft = $state('');
	let monthlyError = $state('');
	let weeklyError = $state('');
	let saving = $state(false);
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
		} catch (caught) {
			if (generation === loadGeneration) {
				error = caught instanceof ApiError ? caught.message : '쿼터 조회 실패';
				users = [];
				quotaList = { default_monthly_credit_limit: '0', items: [] };
			}
		} finally {
			if (generation === loadGeneration) loading = false;
		}
	}

	function openEditor(row: QuotaRow) {
		editingRow = row;
		// 지갑이 없는 사용자는 envelope 기본 월 한도가 실제 상한이다. 빈 값으로 열면 주간만 바꾸려던
		// 저장이 monthly_credit_limit=null 을 보내 기본 상한을 무제한으로 승격시킨다.
		const defaultMonthly = quotaList.default_monthly_credit_limit;
		const fallbackMonthly = isCreditInput(defaultMonthly) ? defaultMonthly : '';
		monthlyDraft = row.quota?.monthly_credit_limit ?? fallbackMonthly;
		weeklyDraft = row.quota?.weekly_credit_limit ?? '';
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
			toast.success('쿼터를 저장했습니다');
		} catch (caught) {
			toast.error(caught instanceof ApiError ? caught.message : '쿼터 저장 실패');
		} finally {
			saving = false;
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
		subtitle="사용자별 월간·주간 크레딧 한도를 설정합니다. 비워두면 무제한입니다."
	/>

	{#if error}
		<Alert class="mb-4">{error}</Alert>
	{/if}

	<div class="mb-4 max-w-xl">
		<Field label="사용자 검색" for="quota-user-search" help="이름, 이메일 또는 사용자 ID로 검색합니다.">
			<TextInput id="quota-user-search" type="search" placeholder="사용자 검색" bind:value={search} />
		</Field>
	</div>

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else}
		<TableShell>
			<table>
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
							<td title={row.user.id}>
								<div class="flex items-center gap-2">
									<span class="font-medium text-[var(--color-ink-1)]">{row.user.name}</span>
									{#if row.orphan}<Pill tone="warning" size="xs">미확인 사용자</Pill>{/if}
								</div>
								{#if row.user.email}<div class="text-xs text-[var(--color-ink-3)]">{row.user.email}</div>{/if}
							</td>
							<td>
								<div class="flex items-center gap-2 tabular-nums">
									{formatCredit(row.quota?.monthly_credit_limit ?? quotaList.default_monthly_credit_limit)}
									{#if !row.quota}<Pill tone="neutral" size="xs">기본값</Pill>{/if}
								</div>
							</td>
							<td class="tabular-nums">{formatCredit(row.quota?.month_credited_cost ?? '0', '0')}</td>
							<td class="tabular-nums">{formatCredit(row.quota?.weekly_credit_limit ?? null)}</td>
							<td class="tabular-nums">{formatCredit(row.quota?.week_credited_cost ?? '0', '0')}</td>
							<td><Button size="sm" variant="secondary" onclick={() => openEditor(row)}>편집</Button></td>
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
			<h2 class="text-base font-semibold text-[var(--color-ink-1)]">사용자 쿼터 편집</h2>
			<p class="mt-1 text-sm text-[var(--color-ink-2)]">{editingRow.user.name}</p>
			<div class="mt-5 space-y-4">
				<Field label="월 한도(크레딧)" for="user-monthly-quota" help="비워두면 무제한" error={monthlyError || undefined}>
					<TextInput id="user-monthly-quota" inputmode="decimal" bind:value={monthlyDraft} />
				</Field>
				<Field label="주간 한도(크레딧)" for="user-weekly-quota" help="비워두면 무제한" error={weeklyError || undefined}>
					<TextInput id="user-weekly-quota" inputmode="decimal" bind:value={weeklyDraft} />
				</Field>
			</div>
			<div class="mt-5 flex justify-end gap-2">
				<Button type="button" variant="ghost" onclick={closeEditor} disabled={saving}>취소</Button>
				<Button type="submit" variant="accent" disabled={saving}>{saving ? '저장 중…' : '저장'}</Button>
			</div>
		</form>
	{/if}
</Modal>
