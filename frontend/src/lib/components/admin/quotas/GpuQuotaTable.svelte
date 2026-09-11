<script lang="ts">
	import type { GpuQuota } from '$lib/types/quotas';
	import type { FlavorReconcileResponse } from '$lib/stores/adminQuotasController.svelte';

	let {
		rows,
		defaults,
		loading,
		error,
		hasAnyAlias,
		onSetLimit,
		onClear,
		reconcilePreview,
	}: {
		rows: GpuQuota[];
		defaults: Record<string, number>;
		loading: boolean;
		error: string;
		hasAnyAlias: boolean;
		onSetLimit: (alias: string, limit: number) => void;
		onClear: (alias: string) => void;
		reconcilePreview?: FlavorReconcileResponse | null;
	} = $props();
</script>

<div class="bg-surface-base border border-line rounded-xl p-6 mb-6">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-1">GPU Quota</h2>
	<p class="text-xs text-ink-3 mb-4">이 프로젝트의 GPU quota입니다. 개별 설정이 없으면 전체 기본값이 적용됩니다.</p>
	{#if error}<div class="text-red-400 text-xs mb-3">{error}</div>{/if}
	{#if loading}
		<div class="text-ink-3 text-sm">불러오는 중...</div>
	{:else if rows.length === 0 && !hasAnyAlias}
		<div class="text-ink-3 text-sm">GPU alias를 찾을 수 없습니다.</div>
	{:else}
		<table class="w-full text-sm">
			<thead>
				<tr class="text-ink-2 text-xs border-b border-line">
					<th class="text-left pb-2">GPU 타입</th>
					<th class="text-right pb-2">기본값</th>
					<th class="text-right pb-2">프로젝트 Limit</th>
					<th class="text-right pb-2">사용 중</th>
					<th class="text-right pb-2">가용</th>
					<th class="text-right pb-2"></th>
				</tr>
			</thead>
			<tbody>
				{#each rows as q}
					{@const alias = q.gpu_type}
					{@const defLimit = defaults[alias] ?? 0}
					{@const effectiveLimit = q.limit}
					{@const inUse = q.in_use}
					{@const avail = effectiveLimit === -1 ? -1 : effectiveLimit - inUse}
					<tr class="border-b border-line/50 last:border-0">
						<td class="py-2 text-ink-0 font-mono">{alias}</td>
						<td class="py-2 text-right text-ink-3">{defLimit === -1 ? '무제한' : defLimit}</td>
						<td class="py-2 text-right">
							<input
								type="number"
								min="-1"
								value={q?.limit ?? ''}
								placeholder={String(defLimit)}
								onchange={(e) => {
									const v = (e.target as HTMLInputElement).value;
									if (v === '') {
										onClear(alias);
									} else {
										onSetLimit(alias, Number(v));
									}
								}}
								class="w-20 bg-surface-selected border border-line-2 rounded px-2 py-1 text-sm text-ink-0 text-right focus:outline-none focus:border-action-warm"
							/>
						</td>
						<td class="py-2 text-right text-ink-2">{inUse}</td>
						<td class="py-2 text-right {avail > 0 ? 'text-green-400' : avail === -1 ? 'text-ink-3' : 'text-red-400'}">
							{effectiveLimit === -1 ? '무제한' : avail}
						</td>
						<td class="py-2 text-right">
							{#if q?.limit != null}
								<button
									onclick={() => onClear(alias)}
									class="text-xs text-ink-3 hover:text-ink-2 transition-colors"
									title="프로젝트별 설정 삭제 (기본값으로 복귀)"
								>초기화</button>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
		<p class="text-xs text-ink-3 mt-2">빈 칸 = 기본값 사용, -1 = 무제한, 0 = 사용 불가</p>

		{#if reconcilePreview && reconcilePreview.operations.length > 0}
			<div class="mt-6 border-t border-[var(--color-line)] pt-4">
				<h3 class="text-xs font-semibold text-[var(--color-ink-1)] uppercase tracking-wide mb-1">
					Quota 연동 Flavor 권한 상태
				</h3>
				<p class="text-xs text-[var(--color-ink-2)] mb-3">
					설정된 GPU limit에 따라 프로젝트에 부여되거나 회수될 Nova Flavor Access 계획입니다.
				</p>
				<div class="space-y-1.5">
					{#each reconcilePreview.operations as op}
						<div class="flex items-center justify-between rounded-lg bg-[var(--color-surface-sunken)] px-3 py-2 text-xs">
							<div class="flex items-center gap-2">
								<span class="font-mono text-[var(--color-ink-0)]">{op.flavor_name}</span>
								{#if op.action === 'add'}
									<span class="rounded bg-[var(--color-surface-base)] text-[var(--color-state-success-text)] border border-[var(--color-state-success)]/40 px-1.5 py-0.5 text-[10px]">권한 추가 예정</span>
								{:else if op.action === 'remove'}
									<span class="rounded bg-[var(--color-surface-base)] text-[var(--color-state-danger-text)] border border-[var(--color-state-danger)]/40 px-1.5 py-0.5 text-[10px]">권한 회수 예정</span>
								{:else}
									<span class="rounded bg-[var(--color-surface-base)] text-[var(--color-ink-2)] px-1.5 py-0.5 text-[10px]">권한 유지</span>
								{/if}
							</div>
							<span class="text-[var(--color-ink-2)] font-mono">
								{Object.entries(op.gpu_demand).map(([k, v]) => `${k} ×${v}`).join(', ')}
							</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<div class="mt-4 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-sunken)] p-3 text-xs text-[var(--color-ink-2)] leading-relaxed">
			<strong class="text-[var(--color-ink-1)] font-medium">쿼터 적용 범위 안내:</strong>
			Afterglow GPU quota 및 단기 예약은 대시보드와 Afterglow 생성 요청을 보호합니다. 이미 Flavor 접근 권한이 부여된 프로젝트의 CLI 또는 직접 Nova API 생성은 Nova 자체 쿼터 한계가 적용됩니다.
		</div>
	{/if}
</div>
