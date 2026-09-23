// @vitest-environment node
import { describe, expect, it } from 'vitest';
import {
	imageReferenceMatchScore,
	imageReferenceMatchesQuery,
	parseImageReference,
	sanitizeImageFilename,
} from './imageReference';

describe('image references', () => {
	it('defaults an omitted tag to latest', () => {
		expect(parseImageReference('ubuntu')).toEqual({ repository: 'ubuntu', tag: 'latest', name: 'ubuntu:latest' });
	});

	it('keeps version tags and registry ports distinct', () => {
		expect(parseImageReference('ubuntu:24.04')).toMatchObject({ repository: 'ubuntu', tag: '24.04' });
		expect(parseImageReference('registry.example:5000/ubuntu')).toMatchObject({
		 repository: 'registry.example:5000/ubuntu', tag: 'latest', name: 'registry.example:5000/ubuntu:latest',
		});
	});

	it('rejects extra tag separators and whitespace', () => {
		expect(() => parseImageReference('ubuntu:v1:v2')).toThrow();
		expect(() => parseImageReference('Ubuntu 24.04')).toThrow();
	});

	it('sanitizes common upload filenames into tagged references', () => {
		expect(sanitizeImageFilename('Ubuntu 24.04.qcow2')).toBe('ubuntu-24.04:latest');
	});

	it('searches repository and tag as separate Docker-style fields', () => {
		const image = { name: 'ubuntu:24.04', repository: 'ubuntu', tag: '24.04', os_distro: 'ubuntu' };
		expect(imageReferenceMatchesQuery(image, 'ubuntu 24.04')).toBe(true);
		expect(imageReferenceMatchesQuery(image, 'debian')).toBe(false);
		expect(imageReferenceMatchScore(image, 'ubuntu:24.04')).toBe(100);
	});
});
