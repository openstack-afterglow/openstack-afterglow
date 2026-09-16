<script lang="ts">
	import { useImageDetailController } from '$lib/stores/imageDetailController.svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError, getBaseUrl } from '$lib/api/client';
	import { Card, Field, SelectInput, Button, StatusChip, Alert } from '$lib/components/ui';

	interface ImageExportJob {
		id: string;
		source_image_id: string;
		target_disk_format: string;
		status: string;
		progress_pct: number;
		error_code?: string | null;
		error_message?: string | null;
		download_path?: string | null;
	}

	const s = useImageDetailController();

	let selectedFormat = $state('qcow2');
	let exportJob = $state<ImageExportJob | null>(null);
	let exporting = $state(false);
	let downloading = $state(false);
	let actionError = $state('');

	const FORMAT_OPTIONS = [
		{ value: 'qcow2', label: 'QCOW2 (QEMU Image)' },
		{ value: 'raw',   label: 'RAW (Raw Disk)' },
		{ value: 'vmdk',  label: 'VMDK (VMware)' },
		{ value: 'vdi',   label: 'VDI (VirtualBox)' },
		{ value: 'vhd',   label: 'VHD (VPC)' },
		{ value: 'vhdx',  label: 'VHDX (Hyper-V)' },
	];

	const VMX_NOTE = 'VMX는 VM 설정 파일입니다. VMware용 디스크 포맷은 VMDK를 선택하세요.';
	const NONTERMINAL_STATUSES = ['queued', 'downloading', 'converting', 'finalizing'];

	const isNonTerminal = $derived(exportJob ? NONTERMINAL_STATUSES.includes(exportJob.status) : false);

	let currentController: AbortController | null = null;
	let pollTimer: ReturnType<typeof setTimeout> | null = null;
	let generation = 0;

	function clearPoll() {
		if (pollTimer) {
			clearTimeout(pollTimer);
			pollTimer = null;
		}
	}

	function schedulePoll(jobId: string, imageId: string, token: string, projectId: string | undefined, gen: number) {
		clearPoll();
		pollTimer = setTimeout(async () => {
			if (gen !== generation || imageId !== s.image?.id) return;
			try {
				const updated = await api.get<ImageExportJob>(
					`/api/v1/palimpsest/hub/image-exports/${jobId}`,
					token,
					projectId,
					{ signal: currentController?.signal, refresh: true }
				);
				if (gen !== generation || imageId !== s.image?.id) return;
				exportJob = updated;
				actionError = '';

				if (NONTERMINAL_STATUSES.includes(updated.status)) {
					schedulePoll(jobId, imageId, token, projectId, gen);
				}
			} catch (err: unknown) {
				if (gen !== generation || imageId !== s.image?.id) return;
				if (err instanceof Error && err.name === 'AbortError') return;
				actionError = err instanceof ApiError ? err.message : '내보내기 상태를 확인하지 못했습니다.';
				schedulePoll(jobId, imageId, token, projectId, gen);
			}
		}, 2000);
	}

	async function loadLatestJob(imageId: string, token: string, projectId: string | undefined, signal: AbortSignal, gen: number) {
		try {
			const res = await api.get<ImageExportJob[] | { items: ImageExportJob[] }>(
				`/api/v1/palimpsest/hub/image-exports?source_image_id=${imageId}&limit=1`,
				token,
				projectId,
				{ signal, refresh: true }
			);
			if (gen !== generation || imageId !== s.image?.id) return;
			const items = Array.isArray(res) ? res : (res?.items ?? []);
			if (items.length > 0) {
				exportJob = items[0];
				if (NONTERMINAL_STATUSES.includes(items[0].status)) {
					schedulePoll(items[0].id, imageId, token, projectId, gen);
				}
			}
		} catch (err: unknown) {
			if (gen !== generation || imageId !== s.image?.id) return;
			if (err instanceof Error && err.name === 'AbortError') return;
		}
	}

	$effect(() => {
		const imageId = s.image?.id;
		const token = $auth.token;
		const projectId = $auth.projectId ?? undefined;

		generation += 1;
		const thisGen = generation;
		currentController?.abort();
		currentController = null;
		clearPoll();
		exportJob = null;
		actionError = '';
		selectedFormat = 'qcow2';
		exporting = false;
		downloading = false;

		if (!imageId || !token) return;

		const controller = new AbortController();
		currentController = controller;
		loadLatestJob(imageId, token, projectId, controller.signal, thisGen);

		return () => {
			controller.abort();
			if (currentController === controller) currentController = null;
			clearPoll();
		};
	});

	async function handleExport() {
		const imageId = s.image?.id;
		const token = $auth.token;
		const projectId = $auth.projectId ?? undefined;
		if (!imageId || !token) return;

		actionError = '';
		exporting = true;
		const thisGen = generation;

		try {
			const res = await api.post<ImageExportJob>(
				'/api/v1/palimpsest/hub/image-exports',
				{ image_id: imageId, disk_format: selectedFormat },
				token,
				projectId
			);
			if (thisGen !== generation || imageId !== s.image?.id) return;
			exportJob = res;
			if (NONTERMINAL_STATUSES.includes(res.status)) {
				schedulePoll(res.id, imageId, token, projectId, thisGen);
			}
		} catch (err: unknown) {
			if (thisGen !== generation || imageId !== s.image?.id) return;
			actionError = err instanceof ApiError ? err.message : '이미지 내보내기 요청에 실패했습니다.';
		} finally {
			if (thisGen === generation) {
				exporting = false;
			}
		}
	}

	async function handleDownload() {
		if (!exportJob || exportJob.status !== 'complete') return;
		const token = $auth.token;
		const imageId = s.image?.id;
		const exportId = exportJob.id;
		const thisGen = generation;
		const projectId = $auth.projectId ?? undefined;
		if (!token) return;

		downloading = true;
		actionError = '';

		try {
			const res = await api.post<{ url: string; expires_in: number }>(
				`/api/v1/palimpsest/hub/image-exports/${exportId}/download-token`,
				{},
				token,
				projectId
			);
			if (thisGen !== generation || imageId !== s.image?.id || exportId !== exportJob?.id) return;
			const url = res.url;
			const absoluteUrl = url.startsWith('http') ? url : `${getBaseUrl()}${url}`;
			const a = document.createElement('a');
			a.href = absoluteUrl;
			a.rel = 'noopener';
			document.body.appendChild(a);
			a.click();
			a.remove();
		} catch (err: unknown) {
			actionError = err instanceof ApiError ? err.message : '다운로드 토큰 발급에 실패했습니다.';
		} finally {
			if (thisGen === generation) downloading = false;
		}
	}
