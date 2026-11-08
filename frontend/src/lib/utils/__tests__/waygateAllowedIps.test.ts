import { describe, expect, it } from 'vitest';
import { t } from '$lib/i18n/ns/waygate';
import { parseWaygateAllowedIps, WAYGATE_ALLOWED_IPS_MAX } from '../waygateAllowedIps';

describe('parseWaygateAllowedIps', () => {
	it('treats blank input as an empty routing list', () => {
		expect(parseWaygateAllowedIps(' \n , ')).toEqual({ ok: true, value: [] });
	});

	it('normalizes host bits like Waygate strict=False and de-duplicates in first order', () => {
		expect(parseWaygateAllowedIps('10.20.0.5/24, 192.168.1.0/24\n10.20.0.0/24 172.16.0.1/32', '10.240.0.0/24')).toEqual({
			ok: true,
			value: ['10.20.0.0/24', '192.168.1.0/24', '172.16.0.1/32'],
		});
	});

	it.each([
		['fd00::1/64', 'fd00::/64'],
		['2001:DB8:0:0:1::5/128', '2001:db8::1:0:0:5/128'],
		['2001:db8:0:1:0:0:0:0/64', '2001:db8:0:1::/64'],
		['::ffff:192.0.2.1/128', '::ffff:c000:201/128'],
		['2001:db8:1:0:1:1:1:1/127', '2001:db8:1:0:1:1:1:0/127'],
	])('formats IPv6 %s canonically as %s', (input, expected) => {
		expect(parseWaygateAllowedIps(input)).toEqual({ ok: true, value: [expected] });
	});

	it.each(['10.0.0.0', '10.0.0.256/24', '10.0.0.0/33', 'fd00::/129', 'fd00:::1/64', '1:2:3:4:5:6:7:8:9/64', 'host.example/24', '10.0.0.0/24/1'])(
		'rejects invalid CIDR %s',
		(value) => {
			expect(parseWaygateAllowedIps(value)).toEqual({ ok: false, error: t('validation.allowedIps.invalid', { value }) });
		}
	);

	it.each(['0.0.0.0/0', '1.2.3.4/0', '::/0'])('rejects default route %s', (value) => {
		expect(parseWaygateAllowedIps(value)).toEqual({ ok: false, error: t('validation.allowedIps.defaultRoute', { value }) });
	});

	it.each(['10.240.0.0/16', '10.240.0.7/32'])('rejects %s overlapping the tunnel subnet', (value) => {
		expect(parseWaygateAllowedIps(value, '10.240.0.0/24')).toEqual({
			ok: false,
			error: t('validation.allowedIps.tunnelOverlap', { value, tunnel: '10.240.0.0/24' }),
		});
	});

	it('does not compare IPv6 routes against an IPv4 tunnel', () => {
		expect(parseWaygateAllowedIps('fd00::/8', '10.240.0.0/24')).toEqual({ ok: true, value: ['fd00::/8'] });
	});

	it('limits the canonical list to the Waygate maximum', () => {
		const entries = Array.from({ length: WAYGATE_ALLOWED_IPS_MAX + 1 }, (_, index) => `10.${index}.0.0/16`);
		expect(parseWaygateAllowedIps(entries.join('\n'))).toEqual({
			ok: false,
			error: t('validation.allowedIps.tooMany', { max: WAYGATE_ALLOWED_IPS_MAX }),
		});
		expect(parseWaygateAllowedIps([...entries.slice(0, WAYGATE_ALLOWED_IPS_MAX), entries[0]].join(','))).toMatchObject({ ok: true });
	});
});
