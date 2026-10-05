<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-identity';

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
				<th class="text-left py-2 pr-4">{t('form.name')}</th>
				<th class="text-left py-2 pr-4">{t('form.description')}</th>
				<th class="text-left py-2 pr-4">{t('projectTable.status')}</th>
				<th class="text-left py-2 pr-4">ID</th>
				<th class="text-left py-2 pr-4">{t('projectTable.createdAt')}</th>
				<th class="text-left py-2">{t('projectTable.actions')}</th>
			</tr>
		</thead>
		<tbody>
			{#each projects as p (p.id)}
				<tr class="border-b border-line/50 text-xs hover:bg-surface-sunken/50 transition-colors">
					<td class="py-2 pr-4 text-ink-0">
						<a href="/admin/projects/{p.id}" class="hover:text-warm-text-hover transition-colors max-md:block max-md:max-w-[66vw] max-md:truncate" title={p.name}>{p.name}</a>
					</td>
					<td class="py-2 pr-4 text-ink-2">{p.description || '-'}</td>
					<td class="py-2 pr-4">
						<span class="px-1.5 py-0.5 rounded text-xs font-medium {p.enabled ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}">
						{p.enabled ? t('state.enabled') : t('state.disabled')}
						</span>
					</td>
					<td class="py-2 pr-4">
						<button
							onclick={() => onCopyId(p.id)}
							class="text-ink-2 font-mono text-xs hover:text-ink-2 transition-colors"
							title={p.id}
						>
						{copiedId === p.id ? t('projectTable.copied') : p.id.slice(0, 8)}
						</button>
					</td>
					<td class="py-2 pr-4 text-ink-2">{p.created_at?.slice(0, 10) ?? '-'}</td>
					<td class="py-2">
						<div class="flex items-center gap-1">
							<button
								onclick={() => onEdit(p)}
								class="px-2 py-0.5 text-xs bg-surface-selected hover:bg-surface-selected text-ink-2 rounded"
							>{t('actions.edit')}</button>
							<button
								onclick={() => onAccess(p)}
								class="px-2 py-0.5 text-xs bg-surface-selected/40 hover:bg-surface-selected/40 text-warm-text rounded"
							>{t('projectTable.permissions')}</button>
							<button
								onclick={() => onDelete(p)}
								class="px-2 py-0.5 text-xs bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded"
							>{t('actions.delete')}</button>
						</div>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
