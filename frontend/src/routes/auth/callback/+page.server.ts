// One-use onboarding/authorization material must not be cached or leaked by referrer.
export const load = ({ setHeaders }: { setHeaders: (headers: Record<string, string>) => void }) => {
	setHeaders({
		'cache-control': 'no-store',
		'referrer-policy': 'no-referrer',
	});
};
