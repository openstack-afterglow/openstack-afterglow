<script lang="ts">
	import type { ContextState } from '$lib/api/chatContracts';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import UsageBar from '$lib/components/ui/UsageBar.svelte';

	let { state, explanation, onClose }: {
		state: ContextState | null;
		explanation: string;
		onClose: () => void;
	} = $props();

	const labels: Record<string, string> = {
		messages: '대화 메시지·초안', system_prompt: '시스템 지침', workspace: '프로젝트 지침',
		memory: '메모리', skills: '스킬', agent: '에이전트 지침', tools: '도구 정의',
		mcp_tools: 'MCP 도구', deferred_tools: '미로딩 도구 (필요 시 로딩)', summary: '압축된 대화 요약', attachments: '첨부', overhead: '메시지 형식·계수 보정'
	};
	const format = new Intl.NumberFormat('ko-KR');
	const ratio = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1 });
	const breakdown = $derived(state?.breakdown);
	const included = $derived(breakdown?.components.filter((component) => component.included) ?? []);
	const deferred = $derived(breakdown?.components.filter((component) => !component.included && !breakdown.uncounted.includes(component.id)) ?? []);
	const unresolved = $derived(breakdown?.components.filter((component) => !component.included && breakdown.uncounted.includes(component.id)) ?? []);
	const fullLimit = $derived(state?.context_limit && state.context_limit > 0 ? state.context_limit : null);
	const knownInput = $derived(state?.input_tokens ?? null);
	const complete = $derived(breakdown?.complete !== false && state?.measurement !== 'unknown' && knownInput !== null);
	const remaining = $derived(complete && state?.input_budget != null ? Math.max(0, state.input_budget - knownInput!) : null);
	const measurement = $derived(state?.measurement === 'tokenizer' ? '토크나이저 계수' : state?.measurement === 'estimated' ? '추정치' : '계수 불가');
	const label = (id: string) => labels[id] ?? id;
	const tokens = (value: number | null) => value === null ? '확인 불가' : format.format(value);
	const share = (value: number | null) => value === null || fullLimit === null ? '—' : `${ratio.format(value / fullLimit * 100)}%`;
</script>

