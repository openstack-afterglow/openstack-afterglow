export interface VisualDebtFinding {
	token: string;
	line: number;
	column: number;
}

export interface VisualDebtBaselineEntry {
	count: number;
	tokens: readonly string[];
}

export type VisualDebtBaseline = Record<string, VisualDebtBaselineEntry>;

export const RAW_VISUAL_TOKEN_PATTERN =
	/#[0-9A-Fa-f]{3,8}\b|\b(?:bg|text|border|stroke|fill)-(?:gray|slate|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}(?:\/\d{1,3})?\b|\b(?:bg|text|border|stroke|fill)-\[#[0-9A-Fa-f]{3,8}\]/g;

export const DESIGN_DEBT_EXCLUDED_PATHS = [
	'frontend/src/routes/layout.css',
	'frontend/src/lib/design/',
	// Pinned third-party source retains upstream defaults; Afterglow adapters remain checked.
	'frontend/src/lib/vendor/bklit-ui/',
	'__tests__/',
] as const;

export function isVisualDebtExcludedPath(path: string): boolean {
	const normalized = path.replaceAll('\\', '/');
	return DESIGN_DEBT_EXCLUDED_PATHS.some((entry) => normalized.includes(entry));
}

export function lineColumnAt(source: string, index: number): { line: number; column: number } {
	const before = source.slice(0, index);
	const lines = before.split('\n');
	return { line: lines.length, column: lines[lines.length - 1].length + 1 };
}

export function findVisualTokenDebt(source: string): VisualDebtFinding[] {
	const findings: VisualDebtFinding[] = [];
	RAW_VISUAL_TOKEN_PATTERN.lastIndex = 0;
	for (const match of source.matchAll(RAW_VISUAL_TOKEN_PATTERN)) {
		const index = match.index ?? 0;
		const { line, column } = lineColumnAt(source, index);
		findings.push({ token: match[0], line, column });
	}
	return findings;
}

export function summarizeVisualTokenDebt(findings: readonly VisualDebtFinding[]): VisualDebtBaselineEntry {
	return {
		count: findings.length,
		tokens: Array.from(new Set(findings.map((finding) => finding.token))).sort(),
	};
}

export function isWithinVisualDebtBaseline(
	findings: readonly VisualDebtFinding[],
	baseline: VisualDebtBaselineEntry | undefined,
): { ok: boolean; reason?: string } {
	if (findings.length === 0) return { ok: true };
	if (!baseline) return { ok: false, reason: 'file is not in legacy visual debt baseline' };
	const allowedTokens = new Set(baseline.tokens);
	const extraTokens = Array.from(new Set(findings.map((finding) => finding.token))).filter((token) => !allowedTokens.has(token));
	if (extraTokens.length > 0) return { ok: false, reason: `new raw visual tokens: ${extraTokens.join(', ')}` };
	if (findings.length > baseline.count) return { ok: false, reason: `raw visual token count increased from ${baseline.count} to ${findings.length}` };
	return { ok: true };
}
