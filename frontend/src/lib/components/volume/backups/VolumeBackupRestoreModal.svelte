<script lang="ts">
	import type { VolumeBackup } from '$lib/types/volume';

	let {
		open = $bindable(),
		backup,
		onRestore,
	}: {
		open: boolean;
		backup: VolumeBackup | null;
		onRestore: (backupId: string) => Promise<{ volume_id: string; volume_name: string } | string>;
	} = $props();

	let restoring = $state(false);
	let error = $state('');
	let result = $state<{ volume_id: string; volume_name: string } | null>(null);

	$effect(() => {
		if (!open) {
			error = '';
			result = null;
		}
	});

	async function restore() {
		if (!backup) return;
		restoring = true;
		error = '';
		const res = await onRestore(backup.id);
		restoring = false;
		if (typeof res === 'string') {
			error = res;
		} else {
			result = res;
		}
	}
</script>

{#if open && backup}
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={() => { open = false; }}
		role="dialog"
		aria-modal="true"
		tabindex="-1"
		onkeydown={(e) => e.key === 'Escape' && (open = false)}
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			{#if result}
				<h2 class="text-lg font-semibold text-ink-0 mb-4">복원 완료</h2>
				<div class="bg-surface-sunken rounded-lg p-4 mb-4 space-y-2">
					<div class="text-xs text-ink-2">복원된 볼륨 ID</div>
					<div class="text-sm text-ink-0 font-mono break-all">{result.volume_id}</div>
					{#if result.volume_name}
						<div class="text-xs text-ink-2 mt-2">볼륨 이름</div>
						<div class="text-sm text-ink-0">{result.volume_name}</div>
					{/if}
				</div>
				<p class="text-xs text-yellow-400 mb-4">원본 인스턴스와 동일한 라이브러리 셋으로 인스턴스를 생성하세요. 다른 라이브러리를 선택하면 파일 가시성이 달라질 수 있습니다.</p>
				<div class="flex justify-end gap-3">
					<button onclick={() => { open = false; }} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">닫기</button>
					<a href="/dashboard/instances/new?upper_volume_id={result.volume_id}" class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg transition-colors">이 볼륨으로 인스턴스 생성</a>
				</div>
			{:else}
				<h2 class="text-lg font-semibold text-ink-0 mb-4">백업 복원</h2>
				<p class="text-sm text-ink-2 mb-4">백업 <span class="text-ink-0 font-medium">"{backup.name || backup.id.slice(0, 8)}"</span>을 새 볼륨으로 복원합니다.</p>
				<p class="text-xs text-yellow-400 mb-4">복원 후 원본 인스턴스와 동일한 라이브러리 셋으로 인스턴스를 생성하세요.</p>
				{#if error}<div class="mt-2 mb-3 text-red-400 text-xs">{error}</div>{/if}
				<div class="flex justify-end gap-3 mt-2">
					<button onclick={() => { open = false; }} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">취소</button>
					<button onclick={restore} disabled={restoring} class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-ink-0 text-sm font-medium rounded-lg transition-colors">{restoring ? '복원 중...' : '복원'}</button>
				</div>
			{/if}
		</div>
	</div>
{/if}
