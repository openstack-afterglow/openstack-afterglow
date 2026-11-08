import { MediaQuery } from 'svelte/reactivity';

/**
 * Tutorials target tablet and desktop only (Tailwind `md`, 768px, see DESIGN.md).
 * Mobile has no tutorial: its dense forms and full-screen panels leave no room for the popover.
 * The server fallback is true so SSR matches the desktop markup; hydration applies the real viewport.
 */
export const tutorialViewport = new MediaQuery('(min-width: 768px)', true);
