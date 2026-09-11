<script lang="ts">
	import type { OrphanKind, CleanupResult } from '$lib/types/orphan';
	type Kind = OrphanKind;

	let {
		kind,
		ids,
		cleaning,
		cleanupError,
		cleanupResult,
		onConfirm,
		onClose,
	}: {
		kind: Kind | null;
		ids: string[];
		cleaning: boolean;
		cleanupError: string;
		cleanupResult: CleanupResult | null;
		onConfirm: () => void;
		onClose: () => void;
	} = $props();

	const KIND_LABELS: Record<Kind, string> = {
		floating_ip: 'Floating IP',
		volume: 'Volume',
		manila_share: 'Manila Share',
		security_group: 'Security Group',
	};
</script>

{#if kind}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={(event) => { if (event.target === event.currentTarget) (onClose)(); }}
		role="dialog"
		onkeydown={(e) => e.key === 'Escape' && onClose()}
		tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-lg mx-4 shadow-[var(--shadow-restraint)]"
			role="document"
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-3">
				{KIND_LABELS[kind]} 정리 ({ids.length}개)
			</h2>

			{#if !cleanupResult}
				<p class="text-sm text-ink-2 mb-4">
					아래 ID 목록을 OpenStack에서 삭제합니다. 이 작업은 되돌릴 수 없습니다.
				</p>
				<div class="bg-surface-canvas border border-line rounded-lg p-3 mb-4 max-h-48 overflow-y-auto">
					<ul class="text-xs font-mono text-ink-2 space-y-0.5">
						{#each ids as id}
							<li>{id}</li>
						{/each}
					</ul>
				</div>
				{#if kind === 'volume'}
					<p class="text-xs text-action-warm mb-3">
						※ 삭제 직전 재조회로 attachments / status를 한 번 더 검증합니다(race 방지).
					</p>
				{:else if kind === 'manila_share'}
					<p class="text-xs text-action-warm mb-3">
						※ 삭제 직전 재조회로 (1) project 복구 여부 (2) snapshot 부재 (3) status를 검증합니다.
					</p>
				{:else if kind === 'security_group'}
					<p class="text-xs text-action-warm mb-3">
						※ 삭제 직전 모든 port를 재조회해 attach가 발생하지 않았는지, marker가 유지되는지 검증합니다.
					</p>
				{/if}
				{#if cleanupError}
					<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">
						{cleanupError}
					</div>
				{/if}
				<div class="flex justify-end gap-3">
					<button
						onclick={onClose}
						class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg"
					>
						취소
					</button>
					<button
						onclick={onConfirm}
						disabled={cleaning}
						class="px-4 py-2 bg-red-600 hover:bg-red-500 text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30"
					>
						{cleaning ? '정리 중...' : '정리'}
					</button>
				</div>
			{:else}
				<div class="space-y-3 mb-4">
					<div class="text-sm text-green-400">
						성공: {cleanupResult.deleted.length}개
					</div>
					{#if cleanupResult.deleted.length > 0}
						<details class="bg-surface-canvas border border-line rounded-lg p-3">
							<summary class="text-xs text-ink-2 cursor-pointer">삭제된 ID 보기</summary>
							<ul class="text-xs font-mono text-ink-2 mt-2 space-y-0.5 max-h-32 overflow-y-auto">
								{#each cleanupResult.deleted as id}
									<li>{id}</li>
								{/each}
							</ul>
						</details>
					{/if}
					<div class="text-sm {cleanupResult.failed.length > 0 ? 'text-red-400' : 'text-ink-3'}">
						실패: {cleanupResult.failed.length}개
					</div>
					{#if cleanupResult.failed.length > 0}
						<div class="bg-red-900/20 border border-red-800 rounded-lg p-3 max-h-48 overflow-y-auto">
							<ul class="text-xs space-y-1.5">
								{#each cleanupResult.failed as f}
									<li>
										<span class="font-mono text-red-300">{f.id.slice(0, 8)}</span>
										<span class="text-red-400 ml-2">{f.error}</span>
									</li>
								{/each}
							</ul>
						</div>
					{/if}
				</div>
				<div class="flex justify-end">
					<button
						onclick={onClose}
						class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg"
					>
						닫기
					</button>
				</div>
			{/if}
		</div>
	</div>
{/if}
