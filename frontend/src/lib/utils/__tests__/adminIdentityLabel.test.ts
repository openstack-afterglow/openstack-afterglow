// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { abbreviatedIdentifier, adminIdentityLabel } from '../adminIdentityLabel';

describe('admin identity labels', () => {
	it('places a readable name before the abbreviated identifier', () => {
		expect(adminIdentityLabel('개발 프로젝트', '944405f937c3410f9b4f082b20a22e10')).toBe('개발 프로젝트 (944405f9)');
	});

	it('keeps a short identifier visible when no name is available', () => {
		expect(adminIdentityLabel(null, 'b9aef3e76c4b4405a91bc0365201fea3')).toBe('(b9aef3e7)');
		expect(abbreviatedIdentifier('short')).toBe('short');
	});
});
