import { describe, expect, it } from 'vitest';
import type { ImageInfo } from '$lib/types/compute';
import type { FlavorOption } from '$lib/types/flavor';
import { imageFlavorProfile, imageRecommendations } from './imageRecommendation';

const cpu: FlavorOption = { id: 'cpu', name: 'general', vcpus: 4, ram: 8192, disk: 40, is_public: true };
const gpu = (extra_specs: Record<string, string>): FlavorOption => ({ ...cpu, id: 'gpu', extra_specs });
const nvidia = gpu({ 'pci_passthrough:alias': 'RTX-3090:1,GA102-audio:1' });
const image: ImageInfo = {
	id: 'driver', name: 'ubuntu:latest', status: 'active', verification_status: 'verified',
	gpu_vendor: 'nvidia', gpu_driver: 'nvidia', created_at: '2026-01-01T00:00:00Z',
};

 describe('imageRecommendations', () => {
	it('recommends only explicit verified vendor and driver matches, not image or flavor names', () => {
		const candidates: ImageInfo[] = [
			image,
			{ ...image, id: 'wrong-vendor', name: 'amd:latest', gpu_vendor: 'amd', gpu_driver: 'amdgpu' },
			{ ...image, id: 'missing-driver', name: 'missing-driver:latest', gpu_driver: null },
			{ ...image, id: 'unverified', name: 'unverified:latest', verification_status: 'unverified' },
			{ ...image, id: 'unavailable', name: 'unavailable:latest', verification_status: 'unavailable' },
			{ ...image, id: 'name-only', name: 'nvidia-cuda-driver:latest', gpu_driver: null, gpu_vendor: null },
		];
		expect([...imageRecommendations(candidates, nvidia)]).toEqual([['driver', 'gpu']]);
		expect(imageRecommendations([image], { ...cpu, name: 'gpu.nvidia.large' }).has(image.id)).toBe(false);
		expect(imageRecommendations([image], gpu({ 'pci_passthrough:alias': 'gpu-unknown:1' })).size).toBe(0);
	});

	it.each([
		['AMD-Radeon:1', 'amd', 'amdgpu'],
		['Intel-Arc-A770:1', 'intel', 'i915'],
		['TITAN-X:2', 'nvidia', 'nvidia'],
	])('matches metadata for %s', (alias, gpu_vendor, gpu_driver) => {
		expect(imageRecommendations([{ ...image, gpu_vendor, gpu_driver }], gpu({ 'pci_passthrough:alias': alias })).get(image.id)).toBe('gpu');
	});

	it.each(['queued', 'saving', 'deactivated', 'killed', 'deleted'])('does not recommend %s images', status => {
		expect(imageRecommendations([{ ...image, status }], nvidia).size).toBe(0);
		expect(imageRecommendations([{ ...image, status, gpu_vendor: null, gpu_driver: null }], cpu).size).toBe(0);
	});

	it('does not revive an obsolete driver upload when the current UUID is inactive or lacks metadata', () => {
		const newer = { ...image, id: 'newer', created_at: '2026-02-01T00:00:00Z' };
		for (const replacement of [{ ...newer, status: 'saving' }, { ...newer, gpu_driver: null }]) {
			for (const candidates of [[image, replacement], [replacement, image]]) {
				expect(imageRecommendations(candidates, nvidia).size).toBe(0);
			}
		}
	});

	it('prefers CPU candidates without declared GPU software, including explicit none', () => {
		const candidates = [
			image,
			{ ...image, id: 'general', name: 'general:latest', gpu_vendor: null, gpu_driver: null },
			{ ...image, id: 'none', name: 'none:latest', gpu_vendor: '', gpu_driver: 'none' },
			{ ...image, id: 'unknown', name: 'unknown:latest', gpu_vendor: 'future-vendor', gpu_driver: 'future-driver' },
			{ ...image, id: 'vendor-only', name: 'vendor-only:latest', gpu_driver: null },
		];
		expect([...imageRecommendations(candidates, cpu)]).toEqual([['general', 'general'], ['none', 'general']]);
	});

	it('recognizes GPU resource requests but cannot borrow vendor identity from an independent PCI alias', () => {
		const unknown = gpu({ 'resources:VGPU': '1' });
		expect(imageFlavorProfile(unknown)).toEqual({ gpu: true, vendor: null, virtual: true });
		expect(imageRecommendations([image], unknown).size).toBe(0);
		const virtual = gpu({ 'resources1:VGPU': '1', 'pci_passthrough:alias': 'nvidia-gpu:1' });
		expect(imageFlavorProfile(virtual)).toEqual({ gpu: true, vendor: null, virtual: true });
		expect(imageRecommendations([image], virtual).size).toBe(0);
		expect(imageRecommendations([{ ...image, gpu_driver: 'nvidia-grid' }], virtual).size).toBe(0);
		expect(imageRecommendations([image], gpu({ 'resources:PGPU': '1', 'pci_passthrough:alias': 'RTX-3090:1' })).size).toBe(0);
		expect(imageFlavorProfile(gpu({ 'resources:PGPU': '1' }))?.gpu).toBe(true);
	});

	it('rejects unknown, conflicting and mismatched driver declarations', () => {
		for (const metadata of [
			{ gpu_vendor: 'nvidia', gpu_driver: 'future-driver' },
			{ gpu_vendor: 'nvidia', gpu_driver: 'amdgpu' },
			{ gpu_vendor: 'future-vendor', gpu_driver: 'nvidia' },
			{ gpu_vendor: null, gpu_driver: 'nvidia' },
		]) expect(imageRecommendations([{ ...image, ...metadata }], nvidia).size).toBe(0);
		const mixed = gpu({ 'pci_passthrough:alias': 'RTX-3090:1,AMD-Radeon:1' });
		expect(imageRecommendations([image], mixed).size).toBe(0);
	});

	it.each(['GA102-audio:1', 'Mellanox-ConnectX-6:1', 'intel-nic:1', 'nvidia-bluefield:1', 'RTX-3090:0', 'RTX-3090:-1', 'RTX-3090:bad'])('does not mistake %s for a GPU request', alias => {
		expect(imageFlavorProfile(gpu({ 'pci_passthrough:alias': alias }))?.gpu).toBe(false);
	});

	it('keeps image RAM requirements but does not cap independently sized Cinder boot volumes by flavor.disk', () => {
		expect(imageRecommendations([{ ...image, min_ram: 16384 }], nvidia).size).toBe(0);
		expect(imageRecommendations([{ ...image, min_disk: 80 }], nvidia).get(image.id)).toBe('gpu');
		expect(imageRecommendations([image], null).size).toBe(0);
	});
});
