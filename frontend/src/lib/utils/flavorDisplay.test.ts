import { describe, expect, it } from 'vitest';
import { consumerFlavorLabel, consumerInstanceFlavorLabel } from './flavorDisplay';
import { t } from '$lib/i18n/ns/compute-pools';

describe('consumer flavor specifications', () => {
	it('uses actual hardware instead of native names or display projections', () => {
		const flavor = { id: '6142dc21-753b-4b23-8382-c52dce4c630e', name: 'cpu.4c_12g', display_name: 'cpu.8c_16g', vcpus: 4, ram: 12288 };
		expect(consumerFlavorLabel(flavor)).toBe('4 vCPU · 12 GiB RAM');
		expect(flavor.id).toBe('6142dc21-753b-4b23-8382-c52dce4c630e');
	});
	it('uses approved primary GPU models and excludes companion aliases', () => {
		expect(consumerFlavorLabel({ name: 'gpu.native', vcpus: 4, ram: 12288,
			extra_specs: { 'afterglow:managed_by': 'domain-compute-v1', 'afterglow:access_mode': 'gpu_quota', 'pci_passthrough:alias': 'graphics:2,sound:2' },
			gpu_primary_aliases: [{ name: 'graphics', count: 2, resource_class: 'CUSTOM_PCI_RENDER', profile_name: 'RTX 6000' }],
		})).toBe('4 vCPU · 12 GiB RAM · RTX 6000 × 2');
	});
	it('keeps unverified GPU roles unknown rather than counting every PCI alias', () => {
		expect(consumerFlavorLabel({ name: 'gpu.native', vcpus: 4, ram: 12288,
			extra_specs: { 'afterglow:managed_by': 'domain-compute-v1', 'afterglow:access_mode': 'gpu_quota', 'pci_passthrough:alias': 'graphics:2,sound:2' },
			gpu_primary_aliases: null,
		})).toBe(`4 vCPU · 12 GiB RAM · GPU · ${t('unknown')}`);
	});
	it.each([undefined, { vcpus: 0, ram: 12288 }, { vcpus: 4, ram: NaN }])('does not fabricate missing or malformed hardware %s', flavor => {
		expect(consumerFlavorLabel(flavor)).toBe(t('unknown'));
	});
	it('formats only verified instance CPU projection, including fractional GiB', () => {
		expect(consumerInstanceFlavorLabel({ flavor_display_name: 'mem.4c_12g' })).toBe('4 vCPU · 12 GiB RAM');
		expect(consumerInstanceFlavorLabel({ flavor_display_name: 'cpu.2c_1.5g' })).toBe('2 vCPU · 1.5 GiB RAM');
		expect(consumerInstanceFlavorLabel({ flavor_display_name: null })).toBe(t('unknown'));
		expect(consumerInstanceFlavorLabel({ flavor_display_name: 'native.uuid' })).toBe(t('unknown'));
	});
	it.each(['m1.small', 'cpu.ag.4c.8g.legacy', 'gpu.renderx1_4c_16g'])('preserves historical native flavor %s without inferring hardware', flavor_name => {
		expect(consumerInstanceFlavorLabel({ flavor_name, flavor_display_name: null })).toBe(flavor_name);
		expect(consumerInstanceFlavorLabel({ flavor_name, flavor_display_name: 'unsupported' })).toBe(flavor_name);
	});
	it('prefers verified specifications and keeps genuinely missing flavor information unknown', () => {
		expect(consumerInstanceFlavorLabel({ flavor_name: 'm1.small', flavor_display_name: 'cpu.2c_1.5g' })).toBe('2 vCPU · 1.5 GiB RAM');
		for (const flavor_name of [undefined, null, '', '   ']) expect(consumerInstanceFlavorLabel({ flavor_name })).toBe(t('unknown'));
	});
});
