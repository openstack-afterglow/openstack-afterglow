const EVENT = 'afterglow:chat-models-changed';

/** Signal only: credentials and model data never cross tabs or enter storage. */
export function invalidateChatModels(): void {
	if (typeof window === 'undefined') return;
	window.dispatchEvent(new Event(EVENT));
	if (typeof BroadcastChannel !== 'undefined') {
		const channel = new BroadcastChannel(EVENT);
		channel.postMessage(null);
		channel.close();
	}
}

export function onChatModelsInvalidated(refresh: () => void): () => void {
	window.addEventListener(EVENT, refresh);
	const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(EVENT) : null;
	if (channel) channel.onmessage = refresh;
	return () => {
		window.removeEventListener(EVENT, refresh);
		channel?.close();
	};
}
