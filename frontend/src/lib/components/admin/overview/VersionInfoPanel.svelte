<script lang="ts">
	import type { VersionInfo } from '$lib/types/adminOverview';
	import { formatUptime } from '$lib/utils/usageBar';

	let {
		versionInfo,
		open = $bindable(false),
	}: {
		versionInfo: VersionInfo | null;
		open: boolean;
	} = $props();
</script>

<div>
	<button
		class="flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink-2 transition-colors"
		onclick={() => open = !open}
	>
		<svg class="w-3.5 h-3.5 transition-transform {open ? 'rotate-90' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
		</svg>
		시스템 버전 정보
	</button>
	{#if open && versionInfo}
		<div class="bg-surface-base border border-line rounded-lg p-5 mt-2">
			<div class="grid grid-cols-1 sm:grid-cols-2 gap-x-12 gap-y-1">
				<div class="col-span-full mb-2">
					<span class="text-[11px] font-semibold text-ink-3 uppercase tracking-wider">플랫폼</span>
				</div>
				<div class="flex justify-between py-1 border-b border-line/50">
					<span class="text-xs text-ink-3">백엔드 버전</span>
					<span class="text-xs text-ink-2 font-mono">{versionInfo.platform.backend_version}</span>
				</div>
				<div class="flex justify-between py-1 border-b border-line/50">
					<span class="text-xs text-ink-3">프론트엔드 버전</span>
					<span class="text-xs text-ink-2 font-mono">{__APP_VERSION__}</span>
				</div>
				<div class="col-span-full mt-3 mb-2">
					<span class="text-[11px] font-semibold text-ink-3 uppercase tracking-wider">런타임</span>
				</div>
				<div class="flex justify-between py-1 border-b border-line/50">
					<span class="text-xs text-ink-3">Python</span>
					<span class="text-xs text-ink-2 font-mono">{versionInfo.runtime.python_version}</span>
				</div>
				<div class="flex justify-between py-1 border-b border-line/50">
					<span class="text-xs text-ink-3">업타임</span>
					<span class="text-xs text-ink-2 font-mono">{formatUptime(versionInfo.runtime.uptime_seconds)}</span>
				</div>
				<div class="col-span-full mt-3 mb-2">
					<span class="text-[11px] font-semibold text-ink-3 uppercase tracking-wider">의존성</span>
				</div>
				{#each Object.entries(versionInfo.dependencies) as [pkg, ver]}
					<div class="flex justify-between py-1 border-b border-line/50">
						<span class="text-xs text-ink-3">{pkg}</span>
						<span class="text-xs text-ink-2 font-mono">{ver ?? '-'}</span>
					</div>
				{/each}
				{#if versionInfo.git.commit}
					<div class="col-span-full mt-3 mb-2">
						<span class="text-[11px] font-semibold text-ink-3 uppercase tracking-wider">Git</span>
					</div>
					<div class="flex justify-between py-1 border-b border-line/50">
						<span class="text-xs text-ink-3">커밋</span>
						<span class="text-xs text-ink-2 font-mono">{versionInfo.git.commit}</span>
					</div>
					{#if versionInfo.git.tag}
						<div class="flex justify-between py-1 border-b border-line/50">
							<span class="text-xs text-ink-3">태그</span>
							<span class="text-xs text-ink-2 font-mono">{versionInfo.git.tag}</span>
						</div>
					{/if}
					{#if versionInfo.git.branch}
						<div class="flex justify-between py-1 border-b border-line/50">
							<span class="text-xs text-ink-3">브랜치</span>
							<span class="text-xs text-ink-2 font-mono">{versionInfo.git.branch}</span>
						</div>
					{/if}
				{/if}
			</div>
		</div>
	{/if}
</div>
