// @vitest-environment node
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { LOCALES as RUNTIME_LOCALES } from '../locales';
import { LOCALES, loadCatalogs, validateCatalogs } from '../../../../scripts/i18n-core.mjs';
import {
	FRONTEND_DIR,
	collectSourceFiles,
	findHardcodedText,
	loadAllowlist,
	scanHardcodedText,
} from '../../../../scripts/i18n-scan.mjs';

describe('translation catalogs', () => {
	it('tooling and runtime agree on the supported locales', () => {
		expect(LOCALES).toEqual([...RUNTIME_LOCALES]);
	});

	it('every namespace is complete, well-formed and placeholder-safe in all locales', async () => {
		const errors = validateCatalogs(await loadCatalogs()).filter((finding) => finding.level === 'error');
		expect(errors.map((finding) => `${finding.code} ${finding.locale ?? ''} ${finding.namespace ?? ''}:${finding.key ?? ''} ${finding.detail}`)).toEqual([]);
	});
});

describe('hard-coded text guard', () => {
	it('keeps visible Korean text out of frontend source', async () => {
		const findings = await scanHardcodedText(await collectSourceFiles(), await loadAllowlist());
		expect(findings.map((finding) => `${finding.file}:${finding.line}: ${finding.text}`)).toEqual([]);
	});

	it('only allowlists lines that still exist', async () => {
		const allowlist = await loadAllowlist();
		for (const [file, entry] of Object.entries(allowlist)) {
			const absolute = path.join(FRONTEND_DIR, file);
			expect(existsSync(absolute), file).toBe(true);
			expect(entry.reason.length, file).toBeGreaterThan(0);
			if (entry.lines === 'all') continue;
			const present = findHardcodedText(readFileSync(absolute, 'utf8'), absolute).map((hit) => hit.text);
			for (const line of entry.lines) expect(present, `${file}: ${line}`).toContain(line);
		}
	});
});
