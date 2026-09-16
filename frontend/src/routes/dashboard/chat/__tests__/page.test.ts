import { describe, expect, it } from 'vitest';

import { load } from '../+page';

describe('/dashboard/chat route', () => {
	it('returns a valid workspace selection or null', () => {
		const workspaceData = load({
			url: new URL('http://localhost:3080/dashboard/chat?workspace=12')
		} as Parameters<typeof load>[0]);
		const ordinaryData = load({
			url: new URL('http://localhost:3080/dashboard/chat?mcp_oauth=connected')
		} as Parameters<typeof load>[0]);

		expect(workspaceData).toEqual({ workspaceId: 12 });
		expect(ordinaryData).toEqual({ workspaceId: null });
	});
});
