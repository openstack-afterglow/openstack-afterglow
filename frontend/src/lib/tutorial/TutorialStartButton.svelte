<script lang="ts">
	import { onDestroy } from 'svelte';

	import Button from '$lib/components/ui/Button.svelte';
	import { startTour } from './engine';
	import { recordTutorialStatus, tutorialStatuses, tutorialStatusesLoaded } from './status';
	import type { TourId } from './tours';

	let { tour, compactOnMobile = false }: { tour: TourId; compactOnMobile?: boolean } = $props();

	// "나중에" 안내 힌트 자동 사라짐까지의 시간(ms). 하단 프로그레스 바 애니메이션과 동기화한다.
	const HINT_MS = 7000;

	// 이 컴포넌트 인스턴스에서 초대 팝오버를 아직 닫지 않았는지(시작/나중에 선택 전).
	let promptOpen = $state(true);
	let laterHint = $state(false);
	let hintTimer: ReturnType<typeof setTimeout> | undefined;

	// 이 투어에 대한 기록(completed/dismissed)이 없으면 미체험 → 초대 대상.
	const pending = $derived($tutorialStatuses[tour] === undefined);
	// 서버 이력 로드가 끝난 뒤(빈 맵 깜빡임 방지) 미체험이면서 아직 선택 전일 때만 초대를 띄운다.
	const inviteOpen = $derived($tutorialStatusesLoaded && pending && promptOpen);

	function startNow() {
		promptOpen = false;
		laterHint = false;
		clearTimeout(hintTimer);
		void startTour(tour);
	}

	function later() {
		promptOpen = false;
		void recordTutorialStatus(tour, 'dismissed');
		// 튜토리얼 버튼이 여기 그대로 있으니 언제든 다시 시작할 수 있음을 알린다(잠시 뒤 자동 사라짐).
		laterHint = true;
		clearTimeout(hintTimer);
		hintTimer = setTimeout(() => (laterHint = false), HINT_MS);
	}

	onDestroy(() => clearTimeout(hintTimer));
</script>

