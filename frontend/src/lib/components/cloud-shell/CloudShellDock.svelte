<script lang="ts">
	import { onDestroy } from 'svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import CloudShellTerminal from './CloudShellTerminal.svelte';
	import { cloudShell } from '$lib/stores/cloudShell.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';

	let overflowOpen = $state(false);
	let panelHeight = $state<number | null>(null);
	let dragging = false;

	const statusKey = $derived(
		cloudShell.phase === 'ready'
			? 'cloud_shell_ready'
			: cloudShell.phase === 'authorizing'
				? 'cloud_shell_authorizing'
				: cloudShell.phase === 'ending'
					? 'cloud_shell_ending'
					: cloudShell.phase === 'error'
						? 'cloud_shell_error'
						: cloudShell.phase === 'closed'
							? 'cloud_shell_closed'
							: 'cloud_shell_preparing',
	);
	const dockClass = $derived(
		[
			'cloud-shell-dock',
			cloudShell.view === 'minimized' ? 'cloud-shell-dock--minimized' : '',
			cloudShell.view === 'maximized' ? 'cloud-shell-dock--maximized' : '',
		]
			.filter(Boolean)
			.join(' '),
	);

	function boundedHeight(value: number) {
		return Math.max(240, Math.min(window.innerHeight * 0.7, value));
	}

	function handlePointerMove(event: PointerEvent) {
		if (!dragging) return;
		panelHeight = boundedHeight(window.innerHeight - event.clientY);
	}

	function stopDragging() {
		dragging = false;
		window.removeEventListener('pointermove', handlePointerMove);
		window.removeEventListener('pointerup', stopDragging);
	}

	function startDragging(event: PointerEvent) {
		if (!window.matchMedia('(min-width: 768px)').matches) return;
		event.preventDefault();
		dragging = true;
		window.addEventListener('pointermove', handlePointerMove);
		window.addEventListener('pointerup', stopDragging, { once: true });
	}

	function resizeWithKeyboard(event: KeyboardEvent) {
		if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
		event.preventDefault();
		const current = panelHeight ?? Math.min(360, window.innerHeight * 0.45);
		if (event.key === 'Home') panelHeight = 240;
		else if (event.key === 'End') panelHeight = window.innerHeight * 0.7;
		else panelHeight = boundedHeight(current + (event.key === 'ArrowUp' ? 24 : -24));
	}

	async function resetHome() {
		overflowOpen = false;
		const projectName = cloudShell.identity?.projectName || '현재 프로젝트';
		const confirmed = await confirmDialog(
			`"${projectName}" Cloud Shell 영구 홈의 모든 데이터를 삭제하시겠습니까? 활성 세션이 있으면 먼저 닫아야 하며, 삭제한 데이터는 복구할 수 없습니다.`,
		);

		if (!confirmed) return;
		if (await cloudShell.resetWorkspace()) {
			toast.success('Cloud Shell 영구 홈 삭제를 확인했습니다.');
		}
	}

	function handleClose() {
		if (cloudShell.active) {
			void cloudShell.close('user', { keepDock: true });
			return;
		}
		cloudShell.dismiss();
	}

	onDestroy(stopDragging);
</script>

