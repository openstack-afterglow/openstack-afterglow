import { prefersReducedMotion } from '$lib/utils/motion';

/**
 * Same-document View Transitions between the public landing and the login studio.
 *
 * The landing hero and the AuthStudioShell identity side render the same AfterglowOrbit scene.
 * During a scene they share `view-transition-name: afterglow-art` (layout.css), so the browser morphs the
 * full-screen hero into the identity side while the auth panel arrives from the inline end. Names exist only
 * while `html[data-route-scene]` is set, so ordinary rendering never carries view-transition names.
 */
export type RouteScene = 'auth-enter' | 'auth-leave';

export const ROUTE_SCENE_ATTRIBUTE = 'routeScene';
/** `detached`: the source artwork is off screen, so only the panel/page choreography runs. */
export const ROUTE_SCENE_ART_ATTRIBUTE = 'routeSceneArt';
export const ROUTE_SCENE_PART_SELECTOR = '[data-route-scene-part="art"]';

export function classifyRouteScene(from: string | null | undefined, to: string | null | undefined): RouteScene | null {
	if (!from || !to || from === to) return null;
	if (from === '/' && to === '/login') return 'auth-enter';
	if (from === '/login' && to === '/') return 'auth-leave';
	return null;
}

interface ViewTransitionLike {
	ready: Promise<void>;
	finished: Promise<void>;
	updateCallbackDone: Promise<void>;
}

type StartViewTransition = (update: () => Promise<void>) => ViewTransitionLike;

function startViewTransitionOf(doc: Document): StartViewTransition | null {
	const start = (doc as Document & { startViewTransition?: StartViewTransition }).startViewTransition;
	return typeof start === 'function' ? start.bind(doc) : null;
}

export function canRunRouteScene(doc: Document | undefined = typeof document === 'undefined' ? undefined : document): boolean {
	return !!doc && startViewTransitionOf(doc) !== null && !prefersReducedMotion();
}

/** The art morph only reads as continuity when the hero is actually on screen. */
function artInView(doc: Document): boolean {
	const art = doc.querySelector<HTMLElement>(ROUTE_SCENE_PART_SELECTOR);
	if (!art) return false;
	const box = art.getBoundingClientRect();
	const height = doc.defaultView?.innerHeight ?? 0;
	return box.height > 0 && box.bottom > height * 0.35 && box.top < height * 0.65;
}

export interface RouteSceneNavigation {
	from: { url: URL } | null;
	to: { url: URL } | null;
	willUnload: boolean;
	complete: Promise<void>;
}

/**
 * `onNavigate` adapter: returns a promise that SvelteKit awaits before it applies the new route (the
 * transition's update callback), or `undefined` when no scene applies and navigation proceeds normally.
 */
export function runRouteScene(navigation: RouteSceneNavigation, doc: Document | undefined = typeof document === 'undefined' ? undefined : document): Promise<void> | undefined {
	if (!doc || navigation.willUnload) return undefined;
	const scene = classifyRouteScene(navigation.from?.url.pathname, navigation.to?.url.pathname);
	const start = startViewTransitionOf(doc);
	if (!scene || !start || prefersReducedMotion()) return undefined;
	const root = doc.documentElement;
	root.dataset[ROUTE_SCENE_ATTRIBUTE] = scene;
	if (scene === 'auth-enter' && !artInView(doc)) root.dataset[ROUTE_SCENE_ART_ATTRIBUTE] = 'detached';
	else delete root.dataset[ROUTE_SCENE_ART_ATTRIBUTE];
	const clear = () => {
		if (root.dataset[ROUTE_SCENE_ATTRIBUTE] !== scene) return;
		delete root.dataset[ROUTE_SCENE_ATTRIBUTE];
		delete root.dataset[ROUTE_SCENE_ART_ATTRIBUTE];
	};
	return new Promise<void>((resolve) => {
		let transition: ViewTransitionLike;
		try {
			transition = start(async () => {
				resolve();
				// A cancelled navigation rejects `complete`; the transition then skips to the current DOM.
				await navigation.complete;
			});
		} catch {
			clear();
			resolve();
			return;
		}
		// A skipped transition rejects these; the navigation itself is unaffected.
		transition.ready.catch(() => {});
		transition.updateCallbackDone.catch(() => {});
		transition.finished.catch(() => {}).finally(clear);
	});
}
