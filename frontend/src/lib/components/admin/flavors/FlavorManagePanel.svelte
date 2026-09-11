<script lang="ts">
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import FlavorAccessTab from './FlavorAccessTab.svelte';
	import FlavorExtraSpecsTab from './FlavorExtraSpecsTab.svelte';

	interface Flavor {
		id: string;
		name: string;
		vcpus: number;
		ram: number;
		disk: number;
		is_public: boolean;
		description: string | null;
		extra_specs: Record<string, string>;
		is_gpu: boolean;
		gpu_count: number;
		frontend_visible?: boolean;
	}

	let {
		flavor,
		onClose,
		onChanged,
	}: {
		flavor: Flavor | null;
		onClose: () => void;
		onChanged: () => void;
	} = $props();

	let activeTab = $state<'access' | 'properties'>('access');

	function formatRam(mb: number): string {
		if (mb >= 1024) return `${(mb / 1024).toFixed(mb % 1024 === 0 ? 0 : 1)} GB`;
		return `${mb} MB`;
	}
</script>

{#if flavor}
	<SlidePanel {onClose} ariaLabel="Flavor 관리" width="w-full md:w-[640px]">
		<div class="p-6">
			<div class="flex items-center justify-between mb-4">
				<h2 class="text-lg font-semibold text-ink-0">Flavor 관리</h2>
				<!-- 닫기 버튼은 SlidePanel 이 제공한다(`[data-slide-panel-close]`) -->
			</div>
			<div class="mb-4">
				<div class="text-sm text-ink-2">Flavor</div>
				<div class="text-ink-0 font-medium">{flavor.name}</div>
				<div class="text-xs text-ink-3">{flavor.vcpus} VCPU / {formatRam(flavor.ram)} / {flavor.disk} GB</div>
				<button
					onclick={() => navigator.clipboard.writeText(flavor!.id)}
					class="mt-1 text-xs text-ink-3 font-mono hover:text-ink-2 transition-colors cursor-pointer select-all"
					title="클릭하여 ID 복사"
				>{flavor.id}</button>
			</div>

			<div class="flex border-b border-line mb-4">
				<button
					onclick={() => (activeTab = 'access')}
					class="px-4 py-2 text-sm {activeTab === 'access' ? 'text-action-warm border-b-2 border-action-warm' : 'text-ink-2 hover:text-ink-1'}"
				>접근 관리</button>
				<button
					onclick={() => (activeTab = 'properties')}
					class="px-4 py-2 text-sm {activeTab === 'properties' ? 'text-action-warm border-b-2 border-action-warm' : 'text-ink-2 hover:text-ink-1'}"
				>속성 (extra_specs)</button>
			</div>

			{#if activeTab === 'access'}
				<FlavorAccessTab {flavor} />
			{:else}
				<FlavorExtraSpecsTab {flavor} {onChanged} />
			{/if}
		</div>
	</SlidePanel>
{/if}
