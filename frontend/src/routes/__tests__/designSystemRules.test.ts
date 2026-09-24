// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { existsSync, lstatSync, readFileSync, readlinkSync } from 'node:fs';
import { resolve } from 'node:path';

const repoRoot = resolve(__dirname, '../../..');
const layoutSource = readFileSync(resolve(repoRoot, 'src/routes/layout.css'), 'utf8');
const designSource = readFileSync(resolve(repoRoot, '../DESIGN.md'), 'utf8');
const readmeSource = readFileSync(resolve(repoRoot, 'README.md'), 'utf8');
const agentsPath = resolve(repoRoot, '../AGENTS.md');
const agentsSource = existsSync(agentsPath) ? readFileSync(agentsPath, 'utf8') : '';
const claudePath = resolve(repoRoot, '../CLAUDE.md');
const alertSource = readFileSync(resolve(repoRoot, 'src/lib/components/ui/Alert.svelte'), 'utf8');
const uiIndexSource = readFileSync(resolve(repoRoot, 'src/lib/components/ui/index.ts'), 'utf8');
const tokenSource = readFileSync(resolve(repoRoot, 'src/lib/design/tokens.ts'), 'utf8');

const editorialTokenNames = [
	'--gradient-editorial-canvas',
	'--pattern-editorial-grid',
	'--gradient-editorial-grid-mask',
	'--gradient-editorial-cta',
	'--color-surface-editorial-media',
];


const chatMessageTokenNames = [
	'--chat-message-gap',
	'--chat-message-meta-gap',
	'--chat-message-meta-inset',
	'--chat-message-meta-size',
	'--chat-message-radius',
	'--chat-message-directional-corner',
	'--chat-message-padding-block',
	'--chat-message-padding-inline',
	'--chat-message-assistant-max-inline',
	'--chat-message-user-max-inline',
];

const designTokenNames = [
	'--color-surface-canvas',
	'--color-surface-base',
	'--color-surface-raised',
	'--color-surface-sunken',
	'--color-surface-selected',
	'--color-surface-scrim',
	'--color-surface-scrim-soft',
	'--color-ink-0',
	'--color-ink-1',
	'--color-ink-2',
	'--color-ink-3',
	'--color-line',
	'--color-line-2',
	'--color-accent',
	'--color-accent-2',
	'--color-warm',
	'--color-warm-2',
	'--color-state-success',
	'--color-state-warning',
	'--color-state-danger',
	'--color-state-info',
	'--color-state-neutral',
];

// 토폴로지 캔버스 도메인 토큰 — layout.css(dark/light)와 DESIGN.md 예외 목록에 모두 존재해야 한다.
const topologyTokenNames = [
	'--color-topology-gateway',
	'--color-topology-internal-2',
	'--topology-zone-fill-alpha',
	'--topology-zone-fill-alpha-active',
	'--color-topology-grid-minor',
	'--color-topology-grid-major',
];

const layerTokenNames = [
	'--z-sidebar',
	'--z-header',
	'--z-panel',
	'--z-modal',
	'--z-toast',
	'--z-confirmation',
	'--z-popover',
	'--z-command',
];

const motionTokenNames = [
	'--motion-duration-fast',
	'--motion-duration-base',
	'--motion-duration-panel',
	'--motion-duration-data',
	'--motion-duration-status-pulse',
	'--motion-ease-standard',
	'--motion-ease-out',
	'--motion-ease-in-out',
];

// 시맨틱 톤은 채움용 값과 글자용 값을 따로 갖는다. 채움 값을 글자에 쓰면 라이트에서 AA 미달이다.
const toneTextTokenNames = [
	'--color-warm-text',
	'--color-warm-text-hover',
	'--color-state-success-text',
	'--color-state-warning-text',
	'--color-state-danger-text',
	'--color-state-info-text',
	'--color-state-neutral-text',
];

// Tailwind 4 는 @theme static 안에 선언된 --color-* 에서만 유틸리티를 만든다. :root 에 선언하면
// 클래스가 조용히 아무 규칙도 만들지 않는다 — action-warm 계열이 실제로 그래서 죽어 있었다.
const themeScopedColorNames = [
	'--color-action-warm',
	'--color-action-warm-hover',
	'--color-action-on-warm',
	'--color-action-on-accent',
];

const radiusTokenNames = ['--radius-sm', '--radius-md', '--radius-lg', '--radius-xl'];

