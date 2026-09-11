<script lang="ts">
	import { useFsWizard } from '$lib/stores/fileStorageWizardStore.svelte';

	const s = useFsWizard();
</script>

<h2 class="text-base font-semibold text-ink-0 mb-4">파일 스토리지 기본 정보</h2>
<div class="space-y-4">
	<div>
		<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">이름 *
			<input bind:value={s.fsForm.name} type="text" placeholder="my-file-storage"
				class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
		</label>
	</div>
	<div>
		<span class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">크기 (GB)</span>
		<div class="flex gap-2 mb-2">
			{#each [10, 20, 50, 100] as preset}
				<button type="button" onclick={() => (s.fsForm.size_gb = preset)}
					class="flex-1 py-1.5 text-xs rounded-lg border transition-colors {s.fsForm.size_gb === preset ? 'border-action-warm bg-surface-selected/30 text-action-warm' : 'border-line-2 text-ink-2 hover:border-line-2'}">
					{preset} GB
				</button>
			{/each}
		</div>
		<input bind:value={s.fsForm.size_gb} type="number" min="1" placeholder="직접 입력"
			class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
	</div>
	<div>
		<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">Share Type
			{#if s.shareTypes.length > 0}
				<select bind:value={s.fsForm.share_type} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
					{#each s.shareTypes as st}<option value={st.name}>{st.name}{st.is_default ? ' (기본값)' : ''}</option>{/each}
				</select>
			{:else}
				<input bind:value={s.fsForm.share_type} type="text" placeholder="share type 이름"
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm font-mono mt-1.5" />
			{/if}
		</label>
	</div>
	<div>
		<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">프로토콜
			<select bind:value={s.fsForm.share_proto} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
				{#each s.allowedProtos as p (p)}
					<option value={p}>{p === 'CEPHFS' ? 'CephFS' : 'NFS'}</option>
				{/each}
			</select>
			{#if s.allowedProtos.length === 1 && s.currentShareType}
				<span class="block text-[10px] text-ink-3 mt-1">선택된 share type 이 {s.allowedProtos[0]} 만 지원합니다.</span>
			{/if}
		</label>
	</div>
	<div>
		<div class="flex items-center justify-between mb-2">
			<span class="block text-xs text-ink-2 uppercase tracking-wide">메타데이터 (선택)</span>
			<button type="button" onclick={s.addMeta} class="text-xs text-action-warm hover:text-action-warm-hover transition-colors">+ 추가</button>
		</div>
		<div class="space-y-2">
			{#each s.metaEntries as meta, i (i)}
				<div class="flex gap-2 items-center">
					<input bind:value={meta.key} type="text" placeholder="key"
						class="flex-1 bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-xs focus:outline-none focus:border-action-warm font-mono" />
					<span class="text-ink-3 text-xs">=</span>
					<input bind:value={meta.value} type="text" placeholder="value"
						class="flex-1 bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-xs focus:outline-none focus:border-action-warm font-mono" />
					<button type="button" onclick={() => s.removeMeta(i)} class="text-ink-3 hover:text-red-400 transition-colors text-xs px-1">✕</button>
				</div>
			{/each}
		</div>
	</div>
</div>
{#if s.wizardError}<div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{s.wizardError}</div>{/if}
<div class="flex justify-end gap-3 mt-6">
	<button onclick={s.closeWizard} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">취소</button>
	<button onclick={s.goStep2} disabled={s.creating}
		class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors">
		{s.creating ? '생성 중...' : (!s.dhssEnabled || s.fsForm.share_proto === 'CEPHFS') ? '생성' : '다음 →'}
	</button>
</div>
