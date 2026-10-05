export type ImageStudioStyleId = 'photo' | 'cinematic' | 'watercolor' | 'illustration' | 'three-dimensional' | 'pixel-art';

export interface ImageStudioStyle {
	id: ImageStudioStyleId;
	labelKey: `imageStudio.style.${'photo' | 'cinematic' | 'watercolor' | 'illustration' | 'threeDimensional' | 'pixelArt'}`;
	/** Locally hosted original thumbnail. */
	image: string;
	/** Korean text appended verbatim to the prompt, regardless of UI locale; no separate style flag. */
	instruction: string;
}

export const IMAGE_STUDIO_STYLES: readonly ImageStudioStyle[] = [
	{ id: 'photo', labelKey: 'imageStudio.style.photo', image: '/studio/styles/photo.webp', instruction: '사실적인 사진 스타일, 자연스러운 조명과 선명한 디테일' },
	{ id: 'cinematic', labelKey: 'imageStudio.style.cinematic', image: '/studio/styles/cinematic.webp', instruction: '영화 장면 같은 시네마틱 스타일, 극적인 조명과 깊이감 있는 구도' },
	{ id: 'watercolor', labelKey: 'imageStudio.style.watercolor', image: '/studio/styles/watercolor.webp', instruction: '부드러운 번짐과 종이 질감이 보이는 수채화 스타일' },
	{ id: 'illustration', labelKey: 'imageStudio.style.illustration', image: '/studio/styles/illustration.webp', instruction: '깔끔한 선과 단순한 색면의 일러스트 스타일' },
	{ id: 'three-dimensional', labelKey: 'imageStudio.style.threeDimensional', image: '/studio/styles/three-dimensional.webp', instruction: '부드러운 재질과 입체적인 음영의 3D 렌더링 스타일' },
	{ id: 'pixel-art', labelKey: 'imageStudio.style.pixelArt', image: '/studio/styles/pixel-art.webp', instruction: '제한된 색상 팔레트의 레트로 픽셀 아트 스타일' }
];

/** The user's draft followed by the provider-facing Korean style instruction, independent of UI locale. */
export function composeImagePrompt(draft: string, styleId: string | null | undefined): string {
	const text = draft.trim();
	const style = IMAGE_STUDIO_STYLES.find((candidate) => candidate.id === styleId);
	if (!text || !style) return text;
	return `${text}\n\n스타일: ${style.instruction}`;
}