</script>

<Card surface="raised" padding="md">
	<div class="space-y-4">
		<div class="flex items-center justify-between">
			<h3 class="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-2)]">이미지 내보내기</h3>
			{#if exportJob}
				<StatusChip status={exportJob.status} />
			{/if}
		</div>

		<div class="space-y-3">
			<Field label="디스크 포맷" for="export-disk-format" help={selectedFormat === 'vmdk' ? VMX_NOTE : undefined}>
				<SelectInput
					id="export-disk-format"
					bind:value={selectedFormat}
					disabled={exporting || isNonTerminal}
				>
					{#each FORMAT_OPTIONS as opt}
						<option value={opt.value}>{opt.label}</option>
					{/each}
				</SelectInput>
			</Field>

			{#if exportJob}
				<div class="flex items-center justify-between text-xs text-[var(--color-ink-1)]">
					<span>진행률</span>
					<span class="font-mono">{exportJob.progress_pct}%</span>
				</div>
			{/if}

			{#if exportJob?.status === 'error' || exportJob?.error_message}
				<Alert tone="danger" title="내보내기 오류">
					{exportJob.error_message || '이미지 내보내기 중 오류가 발생했습니다.'}
				</Alert>
			{/if}

			{#if actionError}
				<Alert tone="danger">
					{actionError}
				</Alert>
			{/if}

			<div class="flex items-center gap-2 pt-1">
				<Button
					variant="primary"
					onclick={handleExport}
					disabled={exporting || isNonTerminal}
				>
					{exporting ? '내보내기 중...' : isNonTerminal ? '처리 중...' : '내보내기'}
				</Button>

				{#if exportJob?.status === 'complete'}
					<Button
						variant="accent"
						onclick={handleDownload}
						disabled={downloading}
					>
						{downloading ? '다운로드 준비 중...' : '다운로드'}
					</Button>
				{/if}
			</div>
		</div>
	</div>
</Card>
