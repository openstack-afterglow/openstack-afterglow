/**
 * Stroke icon path data (24×24 grid, drawn by `ProvisionPipeline`) for provisioning stages.
 * Shared by the VM deployment and Drover cluster progress pipelines.
 */
export const PROVISION_ICON = {
	sharedFolder: 'M3 7.5A1.5 1.5 0 0 1 4.5 6H9l2 2h8.5A1.5 1.5 0 0 1 21 9.5v8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5Z M8.5 13.5h7 M13.5 11.25l2.25 2.25-2.25 2.25',
	disk: 'M5 6c0-1.66 3.13-3 7-3s7 1.34 7 3-3.13 3-7 3-7-1.34-7-3Z M5 6v12c0 1.66 3.13 3 7 3s7-1.34 7-3V6 M5 12c0 1.66 3.13 3 7 3s7-1.34 7-3',
	layers: 'M12 3 3 7.5l9 4.5 9-4.5Z M3 12l9 4.5 9-4.5 M3 16.5 12 21l9-4.5',
	script: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z M14 3v5h5 M10 12.5 8.25 14.25 10 16 M14 12.5l1.75 1.75L14 16',
	server: 'M4 4h16v6H4Z M4 14h16v6H4Z M7.5 7h.01 M7.5 17h.01 M11 7h6 M11 17h6',
	servers: 'M3 4h7.5v7H3Z M13.5 4H21v7h-7.5Z M3 13h7.5v7H3Z M13.5 13H21v7h-7.5Z',
	link: 'M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1 M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1',
	globe: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z M3 12h18 M12 3c2.5 2.5 3.75 5.5 3.75 9S14.5 18.5 12 21 M12 3C9.5 5.5 8.25 8.5 8.25 12S9.5 18.5 12 21',
	shield: 'M12 3 5 6v5c0 4.5 3 8.25 7 10 4-1.75 7-5.5 7-10V6Z M9.25 12l2 2 3.5-3.75',
	terminal: 'M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z M7 10l3 2.5L7 15 M12.5 15H17',
	clipboard: 'M9 4h6v3H9Z M9 5.5H6.5A1.5 1.5 0 0 0 5 7v12.5A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V7a1.5 1.5 0 0 0-1.5-1.5H15 M8.5 12h7 M8.5 16h4.5',
	balancer: 'M12 3v6 M12 9 5.5 15 M12 9l6.5 6 M12 9v6 M4 15h3v3H4Z M10.5 15h3v3h-3Z M17 15h3v3h-3Z',
	key: 'M8 11a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z M10.85 12.15 20 3 M16.5 6.5 19 9 M14 9l2 2',
	nodes: 'M12 3 19.8 7.5v9L12 21l-7.8-4.5v-9Z M12 8.5 15 10.25v3.5L12 15.5l-3-1.75v-3.5Z',
	archive: 'M3 4h18v4H3Z M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8 M10 12h4',
	checkCircle: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z M8 12.5l2.75 2.75L16 9.75',
} as const;
