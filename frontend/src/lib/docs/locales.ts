import { isDocsPath } from './paths';

export const docsLocales = [
	{ id: 'ko', name: '한국어' },
	{ id: 'en', name: 'English' },
	{ id: 'ja', name: '日本語' },
	{ id: 'zh-CN', name: '简体中文' },
] as const;

export type DocsLocale = typeof docsLocales[number]['id'];

export function docsLocaleFromUrl(url: URL): DocsLocale {
	const requested = url.searchParams.get('lang');
	return docsLocales.find(({ id }) => id === requested)?.id ?? 'ko';
}

/** Language changes retain the article, section and any existing reader context. */
export function docsLanguageHref(url: URL, locale: DocsLocale): string {
	const next = new URL(url);
	if (locale === 'ko') next.searchParams.delete('lang');
	else next.searchParams.set('lang', locale);
	return `${next.pathname}${next.search}${next.hash}`;
}

/** Ordinary guide links retain language/tutorial, but not a different article's fragment. */
export function docsHref(slug: string | undefined, locale: DocsLocale, url: URL): string {
	const params = new URLSearchParams();
	if (locale !== 'ko') params.set('lang', locale);
	const tutorial = url.searchParams.get('tutorial');
	if (tutorial === 'on' || tutorial === 'admin') params.set('tutorial', tutorial);
	const query = params.toString();
	return `/docs${slug ? `/${slug}` : ''}${query ? `?${query}` : ''}`;
}

export function docsContentHref(href: string, locale: DocsLocale, url: URL): string {
	if (!href.startsWith('/docs')) return href;
	const target = new URL(href, url);
	if (!isDocsPath(target.pathname)) return href;
	const tutorial = url.searchParams.get('tutorial');
	if (tutorial === 'on' || tutorial === 'admin') target.searchParams.set('tutorial', tutorial);
	return docsLanguageHref(target, locale);
}

const ko = {
	userDocs: '사용자 문서', serviceDocs: '서비스 문서', docsHome: '문서 홈 · 검색',
	skip: '본문으로 건너뛰기', home: '메인 페이지', homeTitle: '메인 페이지로 이동', backHome: '메인 페이지로 돌아가기',
	navigation: '문서 탐색', menu: '문서 메뉴', publicNote: ['문서는 로그인 없이 읽을 수 있습니다.', '실제 작업은 프로젝트 권한이 필요합니다.'],
	consoleAccess: '콘솔 접속', consoleReturn: '콘솔로 돌아가기', language: '언어 선택',
	themeSystem: '시스템 테마', themeDark: '다크 모드', themeLight: '라이트 모드', themeChange: '테마 변경',
	guideTitle: '사용 가이드', indexDescription: 'Nova, Neutron, Octavia, Cinder, Manila부터 Drover, Waygate, Lumen, Palimpsest까지. 프로젝트 준비와 서비스별 사용 절차를 안내합니다.',
	heroTitle: ['필요한 환경을,', '직접 준비하는 방법.'], heroCopy: ['가상 머신 한 대부터 클러스터와 팀 데이터까지.', '서비스를 고르고, 준비하고, 결과를 확인하세요.'],
	getStarted: '처음 시작하기', searchLabel: '문서 검색', searchHelp: '서비스 이름이나 작업을 입력하세요. 예: Floating IP, 백업, kubeconfig', searchPlaceholder: '서비스나 작업 검색…',
	guideCount: (count: number) => `사용 가이드 ${count}개`, resultsCount: (count: number) => `검색 결과 ${count}개`,
	noResultsTitle: '일치하는 문서가 없습니다', noResultsDescription: '서비스 이름 또는 더 짧은 작업 이름으로 검색해 보세요.', resetSearch: '검색 초기화',
	availability: '문서는 현재 콘솔의 사용 방법을 설명합니다. 서비스 활성화, 가용 자원, 모델과 프로젝트 권한은 운영 환경에 따라 다릅니다.',
	prerequisites: '시작 전 확인', consoleUsage: '콘솔에서 사용하기', consoleNote: '로그인하고 작업할 프로젝트를 선택하세요. 조회·변경은 현재 프로젝트의 권한과 서비스 설정을 따릅니다.',
	serviceUnavailable: '이 환경에서 서비스가 비활성화되어 있습니다.', related: '함께 읽기', official: '공식 참고 자료', toc: '이 문서의 목차', inThisArticle: '이 문서에서', breadcrumbs: '문서 경로',
	copy: '복사', copyLabel: (label: string) => `${label} 복사`, copySuccess: '명령을 복사했습니다.', copyFailure: '복사하지 못했습니다. 아래 명령을 선택해 직접 복사하세요.',
	notFound: '문서를 찾을 수 없습니다', failed: '문서를 열지 못했습니다', errorRecovery: '주소를 확인하거나 문서 홈에서 서비스 이름으로 검색하세요.', goHome: '문서 홈으로 이동',
	categories: [
		{ id: 'start', label: '시작하기', description: '계정과 프로젝트를 준비하고 첫 자원을 만듭니다.' },
		{ id: 'openstack', label: 'OpenStack', description: '컴퓨팅, 네트워크, 저장소와 기본 클라우드 서비스를 사용합니다.' },
		{ id: 'afterglow', label: 'Afterglow 서비스', description: '클러스터, VPN, AI와 재사용 가능한 연구 환경을 다룹니다.' },
	],
};