// Elevation은 부유 레이어 전용이다. 이름만 있고 정의가 없으면 box-shadow 가 none 으로 계산되어
// 모달·팝오버 depth 가 조용히 사라지므로, 세 토큰 모두 런타임·TS·문서에 동시에 존재해야 한다.
const elevationTokenNames = ['--shadow-restraint', '--shadow-popover', '--shadow-overlay-compact'];

// Material 은 테마별 alpha 두 개와 테마 공통 blur 두 개로 나뉜다.
const materialAlphaTokenNames = ['--material-chrome-alpha', '--material-overlay-alpha'];
const materialBlurTokenNames = ['--material-chrome-blur', '--material-scrim-blur'];

const motionDurationExports = [
	'fast: 120',
	'base: 160',
	'panel: 200',
	'data: 500',
	'statusPulse: 1400',
	"REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'",
];

const scrimThemeDeclarations = [
	'--color-surface-scrim: rgb(0 0 0 / 60%)',
	'--color-surface-scrim-soft: rgb(0 0 0 / 50%)',
];

const layerCssVars = [
	"sidebar: 'var(--z-sidebar)'",
	"header: 'var(--z-header)'",
	"panel: 'var(--z-panel)'",
	"modal: 'var(--z-modal)'",
	"toast: 'var(--z-toast)'",
	"confirmation: 'var(--z-confirmation)'",
	"popover: 'var(--z-popover)'",
	"command: 'var(--z-command)'",
];

const motionCssVars = [
	"durationFast: 'var(--motion-duration-fast)'",
	"durationBase: 'var(--motion-duration-base)'",
	"durationPanel: 'var(--motion-duration-panel)'",
	"durationData: 'var(--motion-duration-data)'",
	"durationStatusPulse: 'var(--motion-duration-status-pulse)'",
	"easeStandard: 'var(--motion-ease-standard)'",
	"easeOut: 'var(--motion-ease-out)'",
	"easeInOut: 'var(--motion-ease-in-out)'",
];

const requiredUiExports = [
	'Alert',
	'Button',
	'Card',
	'Field',
	'TextInput',
	'SelectInput',
	'ChatBubble',
	'TextareaInput',
	'TableShell',
	'ToggleGroup',
	'UsageBar',
	'StatusChip',
	'Pill',
];

