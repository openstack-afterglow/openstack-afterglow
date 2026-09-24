export const CLOUD_INIT_PRESETS = [
	{ id: 'system-update', label: '시스템 업데이트', content: '#cloud-config\npackage_update: true\npackage_upgrade: true\n' },
	{ id: 'developer-tools', label: '기본 개발 도구', content: '#cloud-config\npackages:\n  - git\n  - curl\n  - htop\n  - jq\n' },
	{ id: 'docker-runtime', label: 'Docker 런타임', content: '#cloud-config\npackages:\n  - docker.io\nruncmd:\n  - systemctl enable --now docker\n' },
] as const;
