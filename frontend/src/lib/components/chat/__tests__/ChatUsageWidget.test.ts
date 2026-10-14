import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import type { ChatUsage } from '$lib/api/chatTree';
import ChatUsageWidget from '../ChatUsageWidget.svelte';

const usage: ChatUsage = {
	found: true, total_credited_cost: 12, lifetime_prompt_tokens: 80,
	lifetime_completion_tokens: 20, lifetime_request_count: 2,
	month_credited_cost: 12, week_credited_cost: 4, month_prompt_tokens: 80,
	month_completion_tokens: 20, month_request_count: 2,
	quota_used: 120, quota_max: 100, quota_weekly_max: 100,
};

afterEach(cleanup);

describe('chat quota usage display', () => {
	it('keeps over-limit usage in the visible readout', () => {
		const { container } = render(ChatUsageWidget, { props: { usage } });
		expect(container.textContent).toContain('120%');
	});


	it('does not imply a zero quota when no limit is configured', () => {
		const { container } = render(ChatUsageWidget, { props: { usage: { ...usage, quota_max: 0 } } });
		expect(container.textContent).not.toContain('0%');
	});
});
