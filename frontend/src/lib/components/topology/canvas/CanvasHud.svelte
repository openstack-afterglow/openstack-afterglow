<script module lang="ts">
	export type HudLabelSize = 'full' | 'mid' | 'min';

	export interface HudLabelItem {
		netId: string;
		name: string;
		cidrText: string;
		kindLabel: string;
		/** 외부(프로바이더) 네트워크 — 인터넷 경계임을 구름 아이콘과 배지로 표시한다 */
		isInternet: boolean;
		isolated: boolean;
		/** ACTIVE 가 아닐 때만 채움 */
		statusText: string | null;
		/** 관리자 보기 전용 pill 텍스트(VLAN 태그/VXLAN VNI, MTU) */
		adminPills: string[];
		color: string;
		sx: number;
		sy: number;
		avail: number;
		size: HudLabelSize;
		active: boolean;
		dim: boolean;
	}

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
	// 스크린 공간 HUD: 존 라벨 칩과 트렁크 배지. 버튼에만 pointer-events 를 준다.
	import Pill from '$lib/components/ui/Pill.svelte';
	import { TRUNK_CAPTION, TRUNK_TITLE } from './canvasHelpers';

	interface Props {
		labels: readonly HudLabelItem[];
		badges: readonly HudBadgeItem[];
		badgesHidden: boolean;
		/** 선택된 네트워크(스위치 선택) id. aria-pressed 는 이 값만 반영하고 호버 파생 active 는 시각 강조에만 쓴다. */
		selectedNetId?: string | null;
		onselectnet: (netId: string) => void;
	}

	let { labels, badges, badgesHidden, selectedNetId = null, onselectnet }: Props = $props();
</script>

<div class="hud">
	{#each labels as l (l.netId)}
		<button
			type="button"
			class="zone-label lbl-{l.size}"
			class:is-active={l.active}
			class:is-dim={l.dim}
			data-hud-control
			data-zone-label={l.netId}
			aria-label="네트워크 {l.name} {l.cidrText} 선택"
			aria-pressed={l.netId === selectedNetId}
			style:--net={l.color}
			style:--sx="{l.sx}px"
			style:--sy="{l.sy}px"
			style:--avail="{l.avail}px"
			onclick={() => onselectnet(l.netId)}
		>
			{#if l.isInternet}
				<span class="zone-cloud" aria-hidden="true"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.6 10.6a2.4 2.4 0 0 1 .3-4.78 3.3 3.3 0 0 1 6.32-.6A2.6 2.6 0 0 1 11.6 10.6z" /><path d="M8 10.6v2.2M4.4 12.8h7.2" /></svg></span>
			{:else}
				<span class="zone-swatch" aria-hidden="true"></span>
			{/if}
			<span class="zone-name">{l.name}</span>
			<span class="zone-cidr">{l.cidrText}</span>
			<span class="zone-pills">
				{#if l.isInternet}<Pill tone="warm" size="xs">인터넷</Pill>{/if}
				<Pill tone="neutral" size="xs">{l.kindLabel}</Pill>
				{#if l.isolated}<Pill tone="neutral" size="xs">격리</Pill>{/if}
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
			<button
				type="button"
				class="trunk-badge"
				class:is-dim={b.dim}
				data-hud-control
				data-trunk-badge={b.key}
				title={TRUNK_TITLE}
				aria-label="{b.netName} 트렁크 배지 ({TRUNK_CAPTION}) {b.rateText}"
				style:--sx="{b.sx}px"
				style:--sy="{b.sy}px"
				onclick={() => onselectnet(b.netId)}
			>
				<span class="badge-rate">{b.rateText}</span>
				<span class="badge-cap">{TRUNK_CAPTION}</span>
			</button>
		{/each}
	{/if}
</div>

<style>
	.hud { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
	.zone-label {
		position: absolute;
		left: 0;
		top: 0;
		transform: translate(var(--sx), var(--sy)) translateY(-50%);
		pointer-events: auto;
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		height: 24px;
		padding: 0 0.5rem;
		border-radius: 999px;
		border: 1px solid var(--color-line);
		background: var(--color-surface-raised);
		color: var(--color-ink-0);
		font: inherit;
		font-size: 0.75rem;
		font-weight: 600;
		white-space: nowrap;
		cursor: pointer;
		max-width: var(--avail, 400px);
		overflow: hidden;
		transition: opacity var(--motion-duration-base) var(--motion-ease-standard);
	}
	.zone-label:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.zone-label.is-active { border-color: var(--net); }
	.zone-label.is-dim { opacity: 0.35; }
	.zone-cloud { display: inline-flex; color: var(--net); flex-shrink: 0; }
	.zone-cloud svg { width: 14px; height: 14px; }
	.zone-swatch { width: 8px; height: 8px; border-radius: 999px; background: var(--net); flex-shrink: 0; }
	.zone-name { overflow: hidden; text-overflow: ellipsis; min-width: 0; }
	.zone-cidr { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-weight: 400; color: var(--color-ink-2); }
	.zone-pills { display: inline-flex; align-items: center; gap: 0.25rem; }
	.lbl-min .zone-cidr, .lbl-min .zone-pills { display: none; }
	.lbl-mid .zone-cidr, .lbl-mid .zone-admin { display: none; }
	.trunk-badge {
		position: absolute;
		left: 0;
		top: 0;
		transform: translate(var(--sx), var(--sy)) translate(-50%, -50%);
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
