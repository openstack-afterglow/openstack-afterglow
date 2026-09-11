<script lang="ts">
	import OrphanSection from './OrphanSection.svelte';
	import type { OrphanShareInfo } from '$lib/types/orphan';

	let {
		items,
		selected = $bindable(new Set<string>()),
		onCleanup,
	}: {
		items: OrphanShareInfo[];
		selected: Set<string>;
		onCleanup: () => void;
	} = $props();
</script>

<OrphanSection
	title="고아 Manila Share"
	{items}
	bind:selected
	emptyMessage="Keystone 프로젝트가 사라진 share 없음."
	{onCleanup}
>
	{#snippet headers()}
		<th class="text-left py-2 pr-4">이름</th>
		<th class="text-left py-2 pr-4">크기(GB)</th>
		<th class="text-left py-2 pr-4">상태</th>
		<th class="text-left py-2 pr-4">사라진 프로젝트</th>
		<th class="text-left py-2 pr-4">생성일</th>
		<th class="text-left py-2 pr-4">연령(일)</th>
		<th class="text-left py-2 pr-4">ID</th>
	{/snippet}
	{#snippet row(s)}
		<td class="py-2 pr-4 text-ink-1">{s.name ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2 font-mono">{s.size_gb}</td>
		<td class="py-2 pr-4 text-green-400">{s.status}</td>
		<td class="py-2 pr-4 text-ink-3 font-mono">{s.project_id?.slice(0, 8) ?? '-'}</td>
		<td class="py-2 pr-4 text-ink-2">{s.created_at?.slice(0, 10) ?? '-'}</td>
		<td class="py-2 pr-4 text-action-warm">{s.age_days}</td>
		<td class="py-2 pr-4 text-ink-3 font-mono">{s.id.slice(0, 8)}</td>
	{/snippet}
</OrphanSection>
