// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const repoRoot = resolve(__dirname, '../../..');
const layoutSource = readFileSync(resolve(repoRoot, 'src/routes/layout.css'), 'utf8');
const designSource = readFileSync(resolve(repoRoot, '../DESIGN.md'), 'utf8');
const alertSource = readFileSync(resolve(repoRoot, 'src/lib/components/ui/Alert.svelte'), 'utf8');
const uiIndexSource = readFileSync(resolve(repoRoot, 'src/lib/components/ui/index.ts'), 'utf8');
const tokenSource = readFileSync(resolve(repoRoot, 'src/lib/design/tokens.ts'), 'utf8');
const source = (path: string) => readFileSync(resolve(repoRoot, 'src', path), 'utf8');



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

const afterglowArtworkTokenNames = [
	'--afterglow-artwork-base',
	'--afterglow-artwork-warm',
	'--afterglow-artwork-light',
	'--afterglow-artwork-ink',
	'--afterglow-artwork-muted',
];

const motionTokenNames = [
	'--motion-duration-fast',
	'--motion-duration-base',
	'--motion-duration-panel',
	'--motion-duration-data',
	'--motion-duration-scene',
	'--motion-ease-standard',
	'--motion-ease-out',
	'--motion-ease-in-out',
	'--motion-duration-shimmer',
	'--motion-duration-stagger',
	'--motion-ease-emphasized',
	'--motion-sheen',
];

// 반복 loop의 정지 frame을 보장하려면 새 duration도 reduced-motion 블록에서 0으로 수렴해야 한다.
const reducedMotionDurationDeclarations = [
	'--motion-duration-scene: 0.01ms',
	'--motion-duration-shimmer: 0.01ms',
	'--motion-duration-stagger: 0ms',
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
	'scene: 720',
	'shimmer: 1600',
	'stagger: 40',
	"REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'",
];

const scrimThemeDeclarations = [
	'--color-surface-scrim: rgb(0 0 0 / 60%)',
	'--color-surface-scrim-soft: rgb(0 0 0 / 50%)',
];

const motionCssVars = [
	"durationFast: 'var(--motion-duration-fast)'",
	"durationBase: 'var(--motion-duration-base)'",
	"durationPanel: 'var(--motion-duration-panel)'",
	"durationData: 'var(--motion-duration-data)'",
	"durationScene: 'var(--motion-duration-scene)'",
	"easeStandard: 'var(--motion-ease-standard)'",
	"easeOut: 'var(--motion-ease-out)'",
	"easeInOut: 'var(--motion-ease-in-out)'",
	"durationShimmer: 'var(--motion-duration-shimmer)'",
	"durationStagger: 'var(--motion-duration-stagger)'",
	"easeEmphasized: 'var(--motion-ease-emphasized)'",
	"sheen: 'var(--motion-sheen)'",
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
	'ProgressTrack',
	'StepProgress',
	'ProvisionPipeline',
	'AnimatedNumber',
];

