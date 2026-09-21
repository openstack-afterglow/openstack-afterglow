export const load = ({ setHeaders }: { setHeaders: (headers: Record<string, string>) => void }) => {
	setHeaders({
		'cache-control': 'no-store',
		'referrer-policy': 'no-referrer',
	});
};
