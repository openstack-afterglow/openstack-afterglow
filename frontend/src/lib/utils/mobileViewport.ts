import { MediaQuery } from 'svelte/reactivity';

/** One viewport owner for mobile-only (<768px, DESIGN.md) console presentation. */
export const mobileViewport = new MediaQuery('(max-width: 767.98px)', false);
