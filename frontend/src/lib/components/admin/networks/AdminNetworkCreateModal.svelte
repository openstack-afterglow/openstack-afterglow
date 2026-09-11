<script lang="ts">
	let {
		open = $bindable(),
		onCreate,
	}: {
		open: boolean;
		onCreate: (form: { name: string; cidr: string; is_external: boolean; is_shared: boolean; enable_dhcp: boolean }) => Promise<string | true>;
	} = $props();

	let form = $state({ name: '', cidr: '', is_external: false, is_shared: false, enable_dhcp: true });
	let creating = $state(false);
	let error = $state('');

	$effect(() => {
		if (!open) {
			form = { name: '', cidr: '', is_external: false, is_shared: false, enable_dhcp: true };
			error = '';
			creating = false;
		}
	});

	async function submit() {
		creating = true;
		error = '';
		const result = await onCreate({ ...form });
		if (result === true) {
			open = false;
		} else {
			error = result;
		}
		creating = false;
	}
</script>

{#if open}
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={(event) => { if (event.target === event.currentTarget) (() => { open = false; })(); }}
		role="dialog"
		onkeydown={(e) => e.key === 'Escape' && (open = false)}
		tabindex="-1"
	>
		<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
			<h2 class="text-lg font-semibold text-ink-0 mb-5">네트워크 생성</h2>
			{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminnetworkcreatemodal-48">이름</label>
					<input id="field-adminnetworkcreatemodal-48" bind:value={form.name} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminnetworkcreatemodal-52">CIDR <span class="text-ink-3">(서브넷 자동 생성, 선택)</span></label>
					<input id="field-adminnetworkcreatemodal-52" bind:value={form.cidr} type="text" placeholder="예: 192.168.1.0/24" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
				<div class="flex items-center gap-4">
					<label class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer">
						<input type="checkbox" bind:checked={form.is_external} class="rounded" /> 외부 네트워크
					</label>
					<label class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer">
						<input type="checkbox" bind:checked={form.is_shared} class="rounded" /> 공유
					</label>
				</div>
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => { open = false; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={submit} disabled={creating || !form.name} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">
					{creating ? '생성 중...' : '생성'}
				</button>
			</div>
		</div>
	</div>
{/if}
