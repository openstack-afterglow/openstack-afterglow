// @vitest-environment node
import { describe, expect, it } from 'vitest';
import type { Flavor } from '$lib/types/flavor';
import {
	buildGpuFilterOptions,
	matchesGpuFilter,
	normalizeGpuAlias,
	parseGpuAliasSpecs,
} from '../flavorGpuFilters';

function flavor(overrides: Partial<Flavor>): Flavor {
	return {
		id: 'flavor-id',
		name: 'flavor-name',
		vcpus: 1,
		ram: 1024,
		disk: 10,
		is_public: true,
		description: null,
		extra_specs: {},
		is_gpu: false,
		gpu_count: 0,
		...overrides,
	};
}

const titanFlavor = flavor({
	id: 'titan',
	name: 'titan.gpu',
	is_gpu: true,
	gpu_count: 2,
	extra_specs: { 'pci_passthrough:alias': 'TITAN-X:2,GP102-audio:2' },
});

const rtxFlavor = flavor({
	id: 'rtx',
	name: 'rtx.gpu',
	is_gpu: true,
	gpu_count: 1,
	extra_specs: { 'pci_passthrough:alias': 'RTX-3090:1' },
});

const cpuFlavor = flavor({
	id: 'cpu',
	name: 'cpu.only',
});

describe('normalizeGpuAlias', () => {
	it('normalizes spaces, underscores, hyphens, dots, and case to the same key', () => {
		const normalized = ['RTX 3090', 'RTX_3090', 'RTX-3090', 'RTX.3090', 'rtx 3090'].map(
			normalizeGpuAlias,
		);

		expect(new Set(normalized)).toEqual(new Set(['rtx3090']));
	});
});

describe('parseGpuAliasSpecs', () => {
	it('extracts GPU aliases from Nova extra specs while ignoring audio aliases and malformed entries', () => {
		expect(
			parseGpuAliasSpecs({
				'pci_passthrough:alias': ' TITAN-X:2, GP102-audio:2, RTX-3090:1, no-count ',
			}),
		).toEqual(['TITAN-X', 'RTX-3090']);
	});

	it('returns no aliases when the flavor has no pci passthrough alias spec', () => {
		expect(parseGpuAliasSpecs({})).toEqual([]);
		expect(parseGpuAliasSpecs(undefined)).toEqual([]);
	});
});

describe('buildGpuFilterOptions', () => {
	it('keeps the three reserved options first and adds sorted, non-audio GPU aliases', () => {
		expect(buildGpuFilterOptions([titanFlavor, rtxFlavor, cpuFlavor])).toEqual([
			{ value: '', label: 'GPU 전체' },
			{ value: '__gpu__', label: 'GPU 있음' },
			{ value: '__non_gpu__', label: 'GPU 없음' },
			{ value: 'RTX-3090', label: 'RTX-3090' },
			{ value: 'TITAN-X', label: 'TITAN-X' },
		]);
	});

	it('deduplicates aliases by their normalized spelling without listing audio aliases', () => {
		const dottedRtxFlavor = flavor({
			id: 'rtx-dotted',
			name: 'rtx.dotted',
			is_gpu: true,
			gpu_count: 1,
			extra_specs: { 'pci_passthrough:alias': 'RTX.3090:1,RTX_3090-audio:1' },
		});

		expect(buildGpuFilterOptions([rtxFlavor, dottedRtxFlavor])).toEqual([
			{ value: '', label: 'GPU 전체' },
			{ value: '__gpu__', label: 'GPU 있음' },
			{ value: '__non_gpu__', label: 'GPU 없음' },
			{ value: 'RTX-3090', label: 'RTX-3090' },
		]);
	});
});

