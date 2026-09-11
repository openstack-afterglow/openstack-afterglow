<script lang="ts">
	import { api, ApiError } from '$lib/api/client';
	import type { K3sFlavor, K3sNodegroup } from '$lib/types/k3s';

	let {
		clusterId,
		token,
		projectId,
		onClose,
		onSaved,
	}: {
		clusterId: string;
		token?: string;
		projectId?: string;
		onClose: () => void;
		onSaved: (ng: K3sNodegroup) => void;
	} = $props();

	let form = $state({
		name: '',
		role: 'agent',
		node_count: 0,
		flavor_id: '',
		stampede_enabled: false,
		min_size: 0,
		max_size: 5,
	});
	let flavors = $state<K3sFlavor[]>([]);
	let saving = $state(false);
	let error = $state('');

	$effect(() => {
		void api.get<K3sFlavor[]>('/api/v1/flavors', token, projectId).then(f => { flavors = f; }).catch(() => {});
	});

	function flavorGpuCount(flavor: K3sFlavor): number {
		const direct = Number(flavor.gpu_count ?? flavor.extra_specs?.gpu_count ?? 0);
		if (Number.isFinite(direct) && direct > 0) return direct;
		const alias = flavor.extra_specs?.['pci_passthrough:alias'] ?? '';
		return alias.split(',').reduce((sum, entry) => {
			const [name, count] = entry.trim().split(':');
			if (!name || name.toLowerCase().includes('audio')) return sum;
			const parsed = Number(count ?? 1);
			return sum + (Number.isFinite(parsed) ? parsed : 1);
		}, 0);
	}

	async function save() {
		saving = true;
		error = '';
		if (form.stampede_enabled && !form.flavor_id) {
			error = 'Stampede 노드그룹은 명시적 Flavor가 필요합니다.';
			saving = false;
			return;
		}
		if (Number(form.node_count) > 0 && !form.flavor_id) {
			error = '노드 프로비저닝을 시작하려면 Flavor를 선택하세요.';
			saving = false;
			return;
		}
		try {
			const body = {
				name: form.name,
				role: form.role,
				node_count: Number(form.node_count),
				flavor_id: form.flavor_id || null,
				stampede_enabled: form.stampede_enabled,
				...(form.stampede_enabled ? { min_size: Number(form.min_size), max_size: Number(form.max_size) } : {}),
			};
			const ng = await api.post<K3sNodegroup>(
				`/api/v1/k3s/clusters/${clusterId}/nodegroups`,
				body,
				token,
				projectId,
			);
			onSaved(ng);
		} catch (e) {
			error = e instanceof ApiError ? e.message : '생성 실패';
		} finally {
			saving = false;
		}
	}
</script>

<div
	class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
	onclick={(event) => { if (event.target === event.currentTarget) (onClose)(); }}
	onkeydown={(e) => e.key === 'Escape' && onClose()}
	role="dialog"
	tabindex="-1"
>
	<div
		class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]"
	>
		<h2 class="text-lg font-semibold text-ink-0 mb-5">노드그룹 추가</h2>

		<div class="space-y-4">
			<label class="block text-xs text-ink-2 uppercase tracking-wide">
				이름
				<input
					bind:value={form.name}
					type="text"
					placeholder="gpu-workers"
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5"
				/>
			</label>

			<div>
				<span class="block text-xs text-ink-2 uppercase tracking-wide mb-1.5">역할</span>
				<div class="px-3 py-2 rounded-lg border border-action-warm bg-surface-selected/30 text-ink-0 text-sm">
					에이전트
				</div>
				<p class="mt-1 text-xs text-ink-3">커스텀 server 노드그룹은 HA join 설계 후 지원됩니다.</p>
			</div>

			<label class="block text-xs text-ink-2 uppercase tracking-wide">
				노드 수 (0–20)
				<input
					bind:value={form.node_count}
					type="number"
					min="0"
					max="20"
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5"
				/>
			</label>

			<label class="block text-xs text-ink-2 uppercase tracking-wide">
				Flavor {form.stampede_enabled || Number(form.node_count) > 0 ? '(필수)' : '(선택)'}
				<select
					bind:value={form.flavor_id}
					class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5"
				>
					<option value="">선택 안 함</option>
					{#each flavors as f}
						<option value={f.id} disabled={f.eligibility ? !f.eligibility.selectable : false}>
							{f.name} ({f.vcpus}vCPU / {Math.round(f.ram / 1024)}GB){flavorGpuCount(f) > 0 ? ` / GPU ${flavorGpuCount(f)}` : ''}{f.eligibility && !f.eligibility.selectable ? ' [쿼터 초과]' : ''}
						</option>
					{/each}
				</select>
			</label>

			<!-- Stampede 오토스케일 -->
			<div class="border border-line-2 rounded-lg p-3 bg-surface-sunken/50">
				<div class="flex items-center justify-between">
					<div class="flex items-center gap-2">
						<span class="text-sm font-medium text-ink-1">Stampede 오토스케일</span>
						<span class="text-xs bg-yellow-900/60 text-yellow-400 border border-yellow-700/50 rounded px-1.5 py-0.5 leading-none">개발 단계</span>
					</div>
					<button
						type="button"
						role="switch"
						aria-checked={form.stampede_enabled}
						aria-label="Stampede 오토스케일"
						onclick={() => form.stampede_enabled = !form.stampede_enabled}
						class="relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {form.stampede_enabled ? 'bg-action-warm' : 'bg-surface-selected'}"
					>
						<span class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-surface-base shadow ring-0 transition duration-200 {form.stampede_enabled ? 'translate-x-4' : 'translate-x-0'}"></span>
					</button>
				</div>
				{#if form.stampede_enabled}
					{#if Number(form.min_size) === 0}
						<div class="mt-2 text-xs text-action-warm/90 bg-surface-selected/10 border border-action-warm/40 rounded px-2.5 py-1.5">
							⚠ min=0 (scale-to-zero): 유휴 시 모든 노드가 자동 제거됩니다.
						</div>
					{/if}
					<div class="mt-3 grid grid-cols-2 gap-3">
						<label class="block text-xs text-ink-2 uppercase tracking-wide">
							최소 노드
							<input bind:value={form.min_size} type="number" min="0" max={form.max_size}
								class="w-full bg-surface-selected border border-line-2 rounded px-2 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1" />
						</label>
						<label class="block text-xs text-ink-2 uppercase tracking-wide">
							최대 노드
							<input bind:value={form.max_size} type="number" min={form.min_size} max="20"
								class="w-full bg-surface-selected border border-line-2 rounded px-2 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1" />
						</label>
					</div>
					<p class="mt-2 text-xs text-ink-3">Pending pod 발생 시 명시한 Flavor로 {form.min_size}~{form.max_size}개 agent 노드 범위에서 스케일합니다.</p>
				{/if}
			</div>
		</div>

		{#if error}
			<div class="mt-4 text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>
		{/if}

		<div class="flex justify-end gap-3 mt-6">
			<button onclick={onClose} disabled={saving} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0">취소</button>
			<button
				onclick={save}
				disabled={saving || !form.name}
				class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg"
			>
				{saving ? '생성 중...' : Number(form.node_count) > 0 ? '프로비저닝 시작' : '생성'}
			</button>
		</div>
	</div>
</div>
