<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';

	interface LibraryConfig {
		id: string;
		name: string;
		version: string;
		depends_on: string[];
		available_prebuilt: boolean;
		share_proto: string;
		size_bytes?: number;
	}

	let { libraries, selected, hasGpuFlavor, ubuntuVersion, onToggle }: {
		libraries: LibraryConfig[];
		selected: string[];
		hasGpuFlavor: boolean;
		ubuntuVersion?: string;
		onToggle: (id: string, deps: string[]) => void;
	} = $props();

	let warnings = $state<string[]>([]);
	let validateTimer: ReturnType<typeof setTimeout> | null = null;

	function isSelected(id: string) {
		return selected.includes(id);
	}

	function isRequiredBy(id: string): boolean {
		return libraries.some(
			(lib) => isSelected(lib.id) && lib.depends_on.includes(id) && lib.id !== id
		);
	}

	function formatSize(bytes?: number): string {
		if (!bytes) return '';
		const gb = bytes / (1024 * 1024 * 1024);
		return gb >= 1 ? `${Math.round(gb)} GB` : `${Math.round(gb * 1024)} MB`;
	}

	const selectedCount = $derived(selected.length);
	const totalSize = $derived.by(() => {
		const bytes = libraries
			.filter(l => selected.includes(l.id))
			.reduce((acc, l) => acc + (l.size_bytes ?? 0), 0);
		return formatSize(bytes);
	});
	const allDepsSatisfied = $derived(
		libraries
			.filter(l => selected.includes(l.id))
			.every(l => l.depends_on.every(dep => selected.includes(dep)))
	);

	$effect(() => {
		const ids = [...selected];
		if (validateTimer) clearTimeout(validateTimer);
		if (ids.length === 0) {
			warnings = [];
			return;
		}
		validateTimer = setTimeout(async () => {
			try {
				const token = $auth.token ?? undefined;
				const projectId = $auth.projectId ?? undefined;
				const body: Record<string, unknown> = { library_ids: ids };
				if (ubuntuVersion) body.ubuntu_version = ubuntuVersion;
				const res = await api.post<{ compatible: boolean; messages: string[] }>(
					'/api/v1/libraries/validate', body, token, projectId
				);
				warnings = res.messages ?? [];
			} catch {
				warnings = [];
			}
		}, 300);
	});
</script>

<p class="text-sm text-ink-2 mb-4">
	선택한 레이어는 첫 부팅 시 cloud-init으로 자동 마운트됩니다.
</p>

{#if warnings.length > 0}
	<div class="p-3 rounded-lg border border-yellow-700 bg-yellow-900/20 text-yellow-300 text-xs space-y-1 mb-4">
		{#each warnings as w}
			<div>⚠ {w}</div>
		{/each}
	</div>
{/if}

<div class="space-y-2">
	{#each libraries as lib}
		{@const selected_ = isSelected(lib.id)}
		{@const locked = isRequiredBy(lib.id)}
		{@const gpuWarn = lib.id === 'vllm' && !hasGpuFlavor}

		<button
			type="button"
			onclick={() => { if (!locked) onToggle(lib.id, lib.depends_on); }}
			disabled={locked}
			class="w-full text-left flex items-center gap-3 p-4 rounded-xl border transition-all {selected_
				? 'border-action-warm bg-surface-selected/10'
				: 'border-line-2 bg-surface-base hover:border-line-2'} {locked ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}"
		>
			<!-- 체크박스 -->
			<div class="w-5 h-5 rounded flex-shrink-0 flex items-center justify-center border transition-colors
				{selected_ ? 'bg-action-warm border-action-warm' : 'border-line-2 bg-surface-sunken'}">
				{#if selected_}
					<svg class="w-3.5 h-3.5 text-ink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/>
					</svg>
				{/if}
			</div>

			<!-- 이름 + 배지 + 의존성 -->
			<div class="flex-1 min-w-0">
				<div class="flex items-center gap-2 flex-wrap">
					<span class="font-medium text-ink-0 text-sm">{lib.name}</span>
					{#if lib.version}
						<span class="font-mono text-[11px] text-ink-3 px-1.5 py-0.5 rounded bg-surface-sunken border border-line-2">{lib.version}</span>
					{/if}
					{#if lib.size_bytes}
						<span class="text-[11px] text-ink-3 ml-auto flex-shrink-0">{formatSize(lib.size_bytes)}</span>
					{/if}
				</div>
				{#if lib.depends_on.length > 0}
					<div class="flex items-center gap-1.5 flex-wrap mt-1.5">
						<span class="text-[11px] text-ink-3">요구사항:</span>
						{#each lib.depends_on as dep}
							{@const met = selected.includes(dep)}
							<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full font-mono text-[10.5px]
								{met
									? 'bg-green-900/30 border border-green-800 text-green-400'
									: 'bg-red-900/30 border border-red-800 text-red-400'}">
								{met ? '✓' : '!'} {dep}
							</span>
						{/each}
						{#if locked}
							<span class="text-[10.5px] text-orange-400">(의존 중)</span>
						{/if}
					</div>
				{/if}
				{#if gpuWarn}
					<div class="mt-1.5">
						<span class="inline-flex items-center px-2 py-0.5 rounded-full bg-yellow-900/30 border border-yellow-800 text-yellow-400 font-mono text-[10.5px] font-semibold">GPU 플레이버 필요</span>
					</div>
				{/if}
			</div>
		</button>
	{/each}
</div>

<!-- 하단 summary strip -->
{#if libraries.length > 0}
	<div class="flex items-center gap-3 flex-wrap px-4 py-3 rounded-lg bg-surface-base border border-line text-xs text-ink-2 mt-4">
		<span>선택 <b class="text-ink-0 font-mono font-semibold">{selectedCount}</b>개 / {libraries.length}개</span>
		{#if totalSize}
			<span class="text-ink-3">·</span>
			<span>OverlayFS 추가 디스크 <b class="text-ink-0 font-mono">{totalSize}</b></span>
		{/if}
		{#if selectedCount > 0}
			<span class="text-ink-3">·</span>
			{#if allDepsSatisfied}
				<span>모든 의존성 충족 <span class="text-green-400 font-semibold">✓</span></span>
			{:else}
				<span>의존성 미충족 <span class="text-red-400 font-semibold">!</span></span>
			{/if}
		{/if}
	</div>
{/if}