describe('matchesGpuFilter', () => {
	it('matches a specific GPU alias only against flavors whose extra specs contain that alias', () => {
		expect(matchesGpuFilter(titanFlavor, 'TITAN-X')).toBe(true);
		expect(matchesGpuFilter(rtxFlavor, 'TITAN-X')).toBe(false);
		expect(matchesGpuFilter(cpuFlavor, 'TITAN-X')).toBe(false);
	});

	it('uses normalized alias matching for specific GPU filters', () => {
		expect(matchesGpuFilter(rtxFlavor, 'RTX 3090')).toBe(true);
		expect(matchesGpuFilter(rtxFlavor, 'rtx_3090')).toBe(true);
		expect(matchesGpuFilter(rtxFlavor, 'RTX.3090')).toBe(true);
	});

	it('matches reserved GPU and non-GPU filter values from observable flavor state', () => {
		expect([titanFlavor, rtxFlavor, cpuFlavor].map((item) => matchesGpuFilter(item, '__gpu__'))).toEqual([
			true,
			true,
			false,
		]);
		expect([titanFlavor, rtxFlavor, cpuFlavor].map((item) => matchesGpuFilter(item, '__non_gpu__'))).toEqual([
			false,
			false,
			true,
		]);
		expect([titanFlavor, rtxFlavor, cpuFlavor].map((item) => matchesGpuFilter(item, ''))).toEqual([
			true,
			true,
			true,
		]);
	});
});


describe('approved managed GPU aliases', () => {
	const managed = flavor({
		id: 'managed',
		is_gpu: true,
		gpu_count: 1,
		extra_specs: {
			'afterglow:managed_by': 'domain-compute-v1',
			'pci_passthrough:alias': 'graphics:1,sound:1',
		},
		gpu_primary_aliases: [{ name: 'graphics', count: 1, resource_class: 'CUSTOM_GRAPHICS', profile_name: 'render-group' }],
	});

	it('lists and matches only approved primary aliases, never arbitrary companions', () => {
		expect(buildGpuFilterOptions([managed]).slice(3)).toEqual([{ value: 'graphics', label: 'graphics' }]);
		expect(matchesGpuFilter(managed, 'graphics')).toBe(true);
		expect(matchesGpuFilter(managed, 'sound')).toBe(false);
		expect(matchesGpuFilter(managed, 'render-group')).toBe(false);
	});

	it('preserves exact managed native names even when legacy normalization would merge them', () => {
		const another = flavor({
			...managed,
			id: 'another',
			gpu_primary_aliases: [{ name: 'GRAPH_ICS', count: 1, resource_class: 'CUSTOM_OTHER', profile_name: 'another' }],
		});
		expect(new Set(buildGpuFilterOptions([managed, another]).slice(3).map(option => option.value))).toEqual(new Set(['GRAPH_ICS', 'graphics']));
		expect(matchesGpuFilter(managed, 'GRAPH_ICS')).toBe(false);
		expect(matchesGpuFilter(another, 'graphics')).toBe(false);
	});

	it.each([null, undefined])('does not infer aliases or non-GPU state from unknown managed mapping %s', evidence => {
		const unknown = flavor({ ...managed, is_gpu: null, gpu_count: null, gpu_primary_aliases: evidence });
		expect(buildGpuFilterOptions([unknown]).slice(3)).toEqual([]);
		expect(matchesGpuFilter(unknown, 'graphics')).toBe(false);
		expect(matchesGpuFilter(unknown, 'sound')).toBe(false);
		expect(matchesGpuFilter(unknown, '__gpu__')).toBe(false);
		expect(matchesGpuFilter(unknown, '__non_gpu__')).toBe(false);
		expect(matchesGpuFilter(unknown, '')).toBe(true);
	});

	it('keeps verified CPU flavors in non-GPU filters without adding alias options', () => {
		const cpu = flavor({ ...managed, is_gpu: false, gpu_count: 0, gpu_primary_aliases: [] });
		expect(matchesGpuFilter(cpu, '__non_gpu__')).toBe(true);
		expect(buildGpuFilterOptions([cpu]).slice(3)).toEqual([]);
	});
});