describe('design system source contracts', () => {
	it('keeps layout.css as the token authority with the legacy override boundary', () => {
		expect(layoutSource).toContain('@theme static');
		expect(layoutSource).toContain(':root.light');
		expect(layoutSource).toContain('Legacy light-mode compatibility overrides');
		for (const token of designTokenNames) expect(layoutSource).toContain(token);
		for (const token of topologyTokenNames) expect(layoutSource).toContain(token);
		for (const token of afterglowArtworkTokenNames) {
			expect(layoutSource).toContain(`${token}:`);
			expect(tokenSource).toContain(`var(${token})`);
		}
	});

	it('maps authored artwork to the existing live console palette rather than a fixed dark color island', () => {
		for (const [artwork, semantic] of [
			['base', 'surface-canvas'], ['warm', 'warm-text'], ['light', 'warm-2'], ['ink', 'ink-0'], ['muted', 'ink-2'],
		]) expect(layoutSource).toContain(`--afterglow-artwork-${artwork}: var(--color-${semantic});`);
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

	it('keeps neutral washes and legacy state copy on readable text roles', () => {
		const darkBlock = layoutSource.slice(0, layoutSource.indexOf(':root.light {'));
		expect(darkBlock).toContain('--color-state-neutral-text: var(--color-ink-2);');
		expect(layoutSource.slice(layoutSource.indexOf(':root.light {'))).toContain('--color-action-warm-hover: color-mix(in oklab, var(--color-warm) 88%, var(--color-surface-base));');
		for (const [legacy, semantic] of [
			['green-400', 'state-success-text'],
			['green-300', 'state-success-text'],
			['red-400', 'state-danger-text'],
			['yellow-400', 'state-warning-text'],
			['red-300', 'state-danger-text'],
			['orange-400', 'warm-text'],
		]) {
			expect(layoutSource).toContain(`:root.light .text-${legacy} { color: var(--color-${semantic}) !important; }`);
		}
		expect(layoutSource).toMatch(/:root :is\(input, textarea\)::placeholder\s*\{\s*color: var\(--color-ink-2\);\s*opacity: 1;/);
		expect(source('lib/components/chat/ChatWindow.svelte')).toMatch(/\.error-bar\s*\{[^}]*color: var\(--color-state-danger-text\);/);
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

	it('keeps motion tokens and reduced-motion behavior aligned', () => {
		for (const token of motionTokenNames) {
			expect(layoutSource).toContain(token);
			expect(tokenSource).toContain(token);
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
		const reducedBlock = layoutSource.slice(layoutSource.indexOf('@media (prefers-reduced-motion: reduce)'));
		for (const declaration of reducedMotionDurationDeclarations) expect(reducedBlock).toContain(declaration);
	});

	it('never defines a motion curve that overshoots its resting value', () => {
		// A cubic-bezier control point with y outside 0..1 springs past the target (bounce/elastic).
		const curves = [...layoutSource.matchAll(/cubic-bezier\(([^)]+)\)/g), ...tokenSource.matchAll(/cubic-bezier\(([^)]+)\)/g)];
		expect(curves.length).toBeGreaterThan(0);
		for (const [, args] of curves) {
			const [, y1, , y2] = args.split(',').map((value) => Number.parseFloat(value));
			expect(y1).toBeGreaterThanOrEqual(0);
			expect(y1).toBeLessThanOrEqual(1);
			expect(y2).toBeGreaterThanOrEqual(0);
			expect(y2).toBeLessThanOrEqual(1);
		}
	});

	it('keeps tutorial invitations and hints in header flow instead of covering controls', () => {
		const tutorial = source('lib/tutorial/TutorialStartButton.svelte');
		expect(tutorial).not.toContain('position: absolute');
		expect(tutorial).not.toContain('position: fixed');
		expect(tutorial).not.toContain('role="dialog"');
		expect(tutorial).not.toContain('keyframes');
	});

	it('uses embedded lists and flat feedback within dashboard sections', () => {
		expect(source('routes/dashboard/usage/+page.svelte')).toContain('<ResponsiveTable embedded');
		expect(source('lib/components/account/ProjectSettingsSection.svelte')).toContain('<ResponsiveTable embedded');
		const lifecycle = source('lib/components/account/ProjectLifecycleSection.svelte');
		expect(lifecycle).not.toContain('rounded-lg');
		for (const alert of lifecycle.matchAll(/<Alert\b([^>]*)>/g)) expect(alert[1]).toMatch(/\bflat\b/);
		const personal = source('lib/components/account/PersonalProjectLabelSection.svelte');
		for (const alert of personal.matchAll(/<Alert\b([^>]*)>/g)) expect(alert[1]).toMatch(/\bflat\b/);
		expect(source('lib/components/dashboard/network/networks/FloatingIpCard.svelte')).toContain('motion-stagger divide-y divide-line');
	});

	it('preserves project section heading size while restoring the h1-h2-h3 outline', () => {
		for (const name of ['PersonalProjectLabelSection', 'ProjectsSection', 'ProjectSettingsSection']) {
			expect(source(`lib/components/account/${name}.svelte`)).toMatch(/<h2 class="text-sm font-semibold text-ink-0">/);
		}
		expect(source('lib/components/account/ProjectLifecycleSection.svelte')).toMatch(/<h3 class="text-sm font-semibold text-ink-0">/);
		const projects = source('lib/components/account/ProjectsSection.svelte');
		expect(projects).toContain('bg-surface-selected');
		expect(projects).not.toContain('bg-action-warm/');
	});

	it('keeps usage and activity annotations readable and tutorial elevation neutral in dark mode', () => {
		expect(source('routes/dashboard/usage/+page.svelte')).not.toContain('--color-ink-3');
		expect(source('routes/dashboard/activity/+page.svelte')).not.toContain('--color-ink-3');
		const banner = source('lib/components/mockup/MockupBanner.svelte');
		expect(banner).toContain('box-shadow: var(--shadow-restraint)');
		expect(banner).not.toContain('--glow-warm');
	});

	it('lets long cluster states and translated actions wrap inside narrow cards', () => {
		const cluster = source('lib/components/dashboard/drover/K3sClusterCard.svelte');
		expect(cluster).toContain('flex flex-wrap items-center gap-2.5');
		expect(cluster).toContain('flex-1 basis-24 min-w-0');
		expect(cluster).toContain('flex flex-wrap gap-1.5');
	});

	it('keeps administrator affirmative actions on readable warm fills', () => {
		for (const path of [
			'routes/admin/ports/+page.svelte',
			'routes/admin/routers/+page.svelte',
			'routes/admin/floating-ips/+page.svelte',
			'routes/admin/object-storage/+page.svelte',
			'lib/components/admin/ports/PortCreateModal.svelte',
			'lib/components/admin/groups/AdminGroupsPage.svelte',
			'lib/components/admin/groups/GroupCreateModal.svelte',
			'lib/components/admin/groups/GroupEditModal.svelte',
			'lib/components/admin/projects/AdminProjectsPage.svelte',
			'lib/components/admin/projects/AdminProjectCreateModal.svelte',
			'lib/components/admin/projects/AdminProjectEditModal.svelte',
		]) {
			const component = source(path);
			const warmClasses = [...component.matchAll(/class="([^"]*\bbg-action-warm\b[^"]*)"/g)]
				.filter(([, classes]) => /\btext-/.test(classes));
			expect(warmClasses.length, path).toBeGreaterThan(0);
			for (const [, classes] of warmClasses) {
				expect(classes.split(/\s+/), path).toContain('text-action-on-warm');
				expect(classes.split(/\s+/), path).not.toContain('text-ink-0');
			}
		}
		expect(source('routes/admin/object-storage/+page.svelte')).not.toMatch(/\b(?:bg|border)-indigo-/);
	});

	it('uses neutral selection for administrator port and project page sizes', () => {
		for (const path of [
			'routes/admin/ports/+page.svelte',
			'lib/components/admin/projects/AdminProjectsPage.svelte',
		]) {
			const component = source(path);
			expect(component, path).toContain("pageSize === n ? 'bg-surface-selected text-ink-0 shadow-[inset_0_0_0_1px_var(--color-line-2)]'");
			expect(component, path).toContain('aria-pressed={pageSize === n}');
		}
	});

	it('names the port dialog from its localized heading without replacing focus or submission', () => {
		const port = source('lib/components/admin/ports/PortCreateModal.svelte');
		expect(port).toContain('const id = $props.id();');
		expect(port).toContain('aria-labelledby="{id}-title"');
		expect(port).toMatch(/<h2 id="\{id\}-title"[^>]*>\{t\('portCreateModal\.title'\)\}<\/h2>/);
		expect(port).toContain('use:dialogFocus={{ enabled: true, onEscape: () => (open = false) }}');
		expect(port).toContain('onclick={handleCreate} disabled={creating || !form.network_id || (!!targetDomainId && !form.project_id)}');
	});

	it('keeps standalone administrator compact resource names at h2 without changing their type scale', () => {
		for (const path of [
			'lib/components/admin/ports/PortsTable.svelte',
			'lib/components/admin/routers/AdminRoutersTable.svelte',
			'routes/admin/floating-ips/+page.svelte',
		]) {
			const component = source(path);
			expect(component, path).toMatch(/<h2 class="break-all (?:font-mono )?font-medium text-ink-0">/);
			expect(component, path).not.toContain('<h3');
			expect(component, path).not.toContain('<h1');
		}
	});

	it('keeps auth branding tied to the app theme and functional utility text on the type ramp', () => {
		const auth = source('lib/components/auth/AuthStudioShell.svelte');
		expect(auth).toContain('style:color-scheme={$resolvedTheme}');
		expect(auth).toContain('font-size: var(--type-support)');
		expect(auth).toContain('font-size: var(--type-identifier)');
		expect(auth).not.toMatch(/\.auth-motion\s*\{[^}]*font-size:\s*0\.(?:5625|625|6875)rem/);
		const beta = source('lib/components/ui/BetaFeatureGate.svelte');
		expect(beta).toContain('color: var(--color-ink-1)');
		expect(beta).not.toContain('box-shadow');
		const artwork = source('lib/components/landing/LandingMotionGraphic.svelte');
		expect(artwork).toMatch(/\.tool\.hit\s*\{[^}]*background: var\(--color-surface-base\);[^}]*color: var\(--color-warm-text\);/);
	});

	it('keeps detail actions wrapping and credential records as divider rows', () => {
		expect(source('lib/components/ui/DetailHeader.svelte')).toContain('flex flex-wrap items-start');
		expect(source('lib/components/database/DbInstanceHeader.svelte')).toContain('flex min-w-0 max-w-full flex-wrap items-center');
		expect(source('lib/components/account/McpAccessSection.svelte')).toContain('.record { align-items: flex-start; padding: 0.75rem 0; border-bottom: 1px solid var(--color-line); }');
		const secrets = source('routes/dashboard/secrets/+page.svelte');
		expect(secrets).not.toContain('STATUS_CLASS');
		expect(secrets).toContain('<Pill tone={getStatusStyle(s.status).tone}');
		expect(secrets).not.toContain('<h3');
		expect(source('lib/components/TimeSeriesChart.svelte')).toContain('<h2 class="text-sm font-semibold text-ink-2">{title}</h2>');
		expect(source('lib/components/topology/canvas/CanvasOwnershipOverview.svelte')).toContain('<h2>{domain.label}</h2>');
	});

});
