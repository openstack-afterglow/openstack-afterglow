<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { Volume } from '$lib/types/volume';

	let { volume, onclose, onsuccess }: {
		volume: Volume | null;
		onclose: () => void;
		onsuccess: () => void;
	} = $props();

	let newSize = $state(0);
	let extending = $state(false);
	let error = $state('');

	$effect(() => {
		if (volume) {
			newSize = volume.size + 10;
			error = '';
		}
	});

	async function confirmExtend() {
		if (!volume) return;
		if (newSize <= volume.size) {
			error = `새 크기(${newSize}GB)는 현재 크기(${volume.size}GB)보다 커야 합니다`;
			return;
		}
		extending = true;
		error = '';
		try {
			await api.post(
				`/api/v1/volumes/${volume.id}/extend`,
				{ new_size: newSize },
				$auth.token ?? undefined,
				$auth.projectId ?? undefined,
			);
			onsuccess();
		} catch (e) {
			error = e instanceof ApiError ? e.message : '볼륨 확장 실패';
		} finally {
			extending = false;
		}
	}
</script>

{#if volume}
<div
	class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
	onclick={onclose}
	role="dialog"
	aria-modal="true"
	tabindex="-1"
	onkeydown={(e) => e.key === 'Escape' && onclose()}
>
	<div
		class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
		onclick={(e) => e.stopPropagation()}
		role="none"
		onkeydown={(e) => e.stopPropagation()}
	>
		<h2 class="text-lg font-semibold text-ink-0 mb-5">볼륨 용량 확장</h2>
		<div class="space-y-4">
			<div>
				<div class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">볼륨</div>
				<div class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-2 text-sm">
					{volume.name || volume.id.slice(0, 8)} <span class="text-ink-3">({volume.status})</span>
				</div>
			</div>
			<div>
				<div class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">현재 크기</div>
				<div class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-2 text-sm font-mono">
					{volume.size} GB
				</div>
			</div>
			<div>
				<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">
					새 크기 (GB) — 최소 {volume.size + 1}GB
					<input
						bind:value={newSize}
						type="number"
						min={volume.size + 1}
						step="10"
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm mt-1.5"
					/>
				</label>
			</div>
		</div>
		{#if error}<div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>{/if}
		<div class="flex justify-end gap-3 mt-6">
			<button onclick={onclose} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">취소</button>
			<button
				onclick={confirmExtend}
				disabled={extending || newSize <= volume.size}
				class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors"
			>{extending ? '확장 중...' : '확장'}</button>
		</div>
	</div>
</div>
{/if}
