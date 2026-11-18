export const REALTIME_IMAGE_ACCEPT = 'image/png,image/jpeg,image/webp';
export const REALTIME_IMAGE_FRAME_BYTES = 2 * 1024 * 1024;
export const REALTIME_IMAGES_PER_SESSION = 8;
const MAX_IMAGE_BYTES = 1024 * 1024;
const MAX_SOURCE_BYTES = 20 * MAX_IMAGE_BYTES;
const MAX_IMAGE_EDGE = 2048;

function dataUrl(blob: Blob): Promise<string> {
	const { promise, resolve, reject } = Promise.withResolvers<string>();
	const reader = new FileReader();
	reader.onload = () => resolve(String(reader.result));
	reader.onerror = () => reject(reader.error);
	reader.readAsDataURL(blob);
	return promise;
}

/** Decode and re-encode locally. Lumen only accepts PNG/JPEG on the realtime wire. */
export async function encodeRealtimeImageFrame(file: File): Promise<string> {
	if (!REALTIME_IMAGE_ACCEPT.split(',').includes(file.type) || !file.size || file.size > MAX_SOURCE_BYTES) {
		throw new Error('Unsupported realtime image source');
	}
	const image = await createImageBitmap(file);
	const canvas = document.createElement('canvas');
	try {
		const context = canvas.getContext('2d');
		if (!context) throw new Error('Canvas unavailable');
		const type = file.type === 'image/jpeg' ? 'image/jpeg' : 'image/png';
		let scale = Math.min(1, MAX_IMAGE_EDGE / Math.max(image.width, image.height));
		for (let attempt = 0; attempt < 4; attempt++, scale /= 2) {
			canvas.width = Math.max(1, Math.floor(image.width * scale));
			canvas.height = Math.max(1, Math.floor(image.height * scale));
			context.drawImage(image, 0, 0, canvas.width, canvas.height);
			const { promise, resolve } = Promise.withResolvers<Blob | null>();
			canvas.toBlob(resolve, type, 0.86);
			const result = await promise;
			if (result && result.size > 0 && result.size <= MAX_IMAGE_BYTES && ['image/png', 'image/jpeg'].includes(result.type)) {
				const frame = JSON.stringify({ type: 'conversation.input_image', image_url: await dataUrl(result) });
				// The entire serialized frame is ASCII (including its base64 image).
				if (frame.length <= REALTIME_IMAGE_FRAME_BYTES) return frame;
			}
		}
		throw new Error('Realtime image exceeds wire limits');
	} finally {
		image.close();
		canvas.width = canvas.height = 0;
	}
}
