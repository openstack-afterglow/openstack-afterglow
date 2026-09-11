<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import type { GpuCatalogDevice } from '$lib/types/gpu';

	let {
		open = $bindable(false),
	}: {
		open: boolean;
	} = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let devices = $state<GpuCatalogDevice[]>([]);
	let loading = $state(false);
	let error = $state('');
	let notice = $state('');

	// 단건 추가 폼
	let form = $state({ vendor_id: '10DE', device_id: '', name: '', is_audio: false, aliases: '' });
	let saving = $state(false);

	// 일괄 갱신 (CSV/xlsx 업로드)
	let csvFile = $state<File | null>(null);
	let csvMode = $state<'replace' | 'upsert'>('replace');
	let importing = $state(false);
	let downloading = $state(false);

	async function load() {
		loading = true;
		error = '';
		try {
			const res = await api.get<{ devices: GpuCatalogDevice[] }>('/api/v1/admin/gpu-devices', token, projectId);
			devices = res.devices;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'GPU 카탈로그 조회 실패';
			devices = [];
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (open) {
			notice = '';
			load();
		}
	});

	async function addDevice() {
		saving = true;
		error = '';
		notice = '';
		try {
			await api.post(
				'/api/v1/admin/gpu-devices',
				{
					vendor_id: form.vendor_id.trim(),
					device_id: form.device_id.trim(),
					name: form.name.trim(),
					is_audio: form.is_audio,
					aliases: form.aliases.split(';').map((a) => a.trim()).filter(Boolean),
				},
				token,
				projectId,
			);
			notice = `장치 추가됨: ${form.name}`;
			form = { vendor_id: '10DE', device_id: '', name: '', is_audio: false, aliases: '' };
			await load();
		} catch (e) {
			error = e instanceof ApiError ? e.message : '장치 추가 실패';
		} finally {
			saving = false;
		}
	}

	async function deleteDevice(d: GpuCatalogDevice) {
		if (!await confirmDialog(`'${d.name}' (${d.vendor_id}:${d.device_id}) 항목을 삭제하시겠습니까?`)) return;
		error = '';
		notice = '';
		try {
			await api.delete(`/api/v1/admin/gpu-devices/${d.vendor_id}/${d.device_id}`, token, projectId);
			await load();
		} catch (e) {
			error = e instanceof ApiError ? e.message : '장치 삭제 실패';
		}
	}

	async function downloadTemplate(format: 'xlsx' | 'csv') {
		downloading = true;
		error = '';
		try {
			const { blob, filename } = await api.downloadBlob(
				`/api/v1/admin/gpu-devices/export?format=${format}`,
				token,
				projectId,
			);
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = filename;
			a.click();
			URL.revokeObjectURL(url);
		} catch (e) {
			if (format === 'xlsx' && e instanceof ApiError && e.status >= 500) {
				error = '엑셀 템플릿 생성을 백엔드가 지원하지 않는 상태입니다 (재시작/재배포 필요). 우선 CSV 템플릿을 이용하세요.';
			} else {
				error = e instanceof ApiError ? e.message : '템플릿 다운로드 실패';
			}
		} finally {
			downloading = false;
		}
	}

	async function importCsv() {
		if (!csvFile) return;
		if (csvMode === 'replace' && !await confirmDialog('전체 교체 모드입니다. 관리자가 추가한 기존 DB 항목이 모두 CSV 내용으로 대체됩니다. 계속하시겠습니까?')) return;
		importing = true;
		error = '';
		notice = '';
		try {
			const fd = new FormData();
			fd.append('file', csvFile);
			const res = await api.upload<{ imported: number; mode: string }>(
				`/api/v1/admin/gpu-devices/import?mode=${csvMode}`,
				fd,
				token,
				projectId,
			);
			notice = `일괄 갱신 완료: ${res.imported}개 항목 (${res.mode === 'replace' ? '전체 교체' : '병합'})`;
			csvFile = null;
			await load();
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'CSV import 실패';
		} finally {
			importing = false;
		}
	}

	function close() {
		open = false;
		error = '';
		notice = '';
	}

	const sourceLabel: Record<string, string> = { builtin: '내장', config: 'config', db: 'DB' };
	const sourceClass: Record<string, string> = {
		builtin: 'bg-surface-sunken text-ink-2',
		config: 'bg-yellow-900/30 text-yellow-400',
		db: 'bg-surface-selected/30 text-action-warm',
	};
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={close}
		role="dialog" aria-modal="true" tabindex="-1"
		onkeydown={(e) => e.key === 'Escape' && close()}
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-3xl mx-4 shadow-[var(--shadow-restraint)] max-h-[85vh] flex flex-col"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			<div class="flex items-center justify-between mb-4">
				<h2 class="text-lg font-semibold text-ink-0">GPU 장치 카탈로그</h2>
				<button onclick={close} class="text-ink-2 hover:text-ink-0 text-lg leading-none">×</button>
			</div>

			{#if error}
				<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-2 text-sm mb-3">{error}</div>
			{/if}
			{#if notice}
				<div class="bg-green-900/30 border border-green-700 text-green-300 rounded-lg px-4 py-2 text-sm mb-3">{notice}</div>
			{/if}

			<div class="flex-1 overflow-y-auto min-h-0 space-y-5">
				<!-- 카탈로그 목록 -->
				<div>
					<div class="text-xs text-ink-3 uppercase tracking-wide mb-2">등록된 장치 ({devices.length})</div>
					{#if loading}
						<div class="text-ink-3 text-sm py-4">로딩 중...</div>
					{:else}
						<div class="border border-line rounded-lg overflow-hidden">
							<table class="w-full text-xs">
								<thead>
									<tr class="bg-surface-canvas text-ink-2 uppercase tracking-wide">
										<th class="text-left px-3 py-2">Vendor:Device</th>
										<th class="text-left px-3 py-2">이름</th>
										<th class="text-left px-3 py-2">Aliases</th>
										<th class="text-left px-3 py-2">소스</th>
										<th class="px-3 py-2"></th>
									</tr>
								</thead>
								<tbody>
									{#each devices.filter((d) => !d.is_audio) as d (d.vendor_id + d.device_id)}
										<tr class="border-t border-line/50">
											<td class="px-3 py-1.5 font-mono text-ink-2">{d.vendor_id}:{d.device_id}</td>
											<td class="px-3 py-1.5 text-ink-0">{d.name} <span class="text-ink-3">({d.vendor_name})</span></td>
											<td class="px-3 py-1.5 font-mono text-ink-2 break-all">{d.aliases.join(', ') || '-'}</td>
											<td class="px-3 py-1.5">
												<span class="px-1.5 py-0.5 rounded {sourceClass[d.source]}">{sourceLabel[d.source]}</span>
											</td>
											<td class="px-3 py-1.5 text-right">
												{#if d.source === 'db'}
													<button onclick={() => deleteDevice(d)} class="text-red-400 hover:text-red-300">삭제</button>
												{/if}
											</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					{/if}
				</div>

				<!-- 단건 추가 -->
				<div>
					<div class="text-xs text-ink-3 uppercase tracking-wide mb-2">장치 추가</div>
					<div class="grid grid-cols-2 md:grid-cols-4 gap-2">
						<input bind:value={form.vendor_id} type="text" placeholder="Vendor (10DE)" maxlength="4"
							class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm" />
						<input bind:value={form.device_id} type="text" placeholder="Device (2204)" maxlength="4"
							class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm" />
						<input bind:value={form.name} type="text" placeholder="이름 (RTX 3090)"
							class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-sm focus:outline-none focus:border-action-warm" />
						<input bind:value={form.aliases} type="text" placeholder="alias (RTX3090;3090)"
							class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-ink-0 text-sm font-mono focus:outline-none focus:border-action-warm" />
					</div>
					<div class="flex items-center justify-between mt-2">
						<label class="flex items-center gap-1.5 text-xs text-ink-2">
							<input bind:checked={form.is_audio} type="checkbox" class="accent-blue-600" />
							오디오 장치 (GPU 집계에서 제외)
						</label>
						<button
							onclick={addDevice}
							disabled={saving || !form.vendor_id.trim() || !form.device_id.trim() || !form.name.trim()}
							class="px-4 py-1.5 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm rounded-lg disabled:opacity-30"
						>{saving ? '저장 중...' : '추가/수정'}</button>
					</div>
				</div>

				<!-- 일괄 갱신 (템플릿 다운로드 → 값 입력 → 업로드) -->
				<div>
					<div class="text-xs text-ink-3 uppercase tracking-wide mb-2">일괄 갱신</div>
					<div class="text-xs text-ink-3 mb-2">
						1) 현재 카탈로그가 채워진 템플릿을 다운로드 → 2) 엑셀 등에서 값 입력 → 3) 업로드.
						컬럼: <span class="font-mono">vendor_id, device_id, name, is_audio, aliases</span> (aliases는 ; 구분, source 컬럼은 무시됨)
					</div>
					<div class="flex flex-wrap items-center gap-2 mb-3">
						<button
							onclick={() => downloadTemplate('xlsx')}
							disabled={downloading}
							class="px-3 py-1.5 bg-surface-sunken hover:bg-surface-selected text-ink-2 text-xs rounded-lg disabled:opacity-30"
						>⬇ 엑셀 템플릿 (.xlsx)</button>
						<button
							onclick={() => downloadTemplate('csv')}
							disabled={downloading}
							class="px-3 py-1.5 bg-surface-sunken hover:bg-surface-selected text-ink-2 text-xs rounded-lg disabled:opacity-30"
						>⬇ CSV 템플릿</button>
					</div>
					<div class="flex flex-wrap items-center gap-3">
						<input
							type="file"
							accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
							onchange={(e) => (csvFile = e.currentTarget.files?.[0] ?? null)}
							class="text-xs text-ink-2 file:mr-2 file:px-3 file:py-1.5 file:rounded-lg file:border-0 file:bg-surface-sunken file:text-ink-2 file:text-xs hover:file:bg-surface-selected"
						/>
						<label class="flex items-center gap-1.5 text-xs text-ink-2">
							<input type="radio" bind:group={csvMode} value="replace" class="accent-blue-600" />
							전체 교체
						</label>
						<label class="flex items-center gap-1.5 text-xs text-ink-2">
							<input type="radio" bind:group={csvMode} value="upsert" class="accent-blue-600" />
							병합 (upsert)
						</label>
						<button
							onclick={importCsv}
							disabled={importing || !csvFile}
							class="px-4 py-1.5 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm rounded-lg disabled:opacity-30"
						>{importing ? '업로드 중...' : '업로드'}</button>
					</div>
				</div>
			</div>
		</div>
	</div>
{/if}
