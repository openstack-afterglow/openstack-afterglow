import type { Locale } from '$lib/i18n/locales';
import { DEFAULT_LOCALE, LOCALES, LOCALE_NATIVE_NAMES, isLocale } from '$lib/i18n/locales';
import { isDocsPath } from './paths';

export const docsLocales = LOCALES.map((id) => ({ id, name: LOCALE_NATIVE_NAMES[id] }));

export type DocsLocale = Locale;

/** Explicit documentation links select a language; ordinary visits use the shared preference. */
export function docsLocaleFromUrl(url: URL, preference: DocsLocale = DEFAULT_LOCALE): DocsLocale {
	const requested = url.searchParams.get('lang');
	return isLocale(requested) ? requested : preference;
}

/** Language changes retain the article, section and any existing reader context. */
export function docsLanguageHref(url: URL, locale: DocsLocale): string {
	const next = new URL(url);
	next.searchParams.set('lang', locale);
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
	screenshotOpen: '원본 이미지 열기 (새 탭)', screenshotOpenLabel: (alt: string) => `${alt} — 원본 이미지 열기 (새 탭)`, screenshotKoreanNote: '실제 한국어 콘솔 화면이며 개인정보·자원 식별자는 가렸습니다.',
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
		screenshotOpen: 'Open original image (new tab)', screenshotOpenLabel: (alt: string) => `${alt} — Open original image (new tab)`, screenshotKoreanNote: 'Actual Korean-language console screens; personal information and resource identifiers are hidden.',
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
		screenshotOpen: '元の画像を開く（新しいタブ）', screenshotOpenLabel: (alt: string) => `${alt} — 元の画像を開く（新しいタブ）`, screenshotKoreanNote: '実際の韓国語コンソール画面です。個人情報とリソース識別子は非表示にしています。',
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
		screenshotOpen: '打开原始图片（新标签页）', screenshotOpenLabel: (alt: string) => `${alt} — 打开原始图片（新标签页）`, screenshotKoreanNote: '这是实际的韩语控制台界面，个人信息和资源标识符已隐藏。',
		notFound: '找不到文档', failed: '无法打开文档', errorRecovery: '请检查地址，或在文档首页按服务名称搜索。', goHome: '前往文档首页',
		categories: [
			{ id: 'start', label: '开始使用', description: '准备账户和项目，然后创建第一个资源。' },
			{ id: 'openstack', label: 'OpenStack', description: '使用计算、网络、存储和基础云服务。' },
			{ id: 'afterglow', label: 'Afterglow服务', description: '使用集群、VPN、AI及可复用的研究环境。' },
		],
	},
	sw: {
		userDocs: 'Nyaraka za mtumiaji', serviceDocs: 'Nyaraka za huduma', docsHome: 'Ukurasa mkuu wa nyaraka · Tafuta',
		skip: 'Ruka hadi kwenye maudhui', home: 'Mwanzo', homeTitle: 'Nenda kwenye ukurasa mkuu', backHome: 'Rudi mwanzo',
		navigation: 'Urambazaji wa nyaraka', menu: 'Menyu ya nyaraka', publicNote: ['Soma nyaraka bila kuingia kwenye akaunti.', 'Shughuli halisi zinahitaji ruhusa za mradi.'],
		consoleAccess: 'Fungua konsoli', consoleReturn: 'Rudi kwenye konsoli', language: 'Chagua lugha',
		themeSystem: 'Mandhari ya mfumo', themeDark: 'Hali ya giza', themeLight: 'Hali ya mwanga', themeChange: 'Badilisha mandhari',
		guideTitle: 'Mwongozo wa matumizi', indexDescription: 'Kuanzia Nova, Neutron, Octavia, Cinder na Manila hadi Drover, Waygate, Lumen na Palimpsest. Andaa mradi wako na ufuate taratibu za matumizi ya kila huduma.',
		heroTitle: ['Mazingira unayohitaji.', 'Jinsi ya kuyaandaa mwenyewe.'], heroCopy: ['Kuanzia mashine pepe moja hadi makundi ya mashine na data ya pamoja ya timu.', 'Chagua huduma, iandae na uhakikishe matokeo.'],
		getStarted: 'Anza kutumia', searchLabel: 'Tafuta nyaraka', searchHelp: 'Andika huduma au kazi. Kwa mfano: Floating IP, nakala rudufu, kubeconfig', searchPlaceholder: 'Tafuta huduma au kazi…',
		guideCount: (count: number) => `Miongozo ${count} ya matumizi`, resultsCount: (count: number) => `Matokeo ${count} ya utafutaji`,
		noResultsTitle: 'Hakuna nyaraka zinazolingana', noResultsDescription: 'Jaribu jina la huduma au jina fupi zaidi la kazi.', resetSearch: 'Weka upya utafutaji',
		availability: 'Miongozo hii inaeleza konsoli ya sasa. Huduma zilizowezeshwa, rasilimali zinazopatikana, modeli na ruhusa za mradi hutegemea mazingira ya uwekaji.',
		prerequisites: 'Kabla ya kuanza', consoleUsage: 'Tumia katika konsoli', consoleNote: 'Ingia na uchague mradi utakaofanyia kazi. Utazamaji na mabadiliko hufuata ruhusa na usanidi wa huduma wa mradi huo.',
		serviceUnavailable: 'Huduma hii imezimwa katika mazingira haya.', related: 'Miongozo inayohusiana', official: 'Marejeo rasmi', toc: 'Yaliyomo katika makala', inThisArticle: 'Katika makala hii', breadcrumbs: 'Njia ya urambazaji wa nyaraka',
		copy: 'Nakili', copyLabel: (label: string) => `Nakili ${label}`, copySuccess: 'Amri imenakiliwa.', copyFailure: 'Imeshindikana kunakili. Chagua amri iliyo hapa chini na uinakili mwenyewe.',
		screenshotOpen: 'Fungua picha asili (kichupo kipya)', screenshotOpenLabel: (alt: string) => `${alt} — Fungua picha asili (kichupo kipya)`, screenshotKoreanNote: 'Picha halisi za skrini za konsoli ya lugha ya Kikorea; taarifa binafsi na vitambulishi vya rasilimali vimefichwa.',
		notFound: 'Nyaraka hazikupatikana', failed: 'Imeshindikana kufungua nyaraka', errorRecovery: 'Hakiki anwani au tafuta jina la huduma katika ukurasa mkuu wa nyaraka.', goHome: 'Nenda kwenye ukurasa mkuu wa nyaraka',
		categories: [
			{ id: 'start', label: 'Kuanza', description: 'Andaa akaunti na mradi wako, kisha unda rasilimali yako ya kwanza.' },
			{ id: 'openstack', label: 'OpenStack', description: 'Tumia huduma za ukokotoaji, mitandao, hifadhi na huduma za msingi za wingu.' },
			{ id: 'afterglow', label: 'Huduma za Afterglow', description: 'Fanya kazi na makundi ya mashine, VPN, AI na mazingira ya utafiti yanayoweza kutumika tena.' },
		],
	},
	nb: {
		userDocs: 'Brukerdokumentasjon', serviceDocs: 'Tjenestedokumentasjon', docsHome: 'Dokumentasjon · Søk',
		skip: 'Hopp til innhold', home: 'Hjem', homeTitle: 'Gå til hjemmesiden', backHome: 'Tilbake til hjemmesiden',
		navigation: 'Dokumentasjonsnavigasjon', menu: 'Dokumentasjonsmeny', publicNote: ['Les dokumentasjonen uten å logge inn.', 'Faktiske operasjoner krever prosjekttillatelser.'],
		consoleAccess: 'Åpne konsollen', consoleReturn: 'Tilbake til konsollen', language: 'Velg språk',
		themeSystem: 'Systemtema', themeDark: 'Mørk modus', themeLight: 'Lys modus', themeChange: 'Bytt tema',
		guideTitle: 'Brukerveiledning', indexDescription: 'Fra Nova, Neutron, Octavia, Cinder og Manila til Drover, Waygate, Lumen og Palimpsest. Klargjør prosjektet og følg praktiske arbeidsflyter for hver tjeneste.',
		heroTitle: ['Miljøet du trenger.', 'Slik bygger du det selv.'], heroCopy: ['Fra én virtuell maskin til klynger og delte teamdata.', 'Velg en tjeneste, klargjør den og kontroller resultatet.'],
		getStarted: 'Kom i gang', searchLabel: 'Søk i dokumentasjonen', searchHelp: 'Skriv inn en tjeneste eller oppgave. For eksempel: flytende IP, sikkerhetskopi, kubeconfig', searchPlaceholder: 'Søk etter tjenester eller oppgaver…',
		guideCount: (count: number) => `${count} brukerveiledninger`, resultsCount: (count: number) => `${count} søkeresultater`,
		noResultsTitle: 'Ingen dokumentasjon samsvarer med søket', noResultsDescription: 'Prøv et tjenestenavn eller et kortere oppgavenavn.', resetSearch: 'Nullstill søket',
		availability: 'Disse veiledningene beskriver den gjeldende konsollen. Aktiverte tjenester, tilgjengelige ressurser, modeller og prosjekttillatelser avhenger av driftsmiljøet.',
		prerequisites: 'Før du begynner', consoleUsage: 'Bruk i konsollen', consoleNote: 'Logg inn og velg prosjektet du skal arbeide i. Lesing og endringer følger prosjektets tillatelser og tjenestekonfigurasjon.',
		serviceUnavailable: 'Denne tjenesten er deaktivert i dette miljøet.', related: 'Relaterte veiledninger', official: 'Offisielle referanser', toc: 'Innhold i artikkelen', inThisArticle: 'I denne artikkelen', breadcrumbs: 'Dokumentasjonssti',
		copy: 'Kopier', copyLabel: (label: string) => `Kopier ${label}`, copySuccess: 'Kommandoen er kopiert.', copyFailure: 'Kunne ikke kopiere. Merk kommandoen nedenfor og kopier den manuelt.',
		screenshotOpen: 'Åpne originalbildet (ny fane)', screenshotOpenLabel: (alt: string) => `${alt} — Åpne originalbildet (ny fane)`, screenshotKoreanNote: 'Faktiske skjermbilder fra den koreanskspråklige konsollen. Personopplysninger og ressursidentifikatorer er skjult.',
		notFound: 'Fant ikke dokumentasjonen', failed: 'Kunne ikke åpne dokumentasjonen', errorRecovery: 'Kontroller adressen eller søk etter tjenesten på dokumentasjonens startside.', goHome: 'Gå til dokumentasjonens startside',
		categories: [
			{ id: 'start', label: 'Kom i gang', description: 'Klargjør kontoen og prosjektet, og opprett deretter din første ressurs.' },
			{ id: 'openstack', label: 'OpenStack', description: 'Bruk databehandling, nettverk, lagring og grunnleggende skytjenester.' },
			{ id: 'afterglow', label: 'Afterglow-tjenester', description: 'Arbeid med klynger, VPN, KI og gjenbrukbare forskningsmiljøer.' },
		],
	},
	ms: {
		userDocs: 'Dokumentasi pengguna', serviceDocs: 'Dokumentasi perkhidmatan', docsHome: 'Halaman utama dokumentasi · Carian',
		skip: 'Langkau ke kandungan', home: 'Halaman utama', homeTitle: 'Pergi ke halaman utama', backHome: 'Kembali ke halaman utama',
		navigation: 'Navigasi dokumentasi', menu: 'Menu dokumentasi', publicNote: ['Baca dokumentasi tanpa log masuk.', 'Operasi sebenar memerlukan kebenaran projek.'],
		consoleAccess: 'Buka konsol', consoleReturn: 'Kembali ke konsol', language: 'Pilih bahasa',
		themeSystem: 'Tema sistem', themeDark: 'Mod gelap', themeLight: 'Mod cerah', themeChange: 'Tukar tema',
		guideTitle: 'Panduan penggunaan', indexDescription: 'Daripada Nova, Neutron, Octavia, Cinder dan Manila hingga Drover, Waygate, Lumen dan Palimpsest. Sediakan projek anda dan ikuti aliran kerja perkhidmatan yang praktikal.',
		heroTitle: ['Persekitaran yang anda perlukan.', 'Cara membinanya sendiri.'], heroCopy: ['Daripada sebuah mesin maya hingga kluster dan data pasukan yang dikongsi.', 'Pilih perkhidmatan, sediakannya dan sahkan hasilnya.'],
		getStarted: 'Bermula', searchLabel: 'Cari dokumentasi', searchHelp: 'Masukkan perkhidmatan atau tugas. Contohnya: IP terapung, sandaran, kubeconfig', searchPlaceholder: 'Cari perkhidmatan atau tugas…',
		guideCount: (count: number) => `${count} panduan penggunaan`, resultsCount: (count: number) => `${count} hasil carian`,
		noResultsTitle: 'Tiada dokumentasi yang sepadan', noResultsDescription: 'Cuba nama perkhidmatan atau nama tugas yang lebih ringkas.', resetSearch: 'Tetapkan semula carian',
		availability: 'Panduan ini menerangkan konsol semasa. Perkhidmatan yang diaktifkan, sumber yang tersedia, model dan kebenaran projek bergantung pada pemasangan anda.',
		prerequisites: 'Sebelum anda bermula', consoleUsage: 'Gunakan dalam konsol', consoleNote: 'Log masuk dan pilih projek yang akan anda gunakan. Pembacaan dan perubahan tertakluk pada kebenaran serta konfigurasi perkhidmatan projek tersebut.',
		serviceUnavailable: 'Perkhidmatan ini dinyahaktifkan dalam persekitaran ini.', related: 'Panduan berkaitan', official: 'Rujukan rasmi', toc: 'Kandungan artikel', inThisArticle: 'Dalam artikel ini', breadcrumbs: 'Jejak navigasi dokumentasi',
		copy: 'Salin', copyLabel: (label: string) => `Salin ${label}`, copySuccess: 'Arahan telah disalin.', copyFailure: 'Tidak dapat menyalin. Pilih arahan di bawah dan salin secara manual.',
		screenshotOpen: 'Buka imej asal (tab baharu)', screenshotOpenLabel: (alt: string) => `${alt} — Buka imej asal (tab baharu)`, screenshotKoreanNote: 'Skrin konsol sebenar dalam bahasa Korea; maklumat peribadi dan pengecam sumber disembunyikan.',
		notFound: 'Dokumentasi tidak ditemukan', failed: 'Tidak dapat membuka dokumentasi', errorRecovery: 'Semak alamat atau cari perkhidmatan pada halaman utama dokumentasi.', goHome: 'Pergi ke halaman utama dokumentasi',
		categories: [
			{ id: 'start', label: 'Bermula', description: 'Sediakan akaun dan projek anda, kemudian cipta sumber pertama anda.' },
			{ id: 'openstack', label: 'OpenStack', description: 'Gunakan pengkomputeran, rangkaian, storan dan perkhidmatan awan teras.' },
			{ id: 'afterglow', label: 'Perkhidmatan Afterglow', description: 'Urus kluster, VPN, AI dan persekitaran penyelidikan boleh guna semula.' },
		],
	},
	vi: {
		userDocs: 'Tài liệu người dùng', serviceDocs: 'Tài liệu dịch vụ', docsHome: 'Trang tài liệu · Tìm kiếm',
		skip: 'Chuyển đến nội dung', home: 'Trang chủ', homeTitle: 'Đi đến trang chủ', backHome: 'Quay lại trang chủ',
		navigation: 'Điều hướng tài liệu', menu: 'Menu tài liệu', publicNote: ['Đọc tài liệu mà không cần đăng nhập.', 'Các thao tác thực tế yêu cầu quyền trong dự án.'],
		consoleAccess: 'Mở bảng điều khiển', consoleReturn: 'Quay lại bảng điều khiển', language: 'Chọn ngôn ngữ',
		themeSystem: 'Giao diện hệ thống', themeDark: 'Chế độ tối', themeLight: 'Chế độ sáng', themeChange: 'Đổi giao diện',
		guideTitle: 'Hướng dẫn sử dụng', indexDescription: 'Từ Nova, Neutron, Octavia, Cinder và Manila đến Drover, Waygate, Lumen và Palimpsest. Chuẩn bị dự án và làm theo quy trình sử dụng thực tế cho từng dịch vụ.',
		heroTitle: ['Môi trường bạn cần.', 'Cách tự xây dựng môi trường đó.'], heroCopy: ['Từ một máy ảo đến các cụm máy và dữ liệu dùng chung của nhóm.', 'Chọn dịch vụ, chuẩn bị và kiểm tra kết quả.'],
		getStarted: 'Bắt đầu', searchLabel: 'Tìm kiếm tài liệu', searchHelp: 'Nhập tên dịch vụ hoặc tác vụ. Ví dụ: IP nổi, bản sao lưu, kubeconfig', searchPlaceholder: 'Tìm dịch vụ hoặc tác vụ…',
		guideCount: (count: number) => `${count} hướng dẫn sử dụng`, resultsCount: (count: number) => `${count} kết quả tìm kiếm`,
		noResultsTitle: 'Không có tài liệu phù hợp', noResultsDescription: 'Thử tìm theo tên dịch vụ hoặc tên tác vụ ngắn hơn.', resetSearch: 'Đặt lại tìm kiếm',
		availability: 'Các hướng dẫn này mô tả bảng điều khiển hiện tại. Dịch vụ được bật, tài nguyên khả dụng, mô hình và quyền trong dự án phụ thuộc vào môi trường triển khai.',
		prerequisites: 'Trước khi bắt đầu', consoleUsage: 'Sử dụng trong bảng điều khiển', consoleNote: 'Đăng nhập và chọn dự án sẽ sử dụng. Việc xem và thay đổi tuân theo quyền và cấu hình dịch vụ của dự án đó.',
		serviceUnavailable: 'Dịch vụ này bị tắt trong môi trường hiện tại.', related: 'Hướng dẫn liên quan', official: 'Tài liệu tham khảo chính thức', toc: 'Mục lục bài viết', inThisArticle: 'Trong bài viết này', breadcrumbs: 'Đường dẫn tài liệu',
		copy: 'Sao chép', copyLabel: (label: string) => `Sao chép ${label}`, copySuccess: 'Đã sao chép lệnh.', copyFailure: 'Không thể sao chép. Hãy chọn lệnh bên dưới và sao chép thủ công.',
		screenshotOpen: 'Mở ảnh gốc (tab mới)', screenshotOpenLabel: (alt: string) => `${alt} — Mở ảnh gốc (tab mới)`, screenshotKoreanNote: 'Ảnh chụp màn hình thực tế của bảng điều khiển bằng tiếng Hàn; thông tin cá nhân và mã định danh tài nguyên đã được che.',
		notFound: 'Không tìm thấy tài liệu', failed: 'Không thể mở tài liệu', errorRecovery: 'Kiểm tra địa chỉ hoặc tìm tên dịch vụ trên trang tài liệu.', goHome: 'Đi đến trang tài liệu',
		categories: [
			{ id: 'start', label: 'Bắt đầu', description: 'Chuẩn bị tài khoản và dự án, sau đó tạo tài nguyên đầu tiên.' },
			{ id: 'openstack', label: 'OpenStack', description: 'Sử dụng dịch vụ điện toán, mạng, lưu trữ và các dịch vụ đám mây cốt lõi.' },
			{ id: 'afterglow', label: 'Dịch vụ Afterglow', description: 'Làm việc với các cụm máy, VPN, AI và môi trường nghiên cứu có thể tái sử dụng.' },
		],
	},
	bn: {
		userDocs: 'ব্যবহারকারীর নথি', serviceDocs: 'সেবার নথি', docsHome: 'নথির মূল পাতা · অনুসন্ধান',
		skip: 'মূল বিষয়বস্তুতে যান', home: 'মূল পাতা', homeTitle: 'মূল পাতায় যান', backHome: 'মূল পাতায় ফিরে যান',
		navigation: 'নথিতে নেভিগেশন', menu: 'নথির মেনু', publicNote: ['লগইন ছাড়াই নথি পড়ুন।', 'প্রকৃত কাজের জন্য প্রকল্পের অনুমতি প্রয়োজন।'],
		consoleAccess: 'কনসোল খুলুন', consoleReturn: 'কনসোলে ফিরে যান', language: 'ভাষা নির্বাচন করুন',
		themeSystem: 'সিস্টেমের থিম', themeDark: 'ডার্ক মোড', themeLight: 'লাইট মোড', themeChange: 'থিম পরিবর্তন করুন',
		guideTitle: 'ব্যবহার নির্দেশিকা', indexDescription: 'Nova, Neutron, Octavia, Cinder ও Manila থেকে Drover, Waygate, Lumen ও Palimpsest পর্যন্ত। প্রকল্প প্রস্তুত করুন এবং প্রতিটি সেবার ব্যবহারিক ধাপ অনুসরণ করুন।',
		heroTitle: ['আপনার প্রয়োজনীয় পরিবেশ।', 'নিজেই তৈরি করার উপায়।'], heroCopy: ['একটি ভার্চুয়াল মেশিন থেকে ক্লাস্টার ও দলের যৌথ ডেটা পর্যন্ত।', 'সেবা বেছে নিন, প্রস্তুত করুন এবং ফলাফল যাচাই করুন।'],
		getStarted: 'শুরু করুন', searchLabel: 'নথি অনুসন্ধান করুন', searchHelp: 'সেবা বা কাজের নাম লিখুন। যেমন: Floating IP, ব্যাকআপ, kubeconfig', searchPlaceholder: 'সেবা বা কাজ খুঁজুন…',
		guideCount: (count: number) => `${count}টি ব্যবহার নির্দেশিকা`, resultsCount: (count: number) => `${count}টি অনুসন্ধান ফলাফল`,
		noResultsTitle: 'মিলে যায় এমন কোনো নথি নেই', noResultsDescription: 'সেবার নাম বা আরও ছোট কাজের নাম দিয়ে খুঁজুন।', resetSearch: 'অনুসন্ধান মুছুন',
		availability: 'এই নির্দেশিকাগুলো বর্তমান কনসোলের ব্যবহার বর্ণনা করে। সক্রিয় সেবা, উপলভ্য রিসোর্স, মডেল ও প্রকল্পের অনুমতি আপনার স্থাপনার ওপর নির্ভর করে।',
		prerequisites: 'শুরুর আগে', consoleUsage: 'কনসোলে ব্যবহার করুন', consoleNote: 'লগইন করে যে প্রকল্পে কাজ করবেন সেটি নির্বাচন করুন। তথ্য দেখা ও পরিবর্তন সেই প্রকল্পের অনুমতি ও সেবার কনফিগারেশন অনুযায়ী হয়।',
		serviceUnavailable: 'এই পরিবেশে সেবাটি নিষ্ক্রিয় আছে।', related: 'সংশ্লিষ্ট নির্দেশিকা', official: 'আনুষ্ঠানিক তথ্যসূত্র', toc: 'এই নিবন্ধের সূচি', inThisArticle: 'এই নিবন্ধে', breadcrumbs: 'নথির পথ',
		copy: 'কপি করুন', copyLabel: (label: string) => `${label} কপি করুন`, copySuccess: 'কমান্ড কপি করা হয়েছে।', copyFailure: 'কপি করা যায়নি। নিচের কমান্ডটি নির্বাচন করে নিজে কপি করুন।',
		screenshotOpen: 'মূল ছবি খুলুন (নতুন ট্যাব)', screenshotOpenLabel: (alt: string) => `${alt} — মূল ছবি খুলুন (নতুন ট্যাব)`, screenshotKoreanNote: 'কোরীয় ভাষার প্রকৃত কনসোলের স্ক্রিনশট; ব্যক্তিগত তথ্য ও রিসোর্স শনাক্তকারী আড়াল করা হয়েছে।',
		notFound: 'নথি পাওয়া যায়নি', failed: 'নথি খোলা যায়নি', errorRecovery: 'ঠিকানা যাচাই করুন অথবা নথির মূল পাতায় সেবার নাম দিয়ে খুঁজুন।', goHome: 'নথির মূল পাতায় যান',
		categories: [
			{ id: 'start', label: 'শুরু করা', description: 'আপনার অ্যাকাউন্ট ও প্রকল্প প্রস্তুত করে প্রথম রিসোর্স তৈরি করুন।' },
			{ id: 'openstack', label: 'OpenStack', description: 'কম্পিউটিং, নেটওয়ার্ক, স্টোরেজ ও মূল ক্লাউড সেবা ব্যবহার করুন।' },
			{ id: 'afterglow', label: 'Afterglow সেবা', description: 'ক্লাস্টার, VPN, AI ও পুনর্ব্যবহারযোগ্য গবেষণার পরিবেশ নিয়ে কাজ করুন।' },
		],
	},
};
