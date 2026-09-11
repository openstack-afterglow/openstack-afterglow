<script lang="ts">
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';

	interface Props {
		showHost?: boolean;
	}

	let { showHost = false }: Props = $props();

	const s = useInstanceDetailController();
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">기본 정보</h2>
	<dl class="grid grid-cols-1 @3xl/panel:grid-cols-2 gap-x-8 gap-y-3">
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">ID</dt>
			<dd class="text-sm text-ink-2 font-mono">{s.instance!.id}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">생성일</dt>
			<dd class="text-sm text-ink-2">{s.formatDate(s.instance!.created_at)}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">이미지</dt>
			<dd class="text-sm text-ink-2">{s.instance!.image_name ?? s.instance!.image_id ?? '볼륨에서 부팅'}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">플레이버</dt>
			<dd class="text-sm text-ink-2">{s.instance!.flavor_name ?? s.instance!.flavor_id ?? '-'}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">키페어</dt>
			<dd class="text-sm text-ink-2 font-mono">{s.instance!.key_name ?? '-'}</dd>
		</div>
		{#if showHost && s.instance!.host}
			<div>
				<dt class="text-xs text-ink-3 mb-0.5">호스트</dt>
				<dd class="text-sm text-ink-2 font-mono">{s.instance!.host}</dd>
			</div>
		{/if}
		{#if s.ownerDisplay}
			<div class="overflow-hidden">
				<dt class="text-xs text-ink-3 mb-0.5">생성자</dt>
				<dd class="text-sm text-ink-2 font-mono truncate max-w-full" title={s.ownerDisplay}>{s.ownerDisplay}</dd>
			</div>
		{/if}
		<div class="col-span-2">
			<dt class="text-xs text-ink-3 mb-1.5">IP 주소</dt>
			<dd class="flex flex-col gap-1.5">
				{#if s.fixedIpsList.length === 0 && s.floatingIpsList.length === 0}
					<span class="text-sm text-ink-3">-</span>
				{/if}
				{#each s.fixedIpsList as fip}
					{@const paired = s.floatingIpsList.find(fl => fl.network_name === fip.network_name)}
					<div class="flex items-center gap-1.5 flex-wrap">
						<span class="text-sm font-mono text-ink-2 bg-surface-sunken px-2 py-0.5 rounded">{fip.addr}</span>
						<span class="text-xs text-ink-3 bg-surface-sunken px-1.5 py-0.5 rounded">fixed</span>
						{#if paired}
							<span class="text-sm font-mono text-green-300 bg-surface-sunken px-2 py-0.5 rounded">{paired.addr}</span>
							<span class="text-xs text-green-500 bg-green-900/20 px-1.5 py-0.5 rounded">floating</span>
						{/if}
						{#if fip.network_name}
							<span class="text-xs text-ink-3">{fip.network_name}</span>
						{/if}
					</div>
				{/each}
			</dd>
		</div>
	</dl>
</div>
