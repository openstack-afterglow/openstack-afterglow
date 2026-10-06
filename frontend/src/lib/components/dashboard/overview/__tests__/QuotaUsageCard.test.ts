import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/svelte';
import QuotaUsageCard from '../QuotaUsageCard.svelte';

const quotas = {
	compute: {
		instances: { limit: 2, in_use: 1 },
		cores: { limit: 4, in_use: 1 },
		ram: { limit: 1024, in_use: 512 },
	},
	storage: { volumes: { limit: 2, in_use: 1 }, gigabytes: { limit: 20, in_use: 10 } },
	network: { floatingip: { limit: -1, in_use: 0 } },
	file_storage: null,
	alerts: [],
};

describe('QuotaUsageCard', () => {
	it('preserves the RAM usage ratio when converting MiB to GiB', () => {
		const { getByText } = render(QuotaUsageCard, { quotas, pending: false, error: null });
		const memory = getByText('Memory (GB)').parentElement;
		expect(memory?.textContent?.replace(/\s+/g, '')).toContain('0.5/1');
		expect(memory?.textContent).toContain('50%');
	});

	it('omits Manila rows when file storage is unavailable', () => {
		const { queryByText } = render(QuotaUsageCard, { quotas, pending: false, error: null });
		expect(queryByText('Manila Shares')).toBeNull();
	});
});
