<script lang="ts">
	import { useFileStorageDetailController } from '$lib/stores/fileStorageDetailController.svelte';

	const s = useFileStorageDetailController();

	// export_location_details 우선, 없으면 경로 문자열 목록을 fallback으로 사용
	const locations = $derived(() => {
		const details = s.fileStorage!.export_location_details;
		if (details && details.length > 0) {
			return details.map((d, i) => ({ path: d.path, preferred: d.preferred, index: i }));
		}
		return s.fileStorage!.export_locations.map((path, i) => ({ path, preferred: false, index: i }));
	});

	// NFS 경로에서 호스트 IP만 추출 (예: "172.30.2.101:/volumes/..." → "172.30.2.101")
	function extractHost(path: string): string | null {
		const m = path.match(/^(\d{1,3}(?:\.\d{1,3}){3})/);
		return m ? m[1] : null;
	}
</script>

<div class="bg-surface-base border border-line rounded-lg p-5 mb-4">
	<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">Export Locations</h3>
	<div class="space-y-2">
		{#each locations() as loc (loc.index)}
			<div class="flex items-start gap-2">
				<div class="flex-1 flex items-center gap-1.5 bg-surface-sunken px-3 py-2 rounded min-w-0">
					{#if loc.preferred}
						<span class="shrink-0 text-[10px] px-1 py-0.5 rounded bg-teal-900/50 text-teal-400 border border-teal-800 leading-none">preferred</span>
					{/if}
					{#if extractHost(loc.path)}
						<span class="shrink-0 font-mono text-xs text-teal-300 font-medium">{extractHost(loc.path)}</span>
						<code class="flex-1 text-xs text-ink-2 font-mono truncate">{loc.path.replace(/^\d{1,3}(?:\.\d{1,3}){3}:/, '')}</code>
					{:else}
						<code class="flex-1 text-xs text-ink-2 font-mono break-all">{loc.path}</code>
					{/if}
				</div>
				<button
					onclick={() => s.copyPath(loc.path, loc.index)}
					class="shrink-0 text-xs px-2 py-1.5 rounded border transition-colors {s.copiedIndex === loc.index
						? 'border-green-700 text-green-400'
						: 'border-line-2 text-ink-2 hover:text-ink-1 hover:border-line-2'}"
				>
					{s.copiedIndex === loc.index ? '복사됨' : '복사'}
				</button>
			</div>
		{/each}
	</div>
</div>
