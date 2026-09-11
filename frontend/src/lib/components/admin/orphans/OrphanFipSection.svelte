<script lang="ts">
	import OrphanSection from './OrphanSection.svelte';
	import type { OrphanFipInfo } from '$lib/types/orphan';

	let {
		items,
		selected = $bindable(new Set<string>()),
		onCleanup,
	}: {
		items: OrphanFipInfo[];
		selected: Set<string>;
		onCleanup: () => void;
	} = $props();
</script>

<OrphanSection
	title="분리된 Floating IPs"
	{items}
	bind:selected
	emptyMessage="분리된 Floating IP 없음."
	{onCleanup}
>
	{#snippet headers()}
		<th class="text-left py-2 pr-4">주소</th>
		<th class="text-left py-2 pr-4">프로젝트</th>
		<th class="text-left py-2 pr-4">생성일</th>
		<th class="text-left py-2 pr-4">연령(일)</th>
		<th class="text-left py-2 pr-4">ID</th>
	{/snippet}
	{#snippet row(f)}
		<td class="py-2 pr-4 font-mono text-green-400">{f.address}</td>
		<td class="py-2 pr-4 text-ink-3 font-mono">{f.project_id?.slice(0, 8) ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2">{f.created_at?.slice(0, 10) ?? '-'}</td>
		<td class="py-2 pr-4 text-action-warm">{f.age_days}</td>
		<td class="py-2 pr-4 text-ink-3 font-mono">{f.id.slice(0, 8)}</td>
	{/snippet}
</OrphanSection>
