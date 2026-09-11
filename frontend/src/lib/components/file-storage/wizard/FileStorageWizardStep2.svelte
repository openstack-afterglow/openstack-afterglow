<script lang="ts">
	import { useFsWizard } from '$lib/stores/fileStorageWizardStore.svelte';

	const s = useFsWizard();
</script>

<h2 class="text-base font-semibold text-ink-0 mb-1">네트워크 설정</h2>
<div class="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-blue-950/30 border border-action-warm/40 text-action-warm text-xs mb-4">
	<svg class="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
		<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
	</svg>
	<span>현재 환경(DHSS=False 드라이버)에서는 Share Network 없이 파일 스토리지가 생성됩니다. Share Network 선택은 선택 사항이며 실제로 사용되지 않습니다.</span>
</div>
<div class="space-y-4">
	<div>
		{#if s.fsForm.share_proto === 'CEPHFS'}
			<div class="bg-surface-sunken/40 border border-line-2 rounded-lg px-3 py-2.5 text-xs text-ink-3">
				CephFS native 프로토콜은 Share Network 없이 직접 마운트됩니다.
			</div>
		{:else}
			<div class="flex items-center justify-between mb-1.5">
				<span class="text-xs text-ink-2 uppercase tracking-wide">Share Network {s.fsForm.share_proto === 'NFS' ? '*' : '(선택)'}</span>
				<button type="button" onclick={() => { s.showInlineNetCreate = !s.showInlineNetCreate; s.inlineNetError = ''; }}
					class="text-xs text-action-warm hover:text-action-warm-hover transition-colors">
					{s.showInlineNetCreate ? '접기' : '+ 새로 생성'}
				</button>
			</div>
			{#if s.shareNetworks.length > 0}
				<select bind:value={s.selectedNetworkId} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm">
					<option value="">기본값 사용{s.fsForm.share_proto === 'NFS' ? '' : ' (권장)'}</option>
					{#each s.shareNetworks as net}<option value={net.id}>{net.name || net.id.slice(0, 8)}{net.status ? ` (${net.status})` : ''}</option>{/each}
				</select>
			{:else if !s.showInlineNetCreate}
				<div class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-3 text-sm">
					Share Network 없음 —
					<button onclick={() => (s.showInlineNetCreate = true)} class="text-action-warm hover:text-action-warm-hover underline">지금 생성</button>
				</div>
			{/if}
		{/if}
	</div>

	{#if s.showInlineNetCreate}
		<div class="border border-line-2 rounded-lg p-4 bg-surface-sunken/40 space-y-3">
			<p class="text-xs text-ink-2 font-medium uppercase tracking-wide">새 Share Network 생성</p>
			<div>
				<label class="block text-xs text-ink-3 mb-1">이름 *
					<input bind:value={s.inlineNetForm.name} type="text" placeholder="my-share-network"
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1" />
				</label>
			</div>
			<div>
				<label class="block text-xs text-ink-3 mb-1">설명 (선택)
					<input bind:value={s.inlineNetForm.description} type="text" placeholder="설명"
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1" />
				</label>
			</div>
			<div>
				<label class="block text-xs text-ink-3 mb-1">Neutron 네트워크 *
					<select bind:value={s.inlineNetForm.neutron_net_id} onchange={s.onInlineNetworkChange}
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1">
						<option value="">네트워크 선택</option>
						{#each s.neutronNetworks as net}<option value={net.id}>{net.name || net.id.slice(0, 12)} ({net.status})</option>{/each}
					</select>
				</label>
			</div>
			<div>
				<label class="block text-xs text-ink-3 mb-1">서브넷 *
					{#if s.loadingSubnets}
						<div class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-3 text-sm mt-1">로딩 중...</div>
					{:else}
						<select bind:value={s.inlineNetForm.neutron_subnet_id} disabled={s.subnets.length === 0}
							class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1 disabled:text-ink-3">
							<option value="">{s.subnets.length === 0 ? '네트워크를 먼저 선택하세요' : '서브넷 선택'}</option>
							{#each s.subnets as subnet}<option value={subnet.id}>{subnet.name || subnet.id.slice(0, 12)} {subnet.cidr ? `(${subnet.cidr})` : ''}</option>{/each}
						</select>
					{/if}
				</label>
			</div>
			{#if s.inlineNetError}<div class="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{s.inlineNetError}</div>{/if}
			<div class="flex justify-end gap-2">
				<button onclick={() => { s.showInlineNetCreate = false; s.inlineNetError = ''; }} class="px-3 py-1.5 text-xs text-ink-2 hover:text-ink-0 transition-colors">취소</button>
				<button onclick={s.createInlineNetwork} disabled={s.inlineNetCreating || !s.inlineNetForm.name.trim() || !s.inlineNetForm.neutron_net_id || !s.inlineNetForm.neutron_subnet_id}
					class="px-4 py-1.5 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-xs font-medium rounded-lg transition-colors">
					{s.inlineNetCreating ? '생성 중...' : 'Share Network 생성'}
				</button>
			</div>
		</div>
	{/if}
</div>

{#if s.wizardError}<div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{s.wizardError}</div>{/if}
<div class="flex justify-between gap-3 mt-6">
	<button onclick={s.backToStep1} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">← 이전</button>
	<div class="flex gap-3">
		<button onclick={s.closeWizard} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">취소</button>
		<button onclick={s.createFileStorage} disabled={s.creating}
			class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors">
			{s.creating ? '생성 중...' : '생성'}
		</button>
	</div>
</div>
