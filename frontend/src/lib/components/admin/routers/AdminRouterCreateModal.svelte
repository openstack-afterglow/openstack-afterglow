<script lang="ts">
	import type { AdminNetwork } from '$lib/types/networks';

	let {
		open = $bindable(),
		externalNetworks,
		onCreate,
	}: {
		open: boolean;
		externalNetworks: AdminNetwork[];
		onCreate: (form: { name: string; external_network_id: string }) => Promise<string | true>;
	} = $props();

	let form = $state({ name: '', external_network_id: '' });
	let creating = $state(false);
	let error = $state('');

	$effect(() => {
		if (!open) {
			form = { name: '', external_network_id: '' };
			error = '';
			creating = false;
		} else if (externalNetworks.length > 0 && !form.external_network_id) {
			form.external_network_id = externalNetworks[0].id;
		}
	});

	async function submit() {
		if (!form.name) return;
		creating = true;
		error = '';
		const result = await onCreate({ ...form });
		creating = false;
		if (result === true) open = false;
		else error = result;
	}
</script>

{#if open}
	<div class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50" onclick={() => { open = false; }} role="dialog" onkeydown={(e) => e.key === 'Escape' && (open = false)} tabindex="-1">
		<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]" onclick={(e) => e.stopPropagation()} role="none" onkeydown={(e) => e.stopPropagation()}>
			<h2 class="text-lg font-semibold text-ink-0 mb-5">라우터 생성</h2>
			{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminroutercreatemodal-46">이름</label>
					<input id="field-adminroutercreatemodal-46" bind:value={form.name} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminroutercreatemodal-50">외부 네트워크 <span class="text-ink-3">(선택)</span></label>
					<select id="field-adminroutercreatemodal-50" bind:value={form.external_network_id} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none">
						<option value="">없음</option>
						{#each externalNetworks as n}
							<option value={n.id}>{n.name || n.id.slice(0, 8)}</option>
						{/each}
					</select>
				</div>
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => { open = false; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={submit} disabled={creating || !form.name} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{creating ? '생성 중...' : '생성'}</button>
			</div>
		</div>
	</div>
{/if}
