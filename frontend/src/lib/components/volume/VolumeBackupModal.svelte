<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { Volume } from '$lib/types/volume';

	let { volume, onclose, onsuccess }: {
		volume: Volume | null;
		onclose: () => void;
		onsuccess: () => void;
	} = $props();

	let name = $state('');
	let description = $state('');
	let incremental = $state(false);
	let creating = $state(false);
	let error = $state('');

	function defaultName(vol: Volume): string {
		const now = new Date();
		const pad = (n: number) => String(n).padStart(2, '0');
		const ts = `${now.getFullYear()}${pad(now.getMonth()+1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`;
		return `${vol.name || vol.id.slice(0, 8)}-backup-${ts}`;
	}

	$effect(() => {
		if (volume) {
			name = defaultName(volume);
			description = '';
			incremental = false;
			error = '';
		}
	});

	async function createBackup() {
		if (!volume) return;
		creating = true;
		error = '';
		try {
			await api.post(
				'/api/v1/volumes/backups',
				{ volume_id: volume.id, name, description: description || null, incremental },
				$auth.token ?? undefined,
				$auth.projectId ?? undefined,
			);
			onsuccess();
		} catch (e) {
			error = e instanceof ApiError ? e.message : '백업 생성 실패';
		} finally {
			creating = false;
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
		<h2 class="text-lg font-semibold text-ink-0 mb-5">볼륨 백업 생성</h2>
		<div class="space-y-4">
			<div>
				<div class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">볼륨</div>
				<div class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-2 text-sm">
					{volume.name || volume.id.slice(0, 8)} <span class="text-ink-3">({volume.size} GB)</span>
				</div>
			</div>
			<div>
				<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">백업 이름
					<input
						bind:value={name}
						type="text"
						placeholder="my-backup"
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5"
					/>
				</label>
			</div>
			<div>
				<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">설명 (선택)
					<input
						bind:value={description}
						type="text"
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5"
					/>
				</label>
			</div>
			<div class="flex items-center gap-2">
				<input type="checkbox" id="backup-incremental" bind:checked={incremental} class="rounded border-line-2" />
				<label for="backup-incremental" class="text-sm text-ink-2">증분 백업</label>
			</div>
		</div>
		{#if error}<div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>{/if}
		<div class="flex justify-end gap-3 mt-6">
			<button onclick={onclose} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">취소</button>
			<button
				onclick={createBackup}
				disabled={creating || !name.trim()}
				class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors"
			>{creating ? '생성 중...' : '백업 생성'}</button>
		</div>
	</div>
</div>
{/if}
