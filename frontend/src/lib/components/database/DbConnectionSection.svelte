<script lang="ts">
	import { useDbInstanceDetailController } from '$lib/stores/dbInstanceDetailController.svelte';

	const s = useDbInstanceDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<h2 class="text-sm font-semibold text-ink-0 mb-3">연결 정보</h2>
	<div class="space-y-2 text-sm">
		<div class="flex gap-4">
			<div class="flex-1">
				<div class="text-ink-3 text-xs mb-0.5">호스트</div>
				{#if s.instance!.address_map && Object.keys(s.instance!.address_map).length > 0}
					<div class="space-y-0.5">
						{#each Object.entries(s.instance!.address_map) as [netName, addrs]}
							{#each addrs ?? [] as addr}
								<div class="text-ink-0 font-mono text-sm">
									<span class="text-ink-2 text-xs mr-1.5">{netName}:</span>{addr}
								</div>
							{/each}
						{/each}
					</div>
				{:else if (s.instance!.ips?.length ?? 0) > 0}
					<div class="space-y-0.5">
						{#each s.instance!.ips ?? [] as addr}
							<div class="text-ink-0 font-mono text-sm">{addr}</div>
						{/each}
					</div>
				{:else}
					<div class="text-ink-3 font-mono">-</div>
				{/if}
			</div>
			<div><div class="text-ink-3 text-xs mb-0.5">포트</div><div class="text-ink-0 font-mono">{s.dbPort}</div></div>
		</div>

		<!-- 공개 IP (Floating IP) -->
		<div>
			<div class="text-ink-3 text-xs mb-1">공개 IP (Floating)</div>
			{#if s.instanceFips.length > 0}
				<div class="flex flex-wrap items-center gap-2">
					{#each s.instanceFips as fip}
						<span class="text-emerald-400 font-mono text-sm bg-emerald-950/40 border border-emerald-800/50 px-2 py-0.5 rounded">{fip.floating_ip_address}</span>
					{/each}
					<button onclick={() => s.detachFip(false)} disabled={s.detachingFip}
						class="text-ink-2 hover:text-ink-1 disabled:text-ink-3 text-xs px-2 py-0.5 rounded border border-line-2 hover:border-line-2 transition-colors">
						{s.detachingFip ? '...' : '해제'}
					</button>
					<button onclick={() => s.detachFip(true)} disabled={s.detachingFip}
						class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-0.5 rounded border border-red-900 hover:border-red-700 transition-colors">
						{s.detachingFip ? '...' : '삭제'}
					</button>
				</div>
			{:else if s.instance!.status === 'BUILD' || s.instance!.status === 'BUILDING'}
				<div class="flex items-center gap-2 text-sm text-yellow-400">
					<svg class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
					<span class="text-xs">인스턴스 생성 중... Floating IP는 완료 후 자동 할당됩니다.</span>
				</div>
			{:else}
				<div class="flex items-center gap-2">
					<span class="text-ink-3 text-sm">미할당</span>
					<button onclick={() => s.attachFip()} disabled={s.attachingFip || !s.instance!.ip}
						class="text-action-warm hover:text-action-warm-hover disabled:text-ink-3 text-xs px-2 py-0.5 rounded border border-action-warm hover:border-action-warm transition-colors">
						{s.attachingFip ? '할당 중...' : '+ 공개 IP 할당'}
					</button>
				</div>
			{/if}
			{#if s.fipError}<p class="text-red-400 text-xs mt-1">{s.fipError}</p>{/if}
		</div>

		{#if s.connectCmd}
			<div>
				<div class="text-ink-3 text-xs mb-1">연결 명령어 예시</div>
				<code class="block bg-surface-sunken rounded px-3 py-2 text-xs text-green-400 font-mono break-all">{s.connectCmd}</code>
			</div>
		{/if}

		{#if s.rootInfo}
			<div class="bg-amber-950/30 border border-action-warm rounded-lg px-3 py-2">
				<div class="text-action-warm text-xs font-medium mb-1">root 계정 활성화됨</div>
				<div class="font-mono text-xs text-ink-0">사용자: {s.rootInfo.name}</div>
				<div class="font-mono text-xs text-ink-0">비밀번호: {s.rootInfo.password}</div>
			</div>
		{:else}
			<button onclick={() => s.enableRoot()} disabled={s.enablingRoot}
				class="text-xs text-action-warm border border-action-warm hover:border-action-warm px-3 py-1.5 rounded transition-colors">
				{s.enablingRoot ? 'root 활성화 중...' : 'root 유저 활성화'}
			</button>
		{/if}
	</div>
</div>
