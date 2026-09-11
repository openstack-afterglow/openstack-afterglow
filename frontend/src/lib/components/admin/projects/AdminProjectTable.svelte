<script lang="ts">
	interface Project {
		id: string;
		name: string;
		description: string;
		enabled: boolean;
		domain_id: string | null;
		created_at: string | null;
	}

	let {
		projects,
		copiedId,
		onCopyId,
		onEdit,
		onAccess,
		onDelete,
	}: {
		projects: Project[];
		copiedId: string | null;
		onCopyId: (id: string) => void;
		onEdit: (p: Project) => void;
		onAccess: (p: Project) => void;
		onDelete: (p: Project) => void;
	} = $props();
</script>

<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				<th class="text-left py-2 pr-4">이름</th>
				<th class="text-left py-2 pr-4">설명</th>
				<th class="text-left py-2 pr-4">상태</th>
				<th class="text-left py-2 pr-4">ID</th>
				<th class="text-left py-2 pr-4">생성일</th>
				<th class="text-left py-2">액션</th>
			</tr>
		</thead>
		<tbody>
			{#each projects as p (p.id)}
				<tr class="border-b border-line/50 text-xs hover:bg-surface-sunken/50 transition-colors">
					<td class="py-2 pr-4 text-ink-0">
						<a href="/admin/projects/{p.id}" class="hover:text-action-warm-hover transition-colors max-md:block max-md:max-w-[66vw] max-md:truncate" title={p.name}>{p.name}</a>
					</td>
					<td class="py-2 pr-4 text-ink-2">{p.description || '-'}</td>
					<td class="py-2 pr-4">
						<span class="px-1.5 py-0.5 rounded text-xs font-medium {p.enabled ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}">
							{p.enabled ? '활성' : '비활성'}
						</span>
					</td>
					<td class="py-2 pr-4">
						<button
							onclick={() => onCopyId(p.id)}
							class="text-ink-3 font-mono text-xs hover:text-ink-2 transition-colors"
							title={p.id}
						>
							{copiedId === p.id ? '복사됨!' : p.id.slice(0, 8)}
						</button>
					</td>
					<td class="py-2 pr-4 text-ink-3">{p.created_at?.slice(0, 10) ?? '-'}</td>
					<td class="py-2">
						<div class="flex items-center gap-1">
							<button
								onclick={() => onEdit(p)}
								class="px-2 py-0.5 text-xs bg-surface-selected hover:bg-surface-selected text-ink-2 rounded"
							>수정</button>
							<button
								onclick={() => onAccess(p)}
								class="px-2 py-0.5 text-xs bg-surface-selected/40 hover:bg-surface-selected/40 text-action-warm rounded"
							>권한</button>
							<button
								onclick={() => onDelete(p)}
								class="px-2 py-0.5 text-xs bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded"
							>삭제</button>
						</div>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
