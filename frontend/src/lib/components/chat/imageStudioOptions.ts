import type { ImageSizeLimits } from '$lib/api/imageStudio';

export function imageDimensions(value: string): [number, number] | null {
	const match = /^([1-9]\d{0,3})x([1-9]\d{0,3})$/i.exec(value.trim());
	return match ? [Number(match[1]), Number(match[2])] : null;
}

export function validCustomImageSize(value: string, limits: ImageSizeLimits): boolean {
	const dimensions = imageDimensions(value);
	if (!dimensions) return false;
	const [width, height] = dimensions;
	const largest = Math.max(width, height);
	return width % limits.dimension_multiple === 0 && height % limits.dimension_multiple === 0 &&
		largest <= limits.max_edge && largest <= Math.min(width, height) * limits.max_aspect_ratio &&
		width * height >= limits.min_pixels && width * height <= limits.max_pixels;
}

export function imageInteger(value: string | number | null | undefined, min: number, max: number): number | undefined {
	if (value == null || (typeof value === 'string' && !/^\d+$/.test(value))) return undefined;
	const number = Number(value);
	return Number.isSafeInteger(number) && number >= min && number <= max ? number : undefined;
}

export function imageAssetExtension(mime: string): string | undefined {
	switch (mime) {
		case 'image/png': return 'png';
		case 'image/jpeg': return 'jpeg';
		case 'image/webp': return 'webp';
		case 'image/gif': return 'gif';
		case 'image/svg+xml': return 'svg';
	}
}

/** OpenAI guide's output-only estimate. Actual usage and billing come from Lumen. */
export function estimateImageOutputTokens(model: string, size: string, quality: string, count: number): number | null {
	const family = /^(?:openai\/)?gpt-image-(2(?:\.[56])?)(?:-|$)/.exec(model)?.[1];
	const dimensions = imageDimensions(size);
	const qualityIndex = ['low', 'medium', 'high', 'xhigh', 'max'].indexOf(quality);
	if (!family || !dimensions || qualityIndex < 0) return null;
	const grid = (family === '2' ? [16, 48, 96] : [16, 24, 48, 64, 96])[qualityIndex];
	if (grid === undefined) return null;
	const [width, height] = dimensions;
	const longer = Math.max(width, height);
	const numerator = grid * Math.min(width, height);
	const quotient = Math.floor(numerator / longer);
	const doubledRemainder = 2 * (numerator % longer);
	const rounded = quotient + Number(doubledRemainder > longer || (doubledRemainder === longer && quotient % 2 === 1));
	const base = Math.ceil(grid * rounded * (2_000_000 + width * height) / 4_000_000);
	return count * (family === '2.6' ? Math.floor((base * [42, 33, 10, 10, 10][qualityIndex] + 5) / 10) : base);
}
