import { describe, expect, it } from 'vitest';
import { compileRegexSearch, matchesRegexSearch } from './regexSearch';

describe('regex search', () => {
	it('supports anchored alternation, Unicode and case-insensitive matching without mutable lastIndex', () => {
		const compiled = compileRegexSearch('^(web|한글)-\\d+$');
		expect(compiled.regex?.flags).toBe('iu');
		expect(matchesRegexSearch(compiled, 'WEB-12')).toBe(true);
		expect(matchesRegexSearch(compiled, 'WEB-12')).toBe(true);
		expect(matchesRegexSearch(compiled, '한글-2')).toBe(true);
		expect(matchesRegexSearch(compiled, 'xweb-12')).toBe(false);
	});

	it('does not trim meaningful whitespace or silently fall back to literal matching', () => {
		expect(matchesRegexSearch(compileRegexSearch(' '), 'web')).toBe(false);
		expect(matchesRegexSearch(compileRegexSearch(' '), 'web api')).toBe(true);
		expect(matchesRegexSearch(compileRegexSearch('a.b'), 'axb')).toBe(true);
		expect(matchesRegexSearch(compileRegexSearch('a\\.b'), 'axb')).toBe(false);
	});

	it('matches explicit fields independently without silently splitting arbitrary strings or enabling multiline', () => {
		const exact = compileRegexSearch('^host2$');
		expect(matchesRegexSearch(exact, ['resource-id', 'host2', 'active'])).toBe(true);
		expect(matchesRegexSearch(exact, 'resource-id\nhost2\nactive')).toBe(false);
		expect(matchesRegexSearch(exact, [])).toBe(false);
		expect(matchesRegexSearch(compileRegexSearch(''), [])).toBe(true);
		expect(matchesRegexSearch(compileRegexSearch('['), ['['])).toBe(false);
	});

	it('treats empty input as unrestricted and invalid syntax as matching nothing', () => {
		expect(compileRegexSearch('')).toEqual({ regex: null, error: false });
		expect(matchesRegexSearch(compileRegexSearch(''), '')).toBe(true);
		expect(compileRegexSearch('[')).toEqual({ regex: null, error: true });
		expect(matchesRegexSearch(compileRegexSearch('['), '[')).toBe(false);
		expect(matchesRegexSearch(compileRegexSearch('['), 'private resource')).toBe(false);
	});
});
