import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import ModelCapabilityBadges from '../ModelCapabilityBadges.svelte';

describe('ModelCapabilityBadges', () => {
	it('renders web search badge when web_search capability is true', () => {
		render(ModelCapabilityBadges, {
			caps: {
				vision: true,
				reasoning: false,
				tool_call: true,
				web_search: true
			}
		});

		expect(screen.getByText('Vision')).toBeTruthy();
		expect(screen.getByText('Tools')).toBeTruthy();
		expect(screen.getByText('Search')).toBeTruthy();
		expect(screen.getByTitle('웹 검색 지원')).toBeTruthy();
	});

	it('renders nothing when caps is empty or null', () => {
		const { container } = render(ModelCapabilityBadges, { caps: null });
		expect(container.querySelector('.badges')).toBeNull();
	});
});
