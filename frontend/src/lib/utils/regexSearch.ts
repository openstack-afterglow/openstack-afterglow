export interface CompiledRegexSearch {
	regex: RegExp | null;
	error: boolean;
}

/** Empty input has no condition; malformed expressions never widen results. */
export function compileRegexSearch(query: string): CompiledRegexSearch {
	if (!query) return { regex: null, error: false };
	try {
		return { regex: new RegExp(query, 'iu'), error: false };
	} catch {
		return { regex: null, error: true };
	}
}

export function matchesRegexSearch(compiled: CompiledRegexSearch, value: string | readonly string[]): boolean {
	if (compiled.error) return false;
	const regex = compiled.regex;
	if (regex === null) return true;
	return typeof value === 'string' ? regex.test(value) : value.some((field) => regex.test(field));
}