export const docsMessages: Record<DocsLocale, typeof ko> = {
	ko,
	en: {
		userDocs: 'User documentation', serviceDocs: 'Service documentation', docsHome: 'Docs home · Search',
		skip: 'Skip to content', home: 'Home', homeTitle: 'Go to the home page', backHome: 'Back to home',
		navigation: 'Documentation navigation', menu: 'Documentation menu', publicNote: ['Read documentation without signing in.', 'Real operations require project permissions.'],
		consoleAccess: 'Open console', consoleReturn: 'Back to console', language: 'Choose language',
		themeSystem: 'System theme', themeDark: 'Dark mode', themeLight: 'Light mode', themeChange: 'Change theme',
		guideTitle: 'Usage guide', indexDescription: 'From Nova, Neutron, Octavia, Cinder and Manila to Drover, Waygate, Lumen and Palimpsest. Prepare your project and follow practical service workflows.',
		heroTitle: ['The environment you need.', 'How to build it yourself.'], heroCopy: ['From one virtual machine to clusters and shared team data.', 'Choose a service, prepare it and verify the result.'],
		getStarted: 'Get started', searchLabel: 'Search documentation', searchHelp: 'Enter a service or task. For example: Floating IP, backup, kubeconfig', searchPlaceholder: 'Search services or tasks…',
		guideCount: (count: number) => `${count} usage guides`, resultsCount: (count: number) => `${count} search results`,
		noResultsTitle: 'No matching documentation', noResultsDescription: 'Try a service name or a shorter task name.', resetSearch: 'Reset search',
		availability: 'These guides describe the current console. Enabled services, available resources, models and project permissions depend on your deployment.',
		prerequisites: 'Before you start', consoleUsage: 'Use in the console', consoleNote: 'Sign in and select the project you will work in. Reads and changes follow that project’s permissions and service configuration.',
		serviceUnavailable: 'This service is disabled in this environment.', related: 'Related guides', official: 'Official references', toc: 'Article contents', inThisArticle: 'In this article', breadcrumbs: 'Documentation breadcrumb',
		copy: 'Copy', copyLabel: (label: string) => `Copy ${label}`, copySuccess: 'Command copied.', copyFailure: 'Could not copy. Select the command below and copy it manually.',
		notFound: 'Documentation not found', failed: 'Could not open documentation', errorRecovery: 'Check the address or search for the service on the docs home page.', goHome: 'Go to docs home',
		categories: [
			{ id: 'start', label: 'Getting started', description: 'Prepare your account and project, then create your first resource.' },
			{ id: 'openstack', label: 'OpenStack', description: 'Use compute, networking, storage and core cloud services.' },
			{ id: 'afterglow', label: 'Afterglow services', description: 'Work with clusters, VPN, AI and reusable research environments.' },
		],
	},
	ja: {
		userDocs: 'ユーザードキュメント', serviceDocs: 'サービスドキュメント', docsHome: 'ドキュメント一覧・検索',
		skip: '本文へスキップ', home: 'ホーム', homeTitle: 'ホームページへ移動', backHome: 'ホームに戻る',
		navigation: 'ドキュメントのナビゲーション', menu: 'ドキュメントメニュー', publicNote: ['ログインせずにドキュメントを読めます。', '実際の操作にはプロジェクトの権限が必要です。'],
		consoleAccess: 'コンソールを開く', consoleReturn: 'コンソールに戻る', language: '言語を選択',
		themeSystem: 'システムのテーマ', themeDark: 'ダークモード', themeLight: 'ライトモード', themeChange: 'テーマを変更',
		guideTitle: '利用ガイド', indexDescription: 'Nova、Neutron、Octavia、Cinder、ManilaからDrover、Waygate、Lumen、Palimpsestまで。プロジェクトの準備とサービスごとの利用手順を紹介します。',
		heroTitle: ['必要な環境を、', '自分で準備する方法。'], heroCopy: ['1台の仮想マシンからクラスター、チームの共有データまで。', 'サービスを選び、準備し、結果を確認しましょう。'],
		getStarted: 'はじめに', searchLabel: 'ドキュメントを検索', searchHelp: 'サービス名や操作を入力します。例：Floating IP、バックアップ、kubeconfig', searchPlaceholder: 'サービスや操作を検索…',
		guideCount: (count: number) => `利用ガイド ${count}件`, resultsCount: (count: number) => `検索結果 ${count}件`,
		noResultsTitle: '一致するドキュメントがありません', noResultsDescription: 'サービス名や、より短い操作名で検索してください。', resetSearch: '検索をリセット',
		availability: 'ドキュメントは現在のコンソールの使い方を説明します。サービスの有効化、利用可能なリソース、モデル、プロジェクトの権限は運用環境によって異なります。',
		prerequisites: '始める前に', consoleUsage: 'コンソールで利用する', consoleNote: 'ログインし、作業するプロジェクトを選択してください。参照・変更には、そのプロジェクトの権限とサービス設定が適用されます。',
		serviceUnavailable: 'この環境ではサービスが無効になっています。', related: '関連ガイド', official: '公式リファレンス', toc: 'この記事の目次', inThisArticle: 'この記事について', breadcrumbs: 'ドキュメントの階層',
		copy: 'コピー', copyLabel: (label: string) => `${label}をコピー`, copySuccess: 'コマンドをコピーしました。', copyFailure: 'コピーできませんでした。下のコマンドを選択して手動でコピーしてください。',
		notFound: 'ドキュメントが見つかりません', failed: 'ドキュメントを開けませんでした', errorRecovery: 'アドレスを確認するか、ドキュメント一覧でサービス名を検索してください。', goHome: 'ドキュメント一覧へ',
		categories: [
			{ id: 'start', label: 'はじめに', description: 'アカウントとプロジェクトを準備し、最初のリソースを作成します。' },
			{ id: 'openstack', label: 'OpenStack', description: 'コンピューティング、ネットワーク、ストレージと基本的なクラウドサービスを利用します。' },
			{ id: 'afterglow', label: 'Afterglowサービス', description: 'クラスター、VPN、AI、再利用できる研究環境を扱います。' },
		],
	},
	'zh-CN': {
		userDocs: '用户文档', serviceDocs: '服务文档', docsHome: '文档首页 · 搜索',
		skip: '跳转到正文', home: '主页', homeTitle: '前往主页', backHome: '返回主页',
		navigation: '文档导航', menu: '文档菜单', publicNote: ['无需登录即可阅读文档。', '实际操作需要项目权限。'],
		consoleAccess: '打开控制台', consoleReturn: '返回控制台', language: '选择语言',
		themeSystem: '系统主题', themeDark: '深色模式', themeLight: '浅色模式', themeChange: '切换主题',
		guideTitle: '使用指南', indexDescription: '从Nova、Neutron、Octavia、Cinder、Manila到Drover、Waygate、Lumen、Palimpsest，介绍项目准备和各项服务的实际使用流程。',
		heroTitle: ['所需的环境，', '亲手准备的方法。'], heroCopy: ['从一台虚拟机到集群与团队共享数据。', '选择服务、完成准备，并验证结果。'],
		getStarted: '开始使用', searchLabel: '搜索文档', searchHelp: '输入服务名称或操作。例如：Floating IP、备份、kubeconfig', searchPlaceholder: '搜索服务或操作…',
		guideCount: (count: number) => `${count}篇使用指南`, resultsCount: (count: number) => `${count}条搜索结果`,
		noResultsTitle: '没有匹配的文档', noResultsDescription: '请尝试服务名称或更简短的操作名称。', resetSearch: '重置搜索',
		availability: '文档介绍当前控制台的使用方法。启用的服务、可用资源、模型和项目权限取决于部署环境。',
		prerequisites: '开始前确认', consoleUsage: '在控制台中使用', consoleNote: '登录并选择要操作的项目。查询与修改遵循当前项目的权限和服务配置。',
		serviceUnavailable: '此环境中未启用该服务。', related: '相关指南', official: '官方参考资料', toc: '本文目录', inThisArticle: '本文内容', breadcrumbs: '文档路径',
		copy: '复制', copyLabel: (label: string) => `复制${label}`, copySuccess: '已复制命令。', copyFailure: '无法复制。请选择下方命令并手动复制。',
		notFound: '找不到文档', failed: '无法打开文档', errorRecovery: '请检查地址，或在文档首页按服务名称搜索。', goHome: '前往文档首页',
		categories: [
			{ id: 'start', label: '开始使用', description: '准备账户和项目，然后创建第一个资源。' },
			{ id: 'openstack', label: 'OpenStack', description: '使用计算、网络、存储和基础云服务。' },
			{ id: 'afterglow', label: 'Afterglow服务', description: '使用集群、VPN、AI及可复用的研究环境。' },
		],
	},
};
