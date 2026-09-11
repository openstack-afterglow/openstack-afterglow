<script lang="ts">
	import type { Group } from '$lib/types/adminGroup';

	interface Props {
		target: Group | null;
		deleting: boolean;
		error: string;
		onConfirm: () => Promise<void>;
	}

	let { target = $bindable(), deleting, error, onConfirm }: Props = $props();
</script>

{#if target}
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={(event) => { if (event.target === event.currentTarget) (() => { target = null; })(); }}
		role="dialog"
		onkeydown={(e) => e.key === 'Escape' && (target = null)}
		tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]"
		>
			<h2 class="text-lg font-semibold text-ink-0 mb-3">그룹 삭제</h2>
			<p class="text-sm text-ink-2 mb-4"><span class="text-ink-0 font-medium">{target.name}</span> 그룹을 삭제하시겠습니까?</p>
			{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
			<div class="flex justify-end gap-3">
				<button onclick={() => { target = null; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={onConfirm} disabled={deleting} class="px-4 py-2 bg-red-600 hover:bg-red-500 text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{deleting ? '삭제 중...' : '삭제'}</button>
			</div>
		</div>
	</div>
{/if}
