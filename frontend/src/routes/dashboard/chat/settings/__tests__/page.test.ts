import { describe, expect, it } from 'vitest';

import { load } from '../+page';

describe('/dashboard/chat/settings route', () => {
	it('keeps a valid section while ignoring OAuth metadata', () => {
		const data = load({
			url: new URL(
				'http://localhost:3080/dashboard/chat/settings?section=mcp&mcp_oauth=connected'
			)
		} as Parameters<typeof load>[0]);

		expect(data).toEqual({ section: 'mcp' });
	});

	it('falls back to usage for an unknown section', () => {
		const data = load({
			url: new URL('http://localhost:3080/dashboard/chat/settings?section=bogus')
		} as Parameters<typeof load>[0]);

		expect(data).toEqual({ section: 'usage' });
	});
});
