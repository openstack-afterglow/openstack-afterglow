// jsdom implements neither Element.animate nor Element.getAnimations. Svelte's `animate:` directive reads
// getAnimations() before it measures a keyed row; with no animations running the correct answer is an empty list.
if (typeof Element !== 'undefined' && typeof Element.prototype.getAnimations !== 'function') {
	Element.prototype.getAnimations = () => [];
}
