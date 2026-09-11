<script lang="ts">
	import type { NetworkInfo } from '$lib/types/networks';
	import type { ProjectName } from '$lib/types/adminPort';

	let {
		open = $bindable(),
		allNetworks,
		allProjects,
		creating,
		error,
		onCreate,
	}: {
		open: boolean;
		allNetworks: NetworkInfo[];
		allProjects: ProjectName[];
		creating: boolean;
		error: string;
		onCreate: (form: { network_id: string; name: string; project_id: string; fixed_ip: string }) => Promise<boolean>;
	} = $props();

	let form = $state({ network_id: '', name: '', project_id: '', fixed_ip: '' });
	let projectSearch = $state('');
	let showProjectDropdown = $state(false);
	let selectedProjectName = $state('');

	const filteredProjects = $derived(
		projectSearch
			? allProjects.filter(p => p.name.toLowerCase().includes(projectSearch.toLowerCase()))
			: allProjects
	);

	// Reset form when modal opens
	$effect(() => {
		if (open) {
			form = { network_id: '', name: '', project_id: '', fixed_ip: '' };
			projectSearch = '';
			selectedProjectName = '';
			showProjectDropdown = false;
		}
	});

	function selectProject(p: ProjectName) {
		form.project_id = p.id;
		selectedProjectName = p.name;
		projectSearch = p.name;
		showProjectDropdown = false;
	}

	async function handleCreate() {
		const success = await onCreate({ ...form });
		if (success) {
			form = { network_id: '', name: '', project_id: '', fixed_ip: '' };
			projectSearch = '';
			selectedProjectName = '';
		}
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
			<h2 class="text-lg font-semibold text-ink-0 mb-5">포트 생성</h2>
			{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
			<div class="space-y-4">
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-portcreatemodal-72">네트워크 *</label>
					<select id="field-portcreatemodal-72" bind:value={form.network_id} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm">
						<option value="">네트워크 선택</option>
						{#each allNetworks as n (n.id)}
							<option value={n.id}>{n.name || n.id.slice(0, 12)}</option>
						{/each}
					</select>
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-portcreatemodal-81">이름</label>
					<input id="field-portcreatemodal-81" bind:value={form.name} type="text" placeholder="포트 이름 (선택)" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
				<div class="relative">
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-portcreatemodal-85">프로젝트</label>
					<input id="field-portcreatemodal-85"
						type="text"
						bind:value={projectSearch}
						onfocus={() => showProjectDropdown = true}
						oninput={() => { showProjectDropdown = true; if (!projectSearch) { form.project_id = ''; selectedProjectName = ''; } }}
						onblur={() => setTimeout(() => { showProjectDropdown = false; }, 150)}
						placeholder="프로젝트 검색..."
						class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm"
					/>
					{#if showProjectDropdown && filteredProjects.length > 0}
						<div class="absolute z-10 w-full mt-1 bg-surface-sunken border border-line-2 rounded-lg shadow-[var(--shadow-restraint)] max-h-40 overflow-y-auto">
							{#each filteredProjects as p (p.id)}
								<button
									type="button"
									onmousedown={() => selectProject(p)}
									class="w-full text-left px-3 py-2 text-sm text-ink-2 hover:bg-surface-selected transition-colors {form.project_id === p.id ? 'bg-surface-selected text-ink-0' : ''}"
								>{p.name}</button>
							{/each}
						</div>
					{/if}
				</div>
				<div>
					<label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-portcreatemodal-108">Fixed IP <span class="text-ink-3">(선택)</span></label>
					<input id="field-portcreatemodal-108" bind:value={form.fixed_ip} type="text" placeholder="예: 192.168.1.100" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
				</div>
			</div>
			<div class="flex justify-end gap-3 mt-6">
				<button onclick={() => { open = false; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
				<button onclick={handleCreate} disabled={creating || !form.network_id} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{creating ? '생성 중...' : '생성'}</button>
			</div>
		</div>
	</div>
{/if}
