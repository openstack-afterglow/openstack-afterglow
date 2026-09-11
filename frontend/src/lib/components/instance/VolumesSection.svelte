<script lang="ts">
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';

	const s = useInstanceDetailController();

	let showAttachVolume = $state(false);
	let attachMode = $state<'existing' | 'new'>('existing');
	let selectedVolumeId = $state('');
	let newVolName = $state('');
	let newVolSize = $state(20);

	async function handleAttachVolume() {
		await s.attachVolume(selectedVolumeId);
		showAttachVolume = false;
		selectedVolumeId = '';
	}

	async function handleCreateAndAttach() {
		await s.createAndAttachVolume(newVolName.trim(), newVolSize);
		showAttachVolume = false;
		newVolName = '';
		newVolSize = 20;
	}
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<div class="flex items-center justify-between mb-4">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide">볼륨</h2>
		<button
			onclick={() => { showAttachVolume = !showAttachVolume; selectedVolumeId = ''; newVolName = ''; newVolSize = 20; }}
			class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
		>
			{showAttachVolume ? '닫기' : '+ 볼륨 연결'}
		</button>
	</div>

	{#if showAttachVolume}
		<div class="mb-4 bg-surface-sunken rounded-lg p-4">
			<div class="flex gap-1 mb-3">
				<button
					onclick={() => { attachMode = 'existing'; }}
					class="text-xs px-2 py-1 rounded border transition-colors {attachMode === 'existing' ? 'text-action-warm border-action-warm bg-surface-selected/20' : 'text-ink-2 border-line-2 hover:text-ink-1'}"
				>
					기존 볼륨
				</button>
				<button
					onclick={() => { attachMode = 'new'; }}
					class="text-xs px-2 py-1 rounded border transition-colors {attachMode === 'new' ? 'text-action-warm border-action-warm bg-surface-selected/20' : 'text-ink-2 border-line-2 hover:text-ink-1'}"
				>
					새 볼륨 생성
				</button>
			</div>

			{#if attachMode === 'existing'}
				{#if s.availableVolumes.length === 0}
					<p class="text-sm text-ink-3">연결 가능한 볼륨이 없습니다. "새 볼륨 생성"을 이용하세요.</p>
				{:else}
					<div class="flex gap-2">
						<select
							bind:value={selectedVolumeId}
							class="flex-1 bg-surface-selected border border-line-2 text-ink-1 text-sm rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
						>
							<option value="">볼륨 선택...</option>
							{#each s.availableVolumes as vol}
								<option value={vol.id}>{vol.name || vol.id.slice(0, 8)} ({vol.size}GB)</option>
							{/each}
						</select>
						<button
							onclick={handleAttachVolume}
							disabled={!selectedVolumeId || s.actioning === 'attach-vol'}
							class="text-xs text-action-warm hover:text-action-warm-hover px-3 py-1.5 border border-action-warm hover:border-action-warm rounded transition-colors disabled:text-ink-3 disabled:border-line-2"
						>
							{s.actioning === 'attach-vol' ? '연결 중...' : '연결'}
						</button>
					</div>
				{/if}
			{:else}
				<div class="space-y-2">
					<div class="flex gap-2">
						<input
							bind:value={newVolName}
							type="text"
							placeholder="볼륨 이름"
							class="flex-1 bg-surface-selected border border-line-2 text-ink-1 text-sm rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
						/>
						<input
							bind:value={newVolSize}
							type="number"
							min="1"
							placeholder="크기(GB)"
							class="w-24 bg-surface-selected border border-line-2 text-ink-1 text-sm rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
						/>
						<button
							onclick={handleCreateAndAttach}
							disabled={!newVolName.trim() || newVolSize < 1 || s.actioning === 'create-vol'}
							class="text-xs text-green-400 hover:text-green-300 px-3 py-1.5 border border-green-900 hover:border-green-700 rounded transition-colors disabled:text-ink-3 disabled:border-line-2 whitespace-nowrap"
						>
							{s.actioning === 'create-vol' ? '생성 중...' : '생성 및 연결'}
						</button>
					</div>
				</div>
			{/if}
		</div>
	{/if}

	{#if s.volumes.length === 0}
		<p class="text-sm text-ink-3">연결된 볼륨 없음</p>
	{:else}
		<div class="space-y-2">
			{#each s.volumes as vol}
				<div class="flex items-center justify-between bg-surface-sunken/50 rounded px-3 py-2">
					<div class="flex items-center gap-4">
						<span class="text-xs font-mono text-action-warm hover:text-action-warm-hover">
							<a href="/dashboard/volumes/{vol.volume_id}">{vol.name || vol.volume_id.slice(0, 12) + '...'}</a>
						</span>
						{#if vol.size}
							<span class="text-xs text-ink-3">{vol.size}GB</span>
						{/if}
						<span class="text-xs font-mono text-ink-3">{vol.device}</span>
						{#if vol.status}
							<span class="text-xs {vol.status === 'in-use' ? 'text-green-400' : 'text-ink-2'}">{vol.status}</span>
						{/if}
						<button
							type="button"
							onclick={() => s.setDeleteOnTermination(vol.volume_id, !vol.delete_on_termination)}
							disabled={s.actioning === 'dot-' + vol.volume_id}
							title="클릭해서 토글"
							class="text-[10px] px-1.5 py-0.5 rounded transition-colors disabled:opacity-50 cursor-pointer
								{vol.delete_on_termination
									? 'text-red-300 bg-red-900/30 hover:bg-red-900/50 border border-red-800/50'
									: 'text-ink-2 bg-surface-sunken hover:bg-surface-selected border border-line-2'}"
						>
							{s.actioning === 'dot-' + vol.volume_id
								? '변경 중...'
								: vol.delete_on_termination
									? '인스턴스 삭제 시 자동 삭제'
									: '유지'}
						</button>
					</div>
					<button
						onclick={() => s.detachVolume(vol.volume_id)}
						disabled={s.actioning === 'detach-' + vol.volume_id}
						class="text-xs text-orange-400 hover:text-orange-300 px-2 py-1 border border-orange-900 hover:border-orange-700 rounded transition-colors disabled:text-ink-3"
					>
						{s.actioning === 'detach-' + vol.volume_id ? '분리 중...' : '분리'}
					</button>
				</div>
			{/each}
		</div>
	{/if}
</div>
