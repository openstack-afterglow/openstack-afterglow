import type { ExperienceMessageMetadata } from '$lib/i18n/experienceMessages';
import { experienceMessage, experienceState, recordExperience, type ExperienceContext } from './experience';

export interface ExperiencePresentation {
	context?: ExperienceContext;
	message?: ExperienceMessageMetadata;
	state?: 'loading' | 'ready' | 'empty' | 'error' | 'disabled';
	step?: number;
}

/** Opt-in source metadata only. Never reads text, inputs, attributes, labels or resource identities. */
export function experiencePresentation(node: HTMLElement, initial: ExperiencePresentation) {
	let options = initial;
	let observer: IntersectionObserver | undefined;
	let intersecting = false;
	let visible = false;
	let lastMessage: ExperienceMessageMetadata | undefined;
	let lastState: ExperiencePresentation['state'];
	let lastStep: number | undefined;
	let activeContext: ExperienceContext | undefined;

	function report() {
		const nextContext = options.context && options.message ? options.context : undefined;
		if (activeContext !== nextContext) {
			if (visible && activeContext) recordExperience(activeContext, 'view.exposure_changed', { visibility: 'hidden' });
			activeContext = nextContext;
			visible = false;
			lastMessage = undefined;
			lastState = undefined;
			lastStep = undefined;
		}
		if (!activeContext) return;
		const nextVisible = intersecting && document.visibilityState === 'visible';
		if (visible !== nextVisible) {
			visible = nextVisible;
			recordExperience(activeContext, 'view.exposure_changed', { visibility: visible ? 'visible' : 'hidden' });
		}
		if (!visible) return;
		if (!lastMessage || options.message!.key !== lastMessage.key ||
			options.message!.locale !== lastMessage.locale ||
			options.message!.catalog_revision !== lastMessage.catalog_revision ||
			options.message!.tone !== lastMessage.tone ||
			options.message!.restoration !== lastMessage.restoration) {
			experienceMessage(activeContext, options.message!);
			lastMessage = options.message;
		}
		if (options.state && (options.state !== lastState || options.step !== lastStep)) {
			experienceState(activeContext, options.state, options.step);
			lastState = options.state;
			lastStep = options.step;
		}
	}

	function sync() {
		if (options.context && options.message && typeof IntersectionObserver !== 'undefined') {
			if (!observer) {
				observer = new IntersectionObserver((entries) => {
					intersecting = entries.some((entry) => entry.target === node && entry.isIntersecting && entry.intersectionRatio > 0);
					report();
				});
				observer.observe(node);
				document.addEventListener('visibilitychange', report);
			}
		} else {
			observer?.disconnect();
			observer = undefined;
			intersecting = false;
			document.removeEventListener('visibilitychange', report);
		}
		report();
	}

	sync();
	return {
		update(next: ExperiencePresentation) { options = next; sync(); },
		destroy() {
			observer?.disconnect();
			document.removeEventListener('visibilitychange', report);
			if (visible && activeContext) recordExperience(activeContext, 'view.exposure_changed', { visibility: 'hidden' });
		},
	};
}
