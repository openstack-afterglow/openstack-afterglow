<script module lang="ts">
	export interface HudLabelItem {
		netId: string;
		name: string;
		cidrText: string;
		kindLabel: string;
		isolated: boolean;
		/** ACTIVE 가 아닐 때만 채움 */
		statusText: string | null;
		/** 관리자 보기 전용 pill 텍스트(VLAN 태그/VXLAN VNI, MTU) */
		adminPills: string[];
		color: string;
		sx: number;
		sy: number;
		avail: number;
		active: boolean;
		dim: boolean;
		summary?: boolean;
	}

	/**
	 * 트렁크 배지. 그려지는 배지는 **언제나 provider uplink** 다 —
	 * `hudBadges` 게이트가 `trunkNetIds.length >= 2` 를 요구하는데
	 * `trunkNetIds` 는 uplink 가 아닌 트렁크에 `[netId]` 한 개만 돌려주기 때문이다.
	 * 그래서 캡션 분기(구 `uplink ? … : TRUNK_CAPTION`)를 두지 않는다.
	 */
	export interface HudBadgeItem {
		key: string;
		netId: string;
		netName: string;
		sx: number;
		sy: number;
		rateText: string;
		dim: boolean;
	}
</script>

<script lang="ts">
	import { onMount } from 'svelte';
	import { SvelteMap } from 'svelte/reactivity';
	import { hudLeader, placeHudItems } from './hudLayout';
	import type { Rect } from './types';
	import { t } from '$lib/i18n/ns/topology';
	// 스크린 공간 HUD: 존 라벨 칩과 트렁크 배지. 버튼에만 pointer-events 를 준다.
	import Pill from '$lib/components/ui/Pill.svelte';
	import { UPLINK_CAPTION, UPLINK_TITLE } from './canvasHelpers';

	interface Props {
		labels: readonly HudLabelItem[];
		badges: readonly HudBadgeItem[];
		badgesHidden: boolean;
		/** Screen-space resource cards and ownership headings, including their text. */
		obstacles?: readonly Rect[];
		viewportWidth?: number;
		viewportHeight?: number;
		/** 선택된 네트워크(스위치 선택) id. aria-pressed 는 이 값만 반영하고 호버 파생 active 는 시각 강조에만 쓴다. */
		selectedNetId?: string | null;
		onselectnet: (netId: string) => void;
		/** 첫 도착 진입 창. 참이면 존 라벨·배지가 존과 함께 페이드로 들어온다(HUD 는 화면 공간이라 opacity 만). */
		entering?: boolean;
	}

	let { labels, badges, badgesHidden, selectedNetId = null, onselectnet, entering = false, obstacles = [], viewportWidth = 0, viewportHeight = 0 }: Props = $props();
	const sizes = new SvelteMap<string, { w: number; h: number }>();
	const elements = new Map<Element, string>();
	let observer: ResizeObserver | undefined;
	function measure(element: HTMLElement, key: string) {
		const { width: w, height: h } = element.getBoundingClientRect();
		const previous = sizes.get(key);
		if (w > 0 && h > 0 && (previous?.w !== w || previous.h !== h)) sizes.set(key, { w, h });
	}
	function observeItem(element: HTMLElement, key: string) {
		elements.set(element, key);
		measure(element, key);
		observer?.observe(element);
		return { destroy() { observer?.unobserve(element); elements.delete(element); sizes.delete(key); } };
	}
	onMount(() => {
		if (typeof ResizeObserver === 'undefined') return;
		observer = new ResizeObserver((entries) => {
			for (const entry of entries) {
				const key = elements.get(entry.target);
				if (key) measure(entry.target as HTMLElement, key);
			}
		});
		for (const element of elements.keys()) observer.observe(element);
		return () => { observer?.disconnect(); observer = undefined; };
	});
	const placements = $derived.by(() => {
		const items = labels.map((l) => {
			const size = sizes.get(`network:${l.netId}`) ?? { w: Math.min(400, Math.max(160, l.avail)), h: 24 };
			return { key: `network:${l.netId}`, x: l.sx, y: l.sy - size.h / 2, ...size };
		});
		if (!badgesHidden) for (const b of badges) {
			const size = sizes.get(`badge:${b.key}`) ?? { w: 140, h: 40 };
			items.push({ key: `badge:${b.key}`, x: b.sx - size.w / 2, y: b.sy - size.h / 2, ...size });
		}
		return placeHudItems(items, obstacles, viewportWidth > 0 && viewportHeight > 0
			? { x: 6, y: 6, w: Math.max(0, viewportWidth - 12), h: Math.max(0, viewportHeight - 12) } : undefined);
	});
</script>

