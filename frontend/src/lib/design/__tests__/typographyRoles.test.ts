// @vitest-environment node
import { existsSync, readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const repoRoot = resolve(__dirname, '../../../../..');
const frontendRoot = resolve(repoRoot, 'frontend');
const layoutSource = readFileSync(resolve(frontendRoot, 'src/routes/layout.css'), 'utf8');
const tokenSource = readFileSync(resolve(frontendRoot, 'src/lib/design/tokens.ts'), 'utf8');
const landingSource = readFileSync(resolve(frontendRoot, 'src/lib/components/landing/LandingPage.svelte'), 'utf8');
const opsBoardSource = readFileSync(resolve(frontendRoot, 'src/lib/components/landing/LandingOpsBoard.svelte'), 'utf8');
const designSource = readFileSync(resolve(repoRoot, 'DESIGN.md'), 'utf8');

const fontFiles = [
	'pretendard/PretendardVariable.woff2',
	'ibm-plex/IBMPlexSansKR-Medium.woff2',
	'ibm-plex/IBMPlexSansKR-SemiBold.woff2',
	'ibm-plex/IBMPlexMono-Regular.woff2',
	'ibm-plex/IBMPlexMono-Medium.woff2',
];

function lightThemeHex(token: string): string {
	const lightTheme = layoutSource.match(/:root\.light\s*\{([\s\S]*?)\n\}/)?.[1];
	const escapedToken = token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
	const value = lightTheme?.match(new RegExp(`${escapedToken}:\\s*(#[0-9a-fA-F]{6})`))?.[1];
	if (!value) throw new Error(`Missing light theme token: ${token}`);
	return value;
}

function relativeLuminance(hex: string): number {
	const channels = [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255);
	const [red, green, blue] = channels.map((channel) =>
		channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
	);
	return 0.2126 * red! + 0.7152 * green! + 0.0722 * blue!;
}

function contrastRatio(foreground: string, background: string): number {
	const foregroundLuminance = relativeLuminance(foreground);
	const backgroundLuminance = relativeLuminance(background);
	const lighter = Math.max(foregroundLuminance, backgroundLuminance);
	const darker = Math.min(foregroundLuminance, backgroundLuminance);
	return (lighter + 0.05) / (darker + 0.05);
}

describe('role-based typography system', () => {
	it('bundles the selected open-licensed WOFF2 files within the intended payload', () => {
		const fontRoot = resolve(frontendRoot, 'static/fonts');
		const totalBytes = fontFiles.reduce((total, file) => {
			const path = resolve(fontRoot, file);
			expect(existsSync(path)).toBe(true);
			return total + statSync(path).size;
		}, 0);

		expect(totalBytes).toBeLessThan(3_500_000);
		expect(existsSync(resolve(fontRoot, 'pretendard/LICENSE.txt'))).toBe(true);
		expect(existsSync(resolve(fontRoot, 'ibm-plex/LICENSE.txt'))).toBe(true);
	});

	it('defines sans, display, and mono roles in the authoritative CSS and TypeScript tokens', () => {
		expect(layoutSource).toContain('font-family: "Pretendard Variable"');
		expect(layoutSource).toContain('font-family: "IBM Plex Sans KR"');
		expect(layoutSource).toContain('font-family: "IBM Plex Mono"');
		expect(layoutSource).toContain('--font-display: "IBM Plex Sans KR"');
		expect(layoutSource).toContain('--font-mono: "IBM Plex Mono", "Pretendard Variable"');
		expect(layoutSource.match(/font-display: swap;/g)).toHaveLength(5);
		expect(layoutSource).not.toContain('MaruBuri');
		expect(layoutSource).not.toMatch(/https?:\/\//);
		expect(tokenSource).toContain('export const FONT_CSS_VAR');
		expect(tokenSource).toContain("display: 'var(--font-display)'");
	});

	it('keeps display typography on editorial headings and documents the same role boundary', () => {
		expect(landingSource).toContain('.hero h1, .section h2, .cap-content h3, blockquote, .audience-note strong { font-family: var(--font-display); }');
		expect(landingSource).toContain('font-family: var(--font-sans);');
		expect(designSource).toContain('Typography has three explicit roles');
		expect(designSource).toContain('do not use it for ordinary console page titles or controls');
	});

	it('keeps small landing labels AA-safe without changing the dark palette', () => {
		const lightSurface = lightThemeHex('--color-surface-base');
		for (const token of [
			'--color-ink-1',
			'--color-ink-2',
			'--color-warm-text',
			'--color-state-success-text',
		]) {
			expect(contrastRatio(lightThemeHex(token), lightSurface), token).toBeGreaterThanOrEqual(4.5);
		}

		expect(layoutSource).toContain('--color-warm-text: var(--color-warm);');
		expect(layoutSource).toContain('--color-state-success-text: var(--color-state-success);');
		expect(tokenSource).toContain('export const TEXT_CSS_VAR');
		expect(tokenSource).toContain("warm: 'var(--color-warm-text)'");
		expect(tokenSource).toContain("success: 'var(--color-state-success-text)'");
		expect(landingSource).not.toContain('color: var(--color-ink-3);');
		expect(landingSource).not.toContain('color: var(--color-state-success);');
		expect(landingSource.match(/color: var\(--color-warm\);/g)).toHaveLength(1);
		expect(landingSource).toContain('color: var(--color-warm-text);');
		expect(landingSource).toContain('color: var(--color-state-success-text);');
		expect(opsBoardSource).not.toContain('color: var(--color-ink-3);');
		expect(opsBoardSource).not.toContain('color: var(--color-state-success);');
		expect(opsBoardSource).not.toContain('color: var(--color-warm);');
		expect(opsBoardSource).toContain('color: var(--color-warm-text);');
		expect(opsBoardSource).toContain('color: var(--color-state-success-text);');
		expect(designSource).toContain('Normal-sized public/editorial labels use `--color-ink-2`, `--color-warm-text`, or `--color-state-success-text`');
	});

	it('delays the dense one-row operations board until the xl width can preserve values', () => {
		expect(opsBoardSource).toContain('@media (min-width: 1024px)');
		expect(opsBoardSource).toContain('@media (min-width: 1280px)');
		expect(designSource).toContain('The board retains its readable two-row desktop flow until the `xl` density refinement (`≥1280px`)');
	});
});