describe('design system source contracts', () => {
	it('keeps layout.css as the token authority with the legacy override boundary', () => {
		expect(layoutSource).toContain('@theme static');
		expect(layoutSource).toContain(':root.light');
		expect(layoutSource).toContain('Legacy light-mode compatibility overrides');
		for (const token of designTokenNames) expect(layoutSource).toContain(token);
		for (const token of topologyTokenNames) expect(layoutSource).toContain(token);
	});

	it('keeps DESIGN.md as the canonical new-entity rulebook', () => {
		expect(designSource).toContain('새 색상·gradient·badge tone·table density·form control·card treatment가 필요하면');
		expect(designSource).toContain('새 route/component file은 raw hex');
		for (const token of designTokenNames) expect(designSource).toContain(token);
		for (const token of topologyTokenNames) expect(designSource).toContain(token);
	});

	it('defines responsive hierarchy and makes it mandatory agent guidance', () => {
		for (const rule of [
			'mobile is `<768px`; tablet is `md` (`768–1023px`); desktop is `lg` (`≥1024px`)',
			'**Mobile (<768px).**',
			'**Tablet (768–1023px).**',
			'**Desktop (≥1024px).**',
			'`TableShell` stays horizontally scrollable with headers intact',
			'PageHeader remains stacked and its actions wrap',
			'Test every new or materially changed visual flow at mobile, tablet, desktop, 767/768, and 1023/1024 cutovers.',
		]) {
			expect(designSource).toContain(rule);
		}
		expect(agentsSource).toContain('`Layout & responsive hierarchy`까지 읽고');
		expect(agentsSource).toContain('mobile (`<768px`), tablet (`768–1023px`), desktop (`≥1024px`)');
	});

	it('keeps editorial public-surface tokens and panel composition documented', () => {
		for (const token of editorialTokenNames) {
			expect(layoutSource).toContain(token);
			expect(tokenSource).toContain(token);
			expect(designSource).toContain(token);
		}
		expect(tokenSource).toContain('EDITORIAL_CSS_VAR');
		expect(designSource).toContain('Approved panel composition');
		expect(designSource).toContain('Card surface="subtle"');
		expect(designSource).toContain('method matrix is one Card');
	});

	it('defines the reusable chat message primitive and its shared layout tokens', () => {
		for (const token of chatMessageTokenNames) {
			expect(layoutSource).toContain(token);
			expect(tokenSource).toContain(token);
			expect(designSource).toContain(token);
		}
		expect(tokenSource).toContain('CHAT_MESSAGE_CSS_VAR');
		expect(designSource).toContain('ChatBubble');
		expect(designSource).toContain('chat-start');
		expect(designSource).toContain('chat-end');
	});

	it('keeps radius and elevation tokens aligned across runtime, TypeScript, and documentation', () => {
		for (const token of [...radiusTokenNames, ...elevationTokenNames]) {
			expect(layoutSource).toContain(token);
			expect(tokenSource).toContain(token);
			expect(designSource).toContain(token);
		}
		expect(tokenSource).toContain('RADIUS_CSS_VAR');
		expect(tokenSource).toContain('ELEVATION_CSS_VAR');
		// 정의 없는 var() 는 box-shadow 를 none 으로 만든다: 각 토큰은 :root 에서 실제 값을 가져야 한다.
		for (const token of elevationTokenNames) {
			expect(layoutSource).toMatch(new RegExp(`${token}:\\s*0 `));
		}
		// 라이트 테마는 어두운 그림자를 재사용하지 않고 별도 알파를 갖는다.
		const lightStart = layoutSource.indexOf(':root.light {');
		const darkBlock = layoutSource.slice(0, lightStart);
		const lightBlock = layoutSource.slice(lightStart);
		const valueOf = (block: string, token: string) =>
			block.match(new RegExp(`${token}:\\s*([^;]+);`))?.[1].trim();
		for (const token of elevationTokenNames) {
			const darkValue = valueOf(darkBlock, token);
			const lightValue = valueOf(lightBlock, token);
			expect(darkValue).toBeTruthy();
			expect(lightValue).toBeTruthy();
			expect(lightValue).not.toBe(darkValue);
		}
	});

	it('keeps the material confined to the floating layer and failing safe to an opaque surface', () => {
		const materialTokenNames = [...materialAlphaTokenNames, ...materialBlurTokenNames];
		for (const token of materialTokenNames) {
			expect(layoutSource).toContain(token);
			expect(tokenSource).toContain(token);
			expect(designSource).toContain(token);
		}
		expect(tokenSource).toContain('MATERIAL_CSS_VAR');

		const lightStart = layoutSource.indexOf(':root.light {');
		const darkBlock = layoutSource.slice(0, lightStart);
		const lightBlock = layoutSource.slice(lightStart);
		const valueOf = (block: string, token: string) =>
			block.match(new RegExp(`${token}:\\s*([^;]+);`))?.[1].trim();
		// alpha 는 테마마다 달라야 한다: 어두운 표면용 값을 흰 표면에 그대로 쓰면 비쳐 보이지 않는다.
		for (const token of materialAlphaTokenNames) {
			expect(valueOf(darkBlock, token)).toBeTruthy();
			expect(valueOf(lightBlock, token)).toBeTruthy();
			expect(valueOf(lightBlock, token)).not.toBe(valueOf(darkBlock, token));
		}
		// blur 는 한 값만 둔다: 라이트 블록에 다시 정의하면 의도가 깨진 것이다.
		for (const token of materialBlurTokenNames) {
			expect(valueOf(darkBlock, token)).toBeTruthy();
			expect(valueOf(lightBlock, token)).toBeUndefined();
		}

		// 불투명이 기본 선언이고 반투명은 향상이다. 세 블록의 명시도가 같으므로 순서가 계약이다:
		// 접근성 보정이 @supports 뒤에 와야 조용히 덮이지 않는다.
		const enhancement = layoutSource.indexOf('@supports ((backdrop-filter: blur(1px))');
		const reducedTransparency = layoutSource.indexOf('prefers-reduced-transparency');
		const forcedColors = layoutSource.indexOf('@media (forced-colors: active) {\n  .material-chrome');
		expect(enhancement).toBeGreaterThan(-1);
		expect(reducedTransparency).toBeGreaterThan(enhancement);
		expect(forcedColors).toBeGreaterThan(enhancement);
		expect(layoutSource).toContain('color-mix(in oklab, var(--color-surface-base) var(--material-chrome-alpha)');
	});

	it('keeps tone text tokens and action colours declared where Tailwind can see them', () => {
		const themeStart = layoutSource.indexOf('@theme static');
		const themeEnd = layoutSource.indexOf('\n}', themeStart);
		const themeBlock = layoutSource.slice(themeStart, themeEnd);
		for (const token of themeScopedColorNames) {
			expect(themeBlock).toContain(token);
			expect(designSource).toContain(token);
		}
		for (const token of toneTextTokenNames) {
			expect(themeBlock).toContain(token);
		}
		// 라이트는 채움 톤을 글자에 재사용하지 않는다: 다섯 톤 모두 별도 값을 가져야 한다.
		const lightBlock = layoutSource.slice(layoutSource.indexOf(':root.light {'));
		for (const token of ['--color-state-success-text', '--color-state-warning-text', '--color-state-danger-text', '--color-state-info-text', '--color-state-neutral-text']) {
			expect(lightBlock).toContain(token);
		}
		// 경고/오류 배너의 글자는 톤이 아니라 톤의 텍스트 형제를 쓴다.
		expect(alertSource).toContain('--alert-text: var(--color-state-danger-text)');
		expect(alertSource).not.toContain('color: var(--alert-tone);');
	});

	it('links tracked frontend docs and optional local agent instructions to the canonical design system', () => {
		expect(readmeSource).toContain('../DESIGN.md');
		if (agentsSource) expect(agentsSource).toContain('프론트엔드 UI/UX 디자인 시스템');
	});

	it('exports the reusable primitives required for new UI work', () => {
		for (const componentName of requiredUiExports) {
			expect(uiIndexSource).toContain(`export { default as ${componentName} }`);
		}
	});
	it('keeps semantic scrims in the Tailwind theme authority', () => {
		const themeSource = layoutSource.slice(layoutSource.indexOf('@theme static'), layoutSource.indexOf('/* Runtime design variables */'));
		for (const declaration of scrimThemeDeclarations) expect(themeSource).toContain(declaration);
		expect(layoutSource).toContain('--color-surface-scrim: rgb(0 0 0 / 25%)');
		expect(layoutSource).toContain('--color-surface-scrim-soft: rgb(0 0 0 / 20%)');
	});

	it('keeps layer tokens aligned across runtime, TypeScript, and documentation', () => {
		for (const token of layerTokenNames) {
			expect(layoutSource).toContain(token);
			expect(designSource).toContain(token);
		}
		expect(tokenSource).toContain('LAYER_CSS_VAR');
		for (const cssVar of layerCssVars) expect(tokenSource).toContain(cssVar);
		expect(tokenSource).toContain('LAYOUT_CSS_VAR');
		expect(tokenSource).toContain("headerHeight: 'var(--app-header-height)'");
		expect(tokenSource).toContain("sidebarWidth: 'var(--app-sidebar-width)'");
	});

	it('keeps motion tokens and reduced-motion behavior aligned', () => {
		for (const token of motionTokenNames) {
			expect(layoutSource).toContain(token);
			expect(tokenSource).toContain(token);
			expect(designSource).toContain(token);
		}
		expect(tokenSource).toContain('MOTION_CSS_VAR');
		for (const cssVar of motionCssVars) expect(tokenSource).toContain(cssVar);
		for (const expectedExport of motionDurationExports) expect(tokenSource).toContain(expectedExport);
		expect(layoutSource).toContain('--default-transition-duration: 0.01ms');
		expect(layoutSource).toContain('--default-animation-duration: 0.01ms');
		expect(layoutSource).toContain('transition-duration: 0.01ms !important');
		expect(layoutSource).toContain('animation-duration: 0.01ms !important');
		expect(layoutSource).toContain('animation-delay: 0ms !important');
		expect(layoutSource).toContain('animation-iteration-count: 1 !important');
		expect(layoutSource).toContain('transition-delay: 0ms !important');
	});

	it('documents interaction ownership and UsageBar edge-case behavior', () => {
		for (const owner of [
			'`ToggleGroup` owns compact mutually exclusive',
			'`SelectionCheckbox` owns checked, indeterminate, disabled, and unavailable-X semantics',
			'`SelectionToolbar` owns the select-all control, selected count, and `onToggle`',
			'`BulkSelectionOverlay` owns the selected-count, busy, and bulk-action presentation',
			'`ActionMenu` owns the overflow trigger, fixed popover placement, outside-click/Escape dismissal',
			'clamps invalid or out-of-range percentages to `0–100`',
			'for `max={-1}` labels the quota `무제한` without a percentage or fill',
		]) {
			expect(designSource).toContain(owner);
		}
	});
	it('keeps AGENTS.md as the single instruction source', () => {
		expect(lstatSync(claudePath).isSymbolicLink()).toBe(true);
		expect(readlinkSync(claudePath)).toBe('AGENTS.md');
		expect(agentsSource).toContain('프론트엔드 UI/UX 디자인 시스템');
	});
});