<div class="hud" class:motion-fade={entering} style:--hud-width="{viewportWidth > 0 ? Math.max(1, viewportWidth - 12) : 400}px">
	<svg class="hud-leaders" aria-hidden="true">
		{#each labels as l (l.netId)}
			{@const rect = placements.get(`network:${l.netId}`)!}
			{@const d = hudLeader({ x: l.sx, y: l.sy }, rect)}
			{#if d}<path {d} style:--net={l.color} class:is-dim={l.dim} />{/if}
		{/each}
	</svg>
	{#each labels as l (l.netId)}
		{@const rect = placements.get(`network:${l.netId}`)!}
		<button
			type="button"
			class="zone-label"
			use:observeItem={`network:${l.netId}`}
			class:is-active={l.active}
			class:is-dim={l.dim}
			data-summary={l.summary || undefined}
			data-hud-control
			data-zone-label={l.netId}
			aria-label={t('hud.selectNetwork', { name: l.name, cidr: l.cidrText })}
			aria-pressed={l.netId === selectedNetId}
			title={[l.name, l.cidrText, l.kindLabel, ...l.adminPills].filter(Boolean).join(' · ')}
			style:--net={l.color}
			style:--sx="{rect.x}px"
			style:--sy="{rect.y}px"
			onclick={() => onselectnet(l.netId)}
		>
			<span class="zone-swatch" aria-hidden="true"></span>
			<span class="zone-name">{l.name}</span>
			<span class="zone-cidr">{l.cidrText}</span>
			<span class="zone-pills">
				<Pill tone="neutral" size="xs">{l.kindLabel}</Pill>
				{#if l.isolated}<Pill tone="neutral" size="xs">{t('hud.isolated')}</Pill>{/if}
				{#if l.statusText}<Pill tone="neutral" size="xs">{l.statusText}</Pill>{/if}
			</span>
			{#if l.adminPills.length}
				<span class="zone-pills zone-admin">
					{#each l.adminPills as text (text)}
						<Pill tone="admin-tone" size="xs">{text}</Pill>
					{/each}
				</span>
			{/if}
		</button>
	{/each}
	{#if !badgesHidden}
		{#each badges as b (b.key)}
			{@const rect = placements.get(`badge:${b.key}`)!}
			<button
				type="button"
				class="trunk-badge"
				use:observeItem={`badge:${b.key}`}
				class:is-dim={b.dim}
				data-hud-control
				data-trunk-badge={b.key}
				title={UPLINK_TITLE()}
				aria-label={t('hud.trunkBadge', { name: b.netName, caption: UPLINK_CAPTION(), rate: b.rateText })}
				style:--sx="{rect.x}px"
				style:--sy="{rect.y}px"
				onclick={() => onselectnet(b.netId)}
			>
				<span class="badge-rate">{b.rateText}</span>
				<span class="badge-cap">{UPLINK_CAPTION()}</span>
			</button>
		{/each}
	{/if}
</div>

<style>
	.hud { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
	.hud-leaders { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }
	.hud-leaders path { fill: none; stroke: var(--net); stroke-width: 1; }
	.hud-leaders .is-dim { opacity: 0.35; }
	.zone-label {
		position: absolute;
		left: 0;
		top: 0;
		transform: translate(var(--sx), var(--sy));
		pointer-events: auto;
		display: inline-flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.375rem;
		min-height: 24px;
		padding: 0.125rem 0.5rem;
		border-radius: 999px;
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
		color: var(--color-ink-0);
		font: inherit;
		font-size: 0.75rem;
		font-weight: 600;
		white-space: normal;
		cursor: pointer;
		width: max-content;
		max-width: min(400px, var(--hud-width));
		transition: opacity var(--motion-duration-base) var(--motion-ease-standard);
	}
	.zone-label:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.zone-label.is-active { border-color: var(--net); }
	.zone-label.is-dim { opacity: 0.35; }
	.zone-swatch { width: 8px; height: 8px; border-radius: 999px; background: var(--net); flex-shrink: 0; }
	.zone-name { min-width: 0; overflow-wrap: anywhere; }
	.zone-cidr { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-weight: 400; color: var(--color-ink-2); overflow-wrap: anywhere; }
	.zone-pills { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 0.25rem; }
	.zone-label[data-summary] .zone-cidr { font-family: var(--font-sans); }
	.zone-label[data-summary] .zone-pills { display: none; }
	.trunk-badge {
		position: absolute;
		left: 0;
		top: 0;
		transform: translate(var(--sx), var(--sy));
		pointer-events: auto;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0;
		padding: 0.125rem 0.5rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
		color: var(--color-ink-0);
		font: inherit;
		cursor: pointer;
		line-height: 1.35;
		transition: opacity var(--motion-duration-base) var(--motion-ease-standard);
	}
	.trunk-badge:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.trunk-badge.is-dim { opacity: 0.3; }
	.badge-rate { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: 0.75rem; font-weight: 500; white-space: nowrap; }
	.badge-cap { font-size: 0.75rem; color: var(--color-ink-2); white-space: nowrap; }
</style>