<span class:tutorial-start--compact={compactOnMobile} class="tutorial-start">
	<Button variant="outline" size="sm" onclick={startNow} ariaLabel="튜토리얼 시작">
		<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
		<span class={compactOnMobile ? 'hidden sm:inline' : ''}>튜토리얼</span>
	</Button>

	{#if inviteOpen}
		<div
			class="ts-invite"
			role="dialog"
			aria-modal="false"
			aria-labelledby={`ts-invite-title-${tour}`}
		>
			<span class="ts-invite__arrow" aria-hidden="true"></span>
			<p id={`ts-invite-title-${tour}`} class="ts-invite__title">튜토리얼을 시작하시겠습니까?</p>
			<p class="ts-invite__desc">이 페이지의 사용 방법을 단계별로 안내해 드려요.</p>
			<div class="ts-invite__actions">
				<Button variant="primary" size="sm" onclick={startNow}>튜토리얼 시작</Button>
				<button type="button" class="ts-invite__later" onclick={later}>나중에</button>
			</div>
		</div>
	{/if}

	{#if laterHint}
		<div class="ts-hint" role="status" style={`--ts-hint-ms: ${HINT_MS}ms`}>
			<span class="ts-hint__arrow" aria-hidden="true"></span>
			언제든 이 <strong>튜토리얼</strong> 버튼으로 다시 시작할 수 있어요.
			<span class="ts-hint__progress" aria-hidden="true"></span>
		</div>
	{/if}
</span>

<style>
	.tutorial-start {
		position: relative;
		display: inline-flex;
		align-items: center;
	}

	/* 초대 팝오버 — 실제 투어 팝오버(.afterglow-tour)와 동일한 디자인 토큰으로 톤을 맞춘다. */

	.ts-invite {
		position: absolute;
		top: calc(100% + 10px);
		left: 50%;
		transform: translateX(-50%);
		z-index: 50;
		width: max-content;
		max-width: 17rem;
		padding: 0.75rem 0.875rem;
		text-align: left;
		background: var(--color-surface-raised);
		color: var(--color-ink-0);
		border: 1px solid var(--color-line);
		border-radius: 0.75rem;
		box-shadow: var(--glow-warm);
		animation: ts-fade-in 0.18s ease-out;
	}

	.ts-invite__arrow {
		position: absolute;
		top: -6px;
		left: 50%;
		width: 11px;
		height: 11px;
		transform: translateX(-50%) rotate(45deg);
		background: var(--color-surface-raised);
		border-left: 1px solid var(--color-line);
		border-top: 1px solid var(--color-line);
	}

	.ts-invite__title {
		margin: 0 0 0.25rem;
		font-size: 0.9375rem;
		font-weight: 600;
		color: var(--color-ink-0);
	}

	.ts-invite__desc {
		margin: 0 0 0.625rem;
		font-size: 0.8125rem;
		line-height: 1.55;
		color: var(--color-ink-1);
	}

	.ts-invite__actions {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.ts-invite__later {
		padding: 0.25rem 0.5rem;
		font-size: 0.8125rem;
		color: var(--color-ink-1);
		background: none;
		border: none;
		border-radius: 0.375rem;
		cursor: pointer;
	}

	.ts-invite__later:hover {
		color: var(--color-ink-0);
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	/* "나중에" 안내 힌트 — 버튼을 가리키며 재시작 위치를 알려준다. */
	.ts-hint {
		position: absolute;
		top: calc(100% + 10px);
		left: 50%;
		transform: translateX(-50%);
		z-index: 50;
		width: max-content;
		max-width: 16rem;
		/* 하단 프로그레스 바 자리를 위해 아래 여백을 넉넉히 둔다. */
		padding: 0.5rem 0.75rem 0.75rem;
		font-size: 0.75rem;
		line-height: 1.5;
		background: var(--color-surface-sunken);
		color: var(--color-ink-1);
		border: 1px solid var(--color-line);
		border-radius: 0.5rem;
		animation: ts-fade-in 0.18s ease-out;
	}

	/* 말풍선 하단의 프로그레스 바 — 자동으로 사라지기까지 남은 시간 동안 오른쪽에서 줄어든다.
	   애니메이션 시간은 인라인 --ts-hint-ms(= HINT_MS)로 JS 타임아웃과 동기화된다. */
	.ts-hint__progress {
		position: absolute;
		left: 0.5rem;
		right: 0.5rem;
		bottom: 0.375rem;
		height: 3px;
		border-radius: 999px;
		background: var(--gradient-warm);
		transform-origin: left center;
		transform: scaleX(1);
		animation: ts-hint-progress var(--ts-hint-ms, 7000ms) linear forwards;
	}

	@keyframes ts-hint-progress {
		from {
			transform: scaleX(1);
		}
		to {
			transform: scaleX(0);
		}
	}

	.ts-hint strong {
		font-weight: 600;
		color: var(--color-ink-0);
	}

	.ts-hint__arrow {
		position: absolute;
		top: -5px;
		left: 50%;
		width: 9px;
		height: 9px;
		transform: translateX(-50%) rotate(45deg);
		background: var(--color-surface-sunken);
		border-left: 1px solid var(--color-line);
		border-top: 1px solid var(--color-line);
	}

	@media (max-width: 639px) {
		.tutorial-start--compact .ts-invite,
		.tutorial-start--compact .ts-hint {
			position: fixed;
			top: 6.5rem;
			left: auto;
			right: 1rem;
			transform: none;
			max-width: calc(100vw - 2rem);
			animation: none;
		}

		.tutorial-start--compact .ts-invite__arrow,
		.tutorial-start--compact .ts-hint__arrow {
			display: none;
		}
	}

	@media (max-width: 640px) {
		.ts-invite,
		.ts-hint {
			position: fixed;
			top: calc(var(--app-header-height) + 0.75rem);
			right: 1rem;
			left: 1rem;
			width: auto;
			max-width: none;
			transform: none;
			animation: none;
		}

		.ts-invite__arrow,
		.ts-hint__arrow {
			display: none;
		}
	}
	@keyframes ts-fade-in {
		from {
			opacity: 0;
			transform: translateX(-50%) translateY(-4px);
		}
		to {
			opacity: 1;
			transform: translateX(-50%) translateY(0);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.ts-invite,
		.ts-hint {
			animation: none;
		}
	}
</style>
