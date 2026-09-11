<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { api, ApiError } from '$lib/api/client';
	import { toast } from '$lib/stores/toast';
	import { formatStorage } from '$lib/utils/format';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';
	import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';

	interface TrashObject {
		trash_key: string;
		original_name: string;
		deleted_at: number;
		bytes: number;
		content_type?: string;
	}

	let {
		containerName,
		token,
		projectId,
		selectionEnabled = false,
	}: {
		containerName: string;
		token: string | undefined;
		projectId: string | undefined;
		selectionEnabled?: boolean;
	} = $props();

	let items = $state<TrashObject[]>([]);
	let loading = $state(true);
	let restoring = $state<string | null>(null);
	let purging = $state<string | null>(null);
	let busy = $state(false);
	const selection = createResourceSelection();

	async function load() {
		loading = true;
		try {
			items = await api.get<TrashObject[]>(
				`/api/v1/object-storage/${encodeURIComponent(containerName)}/trash`,
				token,
				projectId
			);
			selection.retain(items.map((item) => item.trash_key));
		} catch {
			items = [];
			selection.clear();
		} finally {
			loading = false;
		}
	}

	async function restore(trashKey: string, origName: string) {
		restoring = trashKey;
		try {
			const res = await api.post<{ restored_name: string }>(
				`/api/v1/object-storage/${encodeURIComponent(containerName)}/trash/restore`,
				{ trash_key: trashKey },
				token,
				projectId
			);
			selection.remove([trashKey]);
			await load();
			toast.success(`"${res.restored_name}" 복구 완료`);
		} catch (e) {
			toast.error('복구 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			restoring = null;
		}
	}

	async function purge(trashKey: string, origName: string) {
		if (!(await confirmDialog(`"${origName}"을(를) 영구 삭제합니다. 이 작업은 되돌릴 수 없습니다. 계속하시겠습니까?`))) return;
		purging = trashKey;
		try {
			await api.delete(
				`/api/v1/object-storage/${encodeURIComponent(containerName)}/trash/${encodeURIComponent(trashKey)}`,
				token,
				projectId
			);
			selection.remove([trashKey]);
			await load();
		} catch (e) {
			toast.error('영구 삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			purging = null;
		}
	}

	async function runBulk(action: 'restore' | 'purge') {
		const submitted = [...selection.ids];
		const requestContainer = containerName;
		const requestToken = token;
		const requestProject = projectId;
		if (submitted.length === 0) return;
		if (action === 'purge' && !(await confirmDialog(`${submitted.length}개 항목을 영구 삭제합니다. 이 작업은 되돌릴 수 없습니다. 계속하시겠습니까?`))) return;
		busy = true;
		const results = await executeBulkMutations(submitted, (trashKey) =>
			action === 'restore'
				? api.post(`/api/v1/object-storage/${encodeURIComponent(requestContainer)}/trash/restore`, { trash_key: trashKey }, requestToken, requestProject)
				: api.delete(`/api/v1/object-storage/${encodeURIComponent(requestContainer)}/trash/${encodeURIComponent(trashKey)}`, requestToken, requestProject)
		);
		if (containerName === requestContainer && projectId === requestProject) {
			selection.remove(results.filter((result) => result.ok).map((result) => result.id));
			await load();
		}
		const successCount = results.filter((result) => result.ok).length;
		const failureCount = results.length - successCount;
		const label = action === 'restore' ? '복구' : '영구 삭제';
		if (successCount) toast.success(`${successCount}개 ${label} 요청을 완료했습니다.`);
		if (failureCount) toast.error(`${failureCount}개 ${label}에 실패했습니다.`);
		busy = false;
	}
	$effect(() => {
		if (!selectionEnabled) selection.clear();
	});
	$effect(() => {
		const currentContainer = containerName;
		const currentProject = projectId;
		selection.clear();
		if (!currentContainer || !currentProject) {
			items = [];
			loading = false;
			return;
		}
		load();
	});
</script>

<div class="mt-2">
	{#if loading}
		<div class="text-ink-3 text-xs py-8 text-center">휴지통 목록 로딩 중...</div>
	{:else if items.length === 0}
		<div class="text-ink-3 text-xs py-12 text-center">휴지통이 비어 있습니다</div>
	{:else}
		<div class="text-xs text-ink-3 mb-2">총 {items.length}개 항목 — 보관 기간 내 복구 가능</div>
		{#if selectionEnabled}
			<div class="mb-2">
				<SelectionToolbar
					label="휴지통 오브젝트"
					ariaLabel="휴지통 오브젝트 전체 선택"
					checked={selection.count === items.length}
					indeterminate={selection.count > 0 && selection.count < items.length}
					selectedCount={selection.count}
					disabled={busy}
					onToggle={() => selection.toggleAll(items.map((item) => item.trash_key))}
				/>
			</div>
		{/if}
		<table class="w-full text-xs">
			<thead>
				<tr class="border-b border-line text-ink-2">
					{#if selectionEnabled}<th class="py-2 px-3 text-left font-medium w-10">선택</th>{/if}
					<th class="py-2 px-3 text-left font-medium">원본 파일명</th>
					<th class="py-2 px-3 text-left font-medium">삭제일</th>
					<th class="py-2 px-3 text-right font-medium">크기</th>
					<th class="py-2 px-3 text-right font-medium">액션</th>
				</tr>
			</thead>
			<tbody>
				{#each items as item (item.trash_key)}
					<tr class="resource-selection-surface border-b border-line/40 hover:bg-surface-sunken/20 transition-colors" data-selected={selectionEnabled && selection.has(item.trash_key)}>
						{#if selectionEnabled}
							<td class="py-2 px-3">
								<SelectionCheckbox
									checked={selection.has(item.trash_key)}
									disabled={busy}
									ariaLabel={`${item.original_name} 선택`}
									onclick={() => selection.toggle(item.trash_key)}
								/>
							</td>
						{/if}
						<td class="py-2 px-3 text-ink-2 font-mono truncate max-w-xs" title={item.original_name}>{item.original_name}</td>
						<td class="py-2 px-3 text-ink-2">
							{item.deleted_at
								? new Date(item.deleted_at * 1000).toLocaleDateString('ko-KR', {
										year: 'numeric',
										month: '2-digit',
										day: '2-digit',
									})
								: '—'}
						</td>
						<td class="py-2 px-3 text-ink-2 text-right">{item.bytes ? formatStorage(item.bytes / 1_073_741_824) : '—'}</td>
						<td class="py-2 px-3 text-right">
							<div class="flex gap-1.5 justify-end">
								<button onclick={() => restore(item.trash_key, item.original_name)} disabled={restoring === item.trash_key || busy} class="text-emerald-400 hover:text-emerald-300 disabled:text-ink-3 px-2 py-0.5 rounded border border-emerald-900 hover:border-emerald-700 disabled:border-line-2 transition-colors">{restoring === item.trash_key ? '복구 중...' : '복구'}</button>
								<button onclick={() => purge(item.trash_key, item.original_name)} disabled={purging === item.trash_key || busy} class="text-red-400 hover:text-red-300 disabled:text-ink-3 px-2 py-0.5 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors">{purging === item.trash_key ? '삭제 중...' : '영구 삭제'}</button>
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
		<p class="mt-2 text-xs text-ink-3">휴지통 항목도 스토리지 용량을 차지합니다. 필요 없는 항목은 영구 삭제하세요.</p>
		{#if selectionEnabled}
			<BulkSelectionOverlay
				count={selection.count}
				ariaLabel="선택한 휴지통 오브젝트 일괄 작업"
				busy={busy}
				actions={[
					{ key: 'restore', label: '복구', tone: 'success', onAction: () => runBulk('restore') },
					{ key: 'purge', label: '영구 삭제', tone: 'danger', onAction: () => runBulk('purge') },
				]}
				onClear={() => selection.clear()}
			/>
		{/if}
	{/if}
</div>
