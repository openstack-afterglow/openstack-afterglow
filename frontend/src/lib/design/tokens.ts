export const DESIGN_TONES = ['accent', 'warm', 'success', 'warning', 'danger', 'info', 'neutral', 'admin-tone'] as const;
export type DesignTone = (typeof DESIGN_TONES)[number];

export const TONE_CSS_VAR: Record<DesignTone, string> = {
	accent: 'var(--color-accent)',
	warm: 'var(--color-warm)',
	success: 'var(--color-state-success)',
	warning: 'var(--color-state-warning)',
	danger: 'var(--color-state-danger)',
	info: 'var(--color-state-info)',
	neutral: 'var(--color-state-neutral)',
	'admin-tone': 'var(--admin-tone)',
};

export const TEXT_CSS_VAR = {
	primary: 'var(--color-ink-0)',
	secondary: 'var(--color-ink-1)',
	muted: 'var(--color-ink-2)',
	warm: 'var(--color-warm-text)',
	success: 'var(--color-state-success-text)',
} as const;

export const SURFACE_CSS_VAR = {
	canvas: 'var(--color-surface-canvas)',
	base: 'var(--color-surface-base)',
	raised: 'var(--color-surface-raised)',
	sunken: 'var(--color-surface-sunken)',
	selected: 'var(--color-surface-selected)',
	scrim: 'var(--color-surface-scrim)',
	scrimSoft: 'var(--color-surface-scrim-soft)',
} as const;

export const FONT_CSS_VAR = {
	sans: 'var(--font-sans)',
	display: 'var(--font-display)',
	mono: 'var(--font-mono)',
} as const;

export const LAYOUT_CSS_VAR = {
	headerHeight: 'var(--app-header-height)',
	sidebarWidth: 'var(--app-sidebar-width)',
} as const;

export const LAYER_CSS_VAR = {
	sidebar: 'var(--z-sidebar)',
	header: 'var(--z-header)',
	panel: 'var(--z-panel)',
	modal: 'var(--z-modal)',
	toast: 'var(--z-toast)',
	confirmation: 'var(--z-confirmation)',
	popover: 'var(--z-popover)',
	command: 'var(--z-command)',
} as const;

export const RADIUS_CSS_VAR = {
	sm: 'var(--radius-sm)',
	md: 'var(--radius-md)',
	lg: 'var(--radius-lg)',
	xl: 'var(--radius-xl)',
	capsule: '999px',
} as const;

/**
 * Elevation은 부유 레이어 전용이다. restraint 는 트리거에 붙지 않은 다이얼로그·패널,
 * popover 는 트리거에 앵커된 표면, compact 는 20rem 미만의 작은 부유 표면에 쓴다.
 * 콘텐츠 레이어(Card·TableShell·StatTile)는 그림자를 갖지 않는다.
 */
export const ELEVATION_CSS_VAR = {
	restraint: 'var(--shadow-restraint)',
	popover: 'var(--shadow-popover)',
	compact: 'var(--shadow-overlay-compact)',
} as const;

/**
 * Material 은 부유 레이어 전용이다. alpha 는 "표면이 얼마나 남는가"이므로 값이 클수록 불투명하다.
 * 라이트는 흰 표면이 훨씬 잘 비쳐서 더 불투명해야 하므로 테마별 값이 다르고,
 * blur 반경은 의도적으로 두 테마가 같은 값을 쓴다.
 */
export const MATERIAL_CSS_VAR = {
	chromeAlpha: 'var(--material-chrome-alpha)',
	overlayAlpha: 'var(--material-overlay-alpha)',
	chromeBlur: 'var(--material-chrome-blur)',
	scrimBlur: 'var(--material-scrim-blur)',
} as const;

export const MOTION_CSS_VAR = {
	durationFast: 'var(--motion-duration-fast)',
	durationBase: 'var(--motion-duration-base)',
	durationPanel: 'var(--motion-duration-panel)',
	durationData: 'var(--motion-duration-data)',
	durationStatusPulse: 'var(--motion-duration-status-pulse)',
	easeStandard: 'var(--motion-ease-standard)',
	easeOut: 'var(--motion-ease-out)',
	easeInOut: 'var(--motion-ease-in-out)',
} as const;

export const MOTION_DURATION_MS = {
	fast: 120,
	base: 160,
	panel: 200,
	data: 500,
	statusPulse: 1400,
} as const;

export const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)' as const;

export const EDITORIAL_CSS_VAR = {
	canvas: 'var(--gradient-editorial-canvas)',
	grid: 'var(--pattern-editorial-grid)',
	gridMask: 'var(--gradient-editorial-grid-mask)',
	cta: 'var(--gradient-editorial-cta)',
	mediaSurface: 'var(--color-surface-editorial-media)',
} as const;

export const CHART_COLORS = [
	'var(--color-chart-1)',
	'var(--color-chart-2)',
	'var(--color-chart-3)',
	'var(--color-chart-4)',
	'var(--color-chart-5)',
	'var(--color-chart-6)',
] as const;

export const TOPOLOGY_COLORS = {
	external: 'var(--color-topology-external)',
	shared: 'var(--color-topology-shared)',
	internal: 'var(--color-topology-internal)',
	router: 'var(--color-topology-router)',
	link: 'var(--color-topology-link)',
	gateway: 'var(--color-topology-gateway)',
	internal2: 'var(--color-topology-internal-2)',
} as const;

/**
 * 토폴로지 캔버스 뷰 전용 CSS 변수 이름.
 * 존 채움은 color-mix()에 alpha 토큰을 넣어 계산하고, 그리드 선은 minor/major 두 단계만 사용한다.
 * 값이 아니라 변수 이름이므로 getPropertyValue / var() 양쪽에서 쓸 수 있다.
 */
export const TOPOLOGY_CANVAS_CSS_VAR = {
	zoneFillAlpha: '--topology-zone-fill-alpha',
	zoneFillAlphaActive: '--topology-zone-fill-alpha-active',
	gridMinor: '--color-topology-grid-minor',
	gridMajor: '--color-topology-grid-major',
} as const;

export function usageTone(
	percent: number,
	thresholds: { warning: number; danger: number } = { warning: 80, danger: 95 },
): 'accent' | 'warning' | 'danger' {
	if (percent >= thresholds.danger) return 'danger';
	if (percent >= thresholds.warning) return 'warning';
	return 'accent';
}

export const CHAT_MESSAGE_CSS_VAR = {
	gap: 'var(--chat-message-gap)',
	metaGap: 'var(--chat-message-meta-gap)',
	metaInset: 'var(--chat-message-meta-inset)',
	metaSize: 'var(--chat-message-meta-size)',
	radius: 'var(--chat-message-radius)',
	directionalCorner: 'var(--chat-message-directional-corner)',
	paddingBlock: 'var(--chat-message-padding-block)',
	paddingInline: 'var(--chat-message-padding-inline)',
	assistantMaxInline: 'var(--chat-message-assistant-max-inline)',
	userMaxInline: 'var(--chat-message-user-max-inline)'
} as const;

export const SCROLLBAR_CSS_VAR = {
	size: 'var(--scrollbar-size)',
	track: 'var(--scrollbar-track)',
	thumb: 'var(--scrollbar-thumb)',
	thumbHover: 'var(--scrollbar-thumb-hover)'
} as const;
