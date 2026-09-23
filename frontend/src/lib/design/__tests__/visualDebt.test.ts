// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { LEGACY_VISUAL_DEBT } from '../legacyVisualDebt';
import {
	findVisualTokenDebt,
	isVisualDebtExcludedPath,
	isWithinVisualDebtBaseline,
	summarizeVisualTokenDebt,
	type VisualDebtBaseline,
} from '../visualDebt';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../../..');
const sourceRoot = path.join(repoRoot, 'frontend/src');
const baselinePath = path.join(repoRoot, 'frontend/src/lib/design/legacyVisualDebt.ts');
const scannedExtensions = new Set(['.svelte', '.ts', '.css']);

async function collectSourceFiles(dir: string): Promise<string[]> {
	const entries = await readdir(dir, { withFileTypes: true });
	const nested = await Promise.all(entries.map(async (entry) => {
		const fullPath = path.join(dir, entry.name);
		if (entry.isDirectory()) return collectSourceFiles(fullPath);
		if (!entry.isFile() || !scannedExtensions.has(path.extname(entry.name))) return [];
		return [fullPath];
	}));
	return nested.flat();
}

function repoRelative(filePath: string): string {
	return path.relative(repoRoot, filePath).replaceAll(path.sep, '/');
}

function formatBaseline(entries: VisualDebtBaseline): string {
	const lines = [
		"import type { VisualDebtBaseline } from './visualDebt';",
		'',
		'export const LEGACY_VISUAL_DEBT: VisualDebtBaseline = {',
	];
	for (const [filePath, entry] of Object.entries(entries).sort(([a], [b]) => a.localeCompare(b))) {
		lines.push(`\t${JSON.stringify(filePath)}: {`);
		lines.push(`\t\tcount: ${entry.count},`);
		lines.push(`\t\ttokens: ${JSON.stringify(entry.tokens)},`);
		lines.push('\t},');
	}
	lines.push('} as const;', '');
	return lines.join('\n');
}

describe('visual token debt scanner', () => {
	it('flags raw palette utilities while allowing non-color utilities', () => {
		expect(findVisualTokenDebt('<button class="bg-blue-600 text-white border-red-700">').map((finding) => finding.token)).toEqual([
			'bg-blue-600',
			'border-red-700',
		]);
	});

	it('allows design token CSS variable usage', () => {
		expect(findVisualTokenDebt('<div class="text-[var(--color-ink-0)]" style="background: var(--color-surface-raised)">')).toEqual([]);
	});

	it('keeps frontend source within the legacy visual debt baseline', async () => {
		const files = await collectSourceFiles(sourceRoot);
		const baseline: VisualDebtBaseline = {};
		const failures: string[] = [];

		for (const file of files) {
			const rel = repoRelative(file);
			if (isVisualDebtExcludedPath(rel)) continue;
			const source = await readFile(file, 'utf8');
			const findings = findVisualTokenDebt(source);
			if (process.env.UPDATE_VISUAL_DEBT_BASELINE === '1') {
				if (findings.length > 0) baseline[rel] = summarizeVisualTokenDebt(findings);
				continue;
			}

			const result = isWithinVisualDebtBaseline(findings, LEGACY_VISUAL_DEBT[rel]);
			if (!result.ok) {
				const locations = findings.map((finding) => `${finding.line}:${finding.column} ${finding.token}`).join(', ');
				failures.push(`${rel}: ${result.reason}; ${locations}. Define/extend a design token or UI primitive first; do not add raw color classes to new UI entities.`);
			}
		}

		if (process.env.UPDATE_VISUAL_DEBT_BASELINE === '1') {
			await mkdir(path.dirname(baselinePath), { recursive: true });
			await writeFile(baselinePath, formatBaseline(baseline));
			return;
		}

		expect(failures).toEqual([]);
	});

	it('keeps UI primitives free of raw visual token debt', async () => {
		const files = (await collectSourceFiles(path.join(sourceRoot, 'lib/components/ui')))
			.filter((file) => !repoRelative(file).includes('__tests__/'));
		const failures: string[] = [];

		for (const file of files) {
			const source = await readFile(file, 'utf8');
			const findings = findVisualTokenDebt(source);
			if (findings.length > 0) {
				const locations = findings.map((finding) => `${finding.line}:${finding.column} ${finding.token}`).join(', ');
				failures.push(`${repoRelative(file)}: ${locations}. Define/extend a design token or UI primitive first; do not add raw color classes to new UI entities.`);
			}
		}

		expect(failures).toEqual([]);
	});
});
