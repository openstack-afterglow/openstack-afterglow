<script lang="ts">
	import { afterNavigate } from '$app/navigation';
	import { page } from '$app/stores';
	import 'driver.js/dist/driver.css';
	import { isTourActive, readPersistedTour, refreshTourAnchor, refreshTourMessages, startTour } from './engine';
	import { isTourId, TOUR_QUERY_KEY } from './tours';
	import { getLocale } from '$lib/i18n/runtime.svelte';

	let lastParam: string | null = null;
	let resumeChecked = false;

	$effect(() => {
		getLocale();
		refreshTourMessages();
	});

	// ?tour=<id> 딥링크 시작 + 새로고침 재개 담당 (UI 없음 — 시작 버튼은 각 페이지에 있다)
	$effect(() => {
		const param = $page.url.searchParams.get(TOUR_QUERY_KEY);
		if (param !== lastParam) {
			lastParam = param;
			if (isTourId(param)) {
				void startTour(param);
				return;
			}
		}
		if (!resumeChecked) {
			resumeChecked = true;
			if (!param && !isTourActive()) {
				const persisted = readPersistedTour();
				if (persisted) void startTour(persisted.tourId, persisted.stepIndex);
			}
		}
	});

	// 라우트가 바뀌면 진행 중인 투어를 현재 화면에 다시 앵커링한다.
	afterNavigate(() => {
		if (isTourActive()) refreshTourAnchor();
	});
</script>
