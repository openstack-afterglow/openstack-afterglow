<script lang="ts">
	import { onDestroy } from 'svelte';

	import Button from '$lib/components/ui/Button.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
	import { t } from '$lib/i18n/ns/tutorial';
	import { isTourActive, onTourActivityChange, startTour } from './engine';
	import { recordTutorialStatus, tutorialStatuses, tutorialStatusesLoaded } from './status';
	import type { TourId } from './tours';
	import { tutorialViewport } from './viewport';

	// `label` names a specific tour when a page offers more than one; `invite={false}` leaves the invite bubble to
	// the page's other start button so only one bubble can show.
	let { tour, compactOnMobile = false, label, invite = true }: { tour: TourId; compactOnMobile?: boolean; label?: string; invite?: boolean } = $props();

	// "나중에" 안내 힌트가 현재 헤더 흐름 안에서 사라지기까지의 시간(ms).
	const HINT_MS = 7000;

	// 이 컴포넌트 인스턴스에서 초대 팝오버를 아직 닫지 않았는지(시작/나중에 선택 전).
	let promptOpen = $state(true);
	let laterHint = $state(false);
	let hintTimer: ReturnType<typeof setTimeout> | undefined;

	// 이 투어에 대한 기록(completed/dismissed)이 없으면 미체험 → 초대 대상.
	const pending = $derived($tutorialStatuses[tour] === undefined);
	// 서버 이력 로드가 끝난 뒤(빈 맵 깜빡임 방지) 미체험이면서 아직 선택 전일 때만 초대를 띄운다.
	// A running tour owns the highlight; a pending invite from another page would cover its targets.
	let tourActive = $state(isTourActive());
	$effect(() => onTourActivityChange((active) => { tourActive = active; }));
	const inviteOpen = $derived(invite && $tutorialStatusesLoaded && pending && promptOpen && !tourActive);

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

{#if tutorialViewport.current}
<div class:tutorial-start--compact={compactOnMobile} class="tutorial-start">
	{#if inviteOpen}
		<div
			class="ts-invite"
			role="group"
			aria-labelledby={`ts-invite-title-${tour}`}
		>
			<p id={`ts-invite-title-${tour}`} class="ts-invite__title">{t('start.inviteTitle')}</p>
			<p class="ts-invite__desc">{t('start.inviteDescription')}</p>
			<div class="ts-invite__actions">
				<Button variant="outline" size="sm" onclick={startNow} ariaLabel={label ?? t('start.action')}>{t('start.action')}</Button>
				<button type="button" class="ts-invite__later" onclick={later}>{t('start.later')}</button>
			</div>
		</div>
	{:else}
		<Button variant="outline" size="sm" onclick={startNow} ariaLabel={label ?? t('start.action')}>
			<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
			<span class={compactOnMobile ? 'hidden sm:inline' : ''}>{label ?? t('start.label')}</span>
		</Button>
	{/if}

	{#if laterHint}
		<div class="ts-hint" role="status">
			<RichText segments={t.rich('start.hint')} />
		</div>
	{/if}
</div>
{/if}

<style>
	.tutorial-start {
		display: inline-flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.5rem;
		min-width: 0;
		max-width: 17rem;
	}
	.ts-invite { text-align: left; }
	.ts-invite__title {
		margin: 0 0 0.25rem;
		font-size: var(--type-body);
		font-weight: 600;
		color: var(--color-ink-0);
	}
	.ts-invite__desc {
		margin: 0 0 0.5rem;
		font-size: var(--type-support);
		line-height: 1.5;
		text-wrap: pretty;
		color: var(--color-ink-2);
	}
	.ts-invite__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; }
	.ts-invite__later {
		min-height: var(--control-height);
		padding: 0.25rem 0.5rem;
		font-size: var(--type-support);
		color: var(--color-ink-2);
		background: none;
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
	}
	.ts-invite__later:hover { color: var(--color-ink-0); text-decoration: underline; text-underline-offset: 2px; }
	.ts-invite__later:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.ts-hint {
		font-size: var(--type-identifier);
		line-height: 1.5;
		color: var(--color-ink-2);
		text-wrap: pretty;
	}
	.ts-hint :global(strong) { font-weight: 600; color: var(--color-ink-0); }
</style>