<SlidePanel {onClose} width="w-full md:w-[28rem] max-w-full" resizable={false} ariaLabel="컨텍스트 윈도우">
	<section id="chat-context-detail" class="px-4 pb-6 text-sm text-ink-1" aria-labelledby="chat-context-heading">
		<h2 id="chat-context-heading" class="text-base font-semibold text-ink-0">컨텍스트 윈도우</h2>
		<p class="mt-2 break-words text-xs leading-relaxed text-ink-2">{explanation}</p>

		{#if state}
			<div class="mt-5 border-b border-line pb-4">
				<div class="flex flex-wrap items-baseline justify-between gap-2">
					<span class="text-xs text-ink-2">{complete ? '포함된 입력' : '확인된 입력'} · {measurement}</span>
					<strong class="font-mono text-base tabular-nums text-ink-0">{tokens(knownInput)} / {tokens(fullLimit)}</strong>
				</div>
				{#if knownInput !== null && fullLimit !== null}
					<div class="mt-3">
						<UsageBar percent={knownInput / fullLimit * 100} label={complete ? '전체 컨텍스트 대비 입력' : '전체 컨텍스트 대비 확인된 입력 일부'} showValue={false} size="sm" />
					</div>
				{/if}
				<p class="mt-2 text-xs leading-relaxed text-ink-2">비중은 모델 전체 한도 기준입니다. 응답과 안전 여유분을 뺀 입력 예산은 {tokens(state.input_budget)} 토큰입니다.</p>
			</div>

			{#if breakdown}
				<p class="mt-4 text-xs text-ink-2">{breakdown.scope === 'request' ? '실행 요청 기준' : '다음 요청 미리보기'} · {breakdown.complete ? '포함 항목 계수 완료' : '일부 항목 미계수'}</p>
				{#if !breakdown.complete}
					<p class="mt-2 text-xs leading-relaxed text-ink-2">아직 계수되지 않은 항목이 있어 정확한 남은 용량을 표시하지 않습니다. 실제 실행 시 도구 결과 등에 따라 달라질 수 있습니다.</p>
				{/if}
				<div class="mt-4 grid grid-cols-[minmax(0,1fr)_auto_4rem] gap-2 border-b border-line pb-2 text-xs text-ink-2" aria-hidden="true">
					<span>포함된 컨텍스트</span><span>토큰</span><span class="text-right">전체 비중</span>
				</div>
				<div class="divide-y divide-line">
					{#each included as component (component.id)}
						<details class="py-1">
							<summary class="grid min-h-11 cursor-pointer grid-cols-[minmax(0,1fr)_auto_4rem] items-center gap-2 rounded-md text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-line-2">
								<span class="min-w-0 break-words font-medium">{label(component.id)} <span class="font-normal text-ink-2">({tokens(component.count)})</span></span>
								<span class="font-mono tabular-nums">{component.measurement === 'estimated' && component.tokens !== null ? '≈ ' : ''}{tokens(component.tokens)}</span>
								<span class="text-right font-mono tabular-nums text-ink-2">{share(component.tokens)}</span>
							</summary>
							{#if component.items.length}
								<ul class="mt-2 space-y-2 border-l border-line pl-3 text-xs leading-relaxed text-ink-2">
									{#each component.items as item, index (`${index}:${item}`)}<li class="break-words">{item}</li>{/each}
								</ul>
							{:else}
								<p class="mt-2 text-xs text-ink-2">{component.measurement === 'estimated' ? '이 항목은 추정 토큰 수입니다.' : '내용 대신 포함된 항목 수와 계수만 표시합니다.'}</p>
							{/if}
						</details>
					{/each}
				</div>
				{#if breakdown.uncounted.length}
					<p class="mt-3 break-words text-xs leading-relaxed text-ink-2">미계수: {breakdown.uncounted.map(label).join(', ')}</p>
				{/if}
				{#if unresolved.length}
					<h3 class="mt-5 border-t border-line pt-4 text-xs font-semibold">실행 시 확인 · 현재 미계수</h3>
					<p class="mt-2 text-xs leading-relaxed text-ink-2">아직 가져오지 못한 스키마나 첨부 내용을 0으로 계산하지 않습니다. 실행 요청에서 확인되기 전까지 전체 입력과 남은 용량은 확정할 수 없습니다.</p>
					{#each unresolved as component (component.id)}
						<details class="mt-3 text-xs">
							<summary class="min-h-11 cursor-pointer content-center break-words">{label(component.id)} · {component.count === null ? '개수 미확인' : `${format.format(component.count)}개`}</summary>
							<ul class="space-y-2 pl-3 text-ink-2">{#each component.items as item, index (`${index}:${item}`)}<li class="break-words">{item}</li>{/each}</ul>
						</details>
					{/each}
				{/if}
				{#if deferred.length}
					<h3 class="mt-5 border-t border-line pt-4 text-xs font-semibold">선택됨 · 아직 입력에 포함되지 않음</h3>
					<p class="mt-2 text-xs leading-relaxed text-ink-2">이 항목의 스키마는 현재 입력에 포함되지 않습니다. 실제 실행 요청에 노출된 경우에만 입력 토큰으로 계수합니다.</p>
					{#each deferred as component (component.id)}
						<details class="mt-3 text-xs">
							<summary class="min-h-11 cursor-pointer content-center break-words">{label(component.id)} · {component.count === null ? '개수 미확인' : `${format.format(component.count)}개`}</summary>
							<ul class="space-y-2 pl-3 text-ink-2">{#each component.items as item, index (`${index}:${item}`)}<li class="break-words">{item}</li>{/each}</ul>
						</details>
					{/each}
				{/if}
			{:else}
				<p class="mt-5 text-xs leading-relaxed text-ink-2">이 응답에는 구성 항목 정보가 없습니다. 현재 Lumen API·worker가 실행 중인지 확인하고 다음 컨텍스트 조회를 기다려 주세요. 과거 기록을 임의로 분해하지 않습니다.</p>
			{/if}

			<dl class="mt-5 space-y-3 border-t border-line pt-4 text-xs">
				<div class="grid grid-cols-[minmax(0,1fr)_auto_4rem] gap-2"><dt>응답 예약</dt><dd class="font-mono tabular-nums">{tokens(state.output_reserve)}</dd><dd class="text-right font-mono text-ink-2">{share(state.output_reserve)}</dd></div>
				<div class="grid grid-cols-[minmax(0,1fr)_auto_4rem] gap-2"><dt>압축·안전 버퍼</dt><dd class="font-mono tabular-nums">{tokens(state.safety_reserve)}</dd><dd class="text-right font-mono text-ink-2">{share(state.safety_reserve)}</dd></div>
				<div class="grid grid-cols-[minmax(0,1fr)_auto_4rem] gap-2 font-semibold"><dt>남은 입력 용량</dt><dd class="font-mono tabular-nums">{tokens(remaining)}</dd><dd class="text-right font-mono text-ink-2">{share(remaining)}</dd></div>
			</dl>
			<p class="mt-4 break-all text-xs leading-relaxed text-ink-2">모델: {state.model_name}<br />컨텍스트 리비전: {state.revision}</p>
		{/if}

		<div class="mt-5 flex flex-wrap gap-2 border-t border-line pt-4">
			<Button href="/dashboard/chat/settings?section=memory" variant="ghost" size="sm" class="min-h-11">메모리 확인</Button>
			<Button href="/dashboard/chat/settings?section=tools" variant="ghost" size="sm" class="min-h-11">도구 확인</Button>
			<Button href="/dashboard/chat/settings?section=mcp" variant="ghost" size="sm" class="min-h-11">MCP 확인</Button>
			<Button href="/dashboard/chat/settings?section=skills" variant="ghost" size="sm" class="min-h-11">스킬 확인</Button>
		</div>
		<p class="mt-3 text-xs leading-relaxed text-ink-2">이 패널은 요청 구성의 토큰 계수입니다. 공급자가 청구하는 사용량이나 월·주간 크레딧 한도와는 다릅니다.</p>
	</section>
</SlidePanel>
