<script lang="ts">
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';

	interface EndpointGroup {
		service_id: string;
		name: string;
		service: string;
		region: string;
		endpoints: Record<string, string>;
	}

	let {
		endpoints,
		loading,
		emptyMessage,
	}: {
		endpoints: EndpointGroup[];
		loading: boolean;
		emptyMessage: string;
	} = $props();
</script>

{#if loading}
	<LoadingSkeleton variant="table" rows={8} />
{:else if endpoints.length === 0}
	<div class="text-ink-3 text-sm py-8 text-center">{emptyMessage}</div>
{:else}
	<div class="overflow-x-auto">
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
					<th class="text-left py-2 pr-6">Name</th>
					<th class="text-left py-2 pr-6">Service</th>
					<th class="text-left py-2 pr-6">Region</th>
					<th class="text-left py-2">Endpoints</th>
				</tr>
			</thead>
			<tbody>
				{#each [...endpoints].sort((a, b) => (a.name || '').localeCompare(b.name || '')) as ep (ep.service_id)}
					<tr class="border-b border-line/50 text-xs hover:bg-surface-sunken/30 align-top">
						<td class="py-3 pr-6 text-ink-0 font-medium">{ep.name}</td>
						<td class="py-3 pr-6 text-ink-2">{ep.service}</td>
						<td class="py-3 pr-6 text-ink-2">{ep.region}</td>
						<td class="py-3">
							<div class="space-y-1">
								{#each Object.entries(ep.endpoints).sort() as [iface, url]}
									<div class="flex items-start gap-2">
										<span class="text-ink-3 w-14 shrink-0 font-medium">{iface}:</span>
										<span class="text-ink-2 font-mono break-all">{url}</span>
									</div>
								{/each}
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