{#if cloudShell.visible}
	<section
		class={dockClass}
		style:--cloud-shell-user-height={panelHeight ? `${panelHeight}px` : undefined}
		aria-label="Cloud Shell"
	>
		<button
			type="button"
			class="cloud-shell-resize-handle"
			aria-label="Cloud Shell 높이 조절: 위아래 방향키 사용"
			title="드래그하거나 위아래 방향키로 높이 조절"
			onpointerdown={startDragging}
			onkeydown={resizeWithKeyboard}
		></button>

		<header class="cloud-shell-header">
			<div class="min-w-0 flex-1">
				<div class="flex min-w-0 items-center gap-2">
					<h2 class="shrink-0 font-display text-sm font-semibold text-ink-0">Cloud Shell</h2>
					<span class="truncate text-xs text-ink-2">{cloudShell.identity?.projectName || '프로젝트 없음'}</span>
					<StatusChip status={statusKey} class="hidden sm:inline-flex" />
				</div>
				{#if cloudShell.view !== 'minimized'}
					<p class="mt-0.5 truncate text-xs text-ink-3" aria-live="polite">
						{cloudShell.statusStep || `${cloudShell.homeSizeGiB} GiB · 영구 홈`}
					</p>
				{/if}
			</div>

			<div class="flex shrink-0 items-center gap-0.5">
				<Button
					variant="ghost"
					size="icon"
					class="!size-11 md:!size-8"
					onclick={() => cloudShell.view === 'minimized' ? cloudShell.restore() : cloudShell.minimize()}
					ariaLabel={cloudShell.view === 'minimized' ? 'Cloud Shell 복원' : 'Cloud Shell 최소화'}
					title={cloudShell.view === 'minimized' ? '복원' : '최소화'}
				>
					<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
						{#if cloudShell.view === 'minimized'}
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M7 15l5-5 5 5" />
						{:else}
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M6 12h12" />
						{/if}
					</svg>
				</Button>
				<Button
					variant="ghost"
					size="icon"
					class="cloud-shell-maximize-control !size-8"
					onclick={() => cloudShell.toggleMaximized()}
					ariaLabel={cloudShell.view === 'maximized' ? 'Cloud Shell 원래 크기' : 'Cloud Shell 최대화'}
					title={cloudShell.view === 'maximized' ? '원래 크기' : '최대화'}
				>
					<svg class="size-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M5 5h14v14H5z" />
					</svg>
				</Button>
				<div class="relative">
					<Button
						variant="ghost"
						size="icon"
						class="!size-11 md:!size-8"
						onclick={() => (overflowOpen = !overflowOpen)}
						ariaLabel="Cloud Shell 추가 작업"
						ariaPressed={overflowOpen}
						title="추가 작업"
					>
						<svg class="size-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
							<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>
						</svg>
					</Button>
					{#if overflowOpen}
						<div class="absolute bottom-full right-0 z-[var(--z-popover)] mb-2 w-48 overflow-hidden rounded-lg border border-line bg-surface-raised shadow-[var(--shadow-popover)] md:bottom-auto md:top-full md:mb-0 md:mt-2">
							<button
								type="button"
								disabled={cloudShell.resetting}
								onclick={() => void resetHome()}
								class="w-full px-3 py-2.5 text-left text-xs text-state-danger transition-colors hover:bg-surface-sunken disabled:opacity-50"
							>
								{cloudShell.resetting ? '홈 초기화 중…' : '홈 초기화'}
							</button>
						</div>
					{/if}
				</div>
				<Button
					variant="ghost"
					size="icon"
					class="!size-11 md:!size-8"
					onclick={handleClose}
					ariaLabel={cloudShell.active ? 'Cloud Shell 닫기' : 'Cloud Shell 패널 닫기'}
					title={cloudShell.active ? '세션 닫기' : '패널 닫기'}
				>
					<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M6 6l12 12M18 6L6 18" />
					</svg>
				</Button>
			</div>
		</header>

		<div class:hidden={cloudShell.view === 'minimized'} class="flex min-h-0 flex-1 flex-col overflow-hidden">
			{#if cloudShell.resetError}
				<div class="shrink-0 border-b border-line p-3" aria-live="polite">
					<Alert tone="warning" title="영구 홈을 초기화할 수 없습니다">
						{cloudShell.resetError}
					</Alert>
				</div>
			{/if}
			{#if cloudShell.phase === 'error'}
				<div class="border-b border-line p-3" aria-live="polite">
					<Alert tone="danger" title="Cloud Shell을 시작할 수 없습니다">
						<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
							<p>{cloudShell.error}</p>
							<Button variant="danger-outline" size="sm" onclick={() => cloudShell.retry()}>다시 시도</Button>
						</div>
					</Alert>
				</div>
			{/if}
			<div class="min-h-0 flex-1"><CloudShellTerminal /></div>
		</div>
	</section>
{/if}
