<script lang="ts">
	import type { ClusterTemplate, CreateClusterForm } from '$lib/types/cluster';

	let {
		open = $bindable(),
		templates,
		onCreate,
	}: {
		open: boolean;
		templates: ClusterTemplate[];
		onCreate: (form: CreateClusterForm) => Promise<string | true>;
	} = $props();

	let form = $state<CreateClusterForm>({
		name: '',
		cluster_template_id: '',
		node_count: 1,
		master_count: 1,
		keypair: '',
	});
	let creating = $state(false);
	let error = $state('');

	$effect(() => {
		if (!open) {
			form = { name: '', cluster_template_id: templates[0]?.id ?? '', node_count: 1, master_count: 1, keypair: '' };
			error = '';
			creating = false;
		}
	});

	$effect(() => {
		if (open && templates.length > 0 && !form.cluster_template_id) {
			form.cluster_template_id = templates[0].id;
		}
	});

	async function submit() {
		if (!form.name.trim() || !form.cluster_template_id) return;
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
		onclick={() => { open = false; error = ''; }}
		role="dialog"
		aria-modal="true"
		tabindex="-1"
		onkeydown={(e) => e.key === 'Escape' && (open = false)}
	>
		<div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]" onclick={(e) => e.stopPropagation()} role="none" onkeydown={(e) => e.stopPropagation()}>
			<h2 class="text-lg font-semibold text-ink-0 mb-5">K8s 클러스터 생성</h2>
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">클러스터 이름
						<input bind:value={form.name} type="text" placeholder="my-cluster" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
					</label>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">클러스터 템플릿
						<select bind:value={form.cluster_template_id} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5">
							{#each templates as t}
								<option value={t.id}>{t.name} ({t.coe})</option>
							{/each}
						</select>
					</label>
				</div>
				<div class="grid grid-cols-2 gap-3">
					<div>
						<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">마스터 수
							<input bind:value={form.master_count} type="number" min="1" max="5" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
						</label>
					</div>
					<div>
						<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">워커 수
							<input bind:value={form.node_count} type="number" min="1" max="50" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
						</label>
					</div>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">키페어 (선택)
						<input bind:value={form.keypair} type="text" placeholder="my-keypair" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
					</label>
				</div>
			</div>
			{#if error}<div class="mt-3 text-red-400 text-xs">{error}</div>{/if}
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => { open = false; error = ''; }} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">취소</button>
				<button onclick={submit} disabled={creating || !form.name || !form.cluster_template_id} class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-ink-0 text-sm font-medium rounded-lg transition-colors">
					{creating ? '생성 중...' : '생성'}
				</button>
			</div>
		</div>
	</div>
{/if}
