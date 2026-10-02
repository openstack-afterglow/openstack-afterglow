// @vitest-environment node
import { existsSync, readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const repoRoot = resolve(__dirname, '../../../../..');
const frontendRoot = resolve(repoRoot, 'frontend');
const layoutSource = readFileSync(resolve(frontendRoot, 'src/routes/layout.css'), 'utf8');

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

	});

});
