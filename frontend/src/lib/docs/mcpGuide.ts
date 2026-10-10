import type { DocGuide } from './types';

export const mcpGuide: DocGuide = {
	slug: 'mcp',
	name: 'MCP',
	title: '개인 MCP 키로 외부 AI 연결하기',
	summary: '계정에서 프로젝트에 묶인 개인 키와 HTTP 설정을 만들고 인증된 연결을 확인합니다. 외부 AI의 Afterglow 접근과 Lumen의 외부 서버 연결을 구분합니다.',
	category: 'afterglow',
	keywords: ['MCP', '개인 키', '연결 확인', 'Claude Code', 'Cursor', 'VS Code', 'Codex', 'OAuth', 'Authorization', 'mcpServers'],
	prerequisites: [
		'Afterglow에 로그인하고 접근할 프로젝트를 선택하세요. 운영자가 MCP 서비스를 활성화하고 공개 HTTPS 엔드포인트·DNS·TLS를 준비해야 합니다.',
		'사용할 AI 클라이언트가 Streamable HTTP와 Bearer 헤더 또는 사용자별 OAuth를 지원하는지 공식 문서에서 확인하세요.'
	],
	sections: [
		{
			id: 'direction',
			title: '1. 연결 방향과 권한 이해하기',
			paragraphs: [
				'이 가이드는 외부 AI 클라이언트 → Afterglow MCP 서버의 인바운드 연결입니다. /dashboard/account의 외부 AI 접근에서 발급한 개인 키는 발급 사용자와 당시 선택한 프로젝트에 묶입니다. 브라우저 로그인 토큰, Keystone 비밀번호, Lumen 추론 API 키를 대신 넣지 마세요.',
				'Afterglow는 제한된 Keystone application credential로 위임 권한을 실행합니다. 개인 키는 다른 사용자·프로젝트나 관리자 전체 클라우드 접근을 허용하지 않습니다. 클라이언트 설정에 프로젝트 ID를 추가하거나 대시보드 프로젝트를 바꿔도 기존 키의 프로젝트는 바뀌지 않습니다.'
			],
			links: [{ label: '계정의 외부 AI 접근', href: '/dashboard/account' }]
		},
		{
			id: 'personal-key',
			title: '2. 최소 권한 개인 키 발급·회수하기',
			steps: [
				{
					title: '프로젝트와 권한을 선택합니다',
					text: ['계정 → 외부 AI 접근에서 용도를 알아볼 수 있는 이름을 입력하세요. 기본 read는 조회 권한이며 manage는 조회와 허용된 변경 권한을 포함합니다. 연결 확인과 조회에는 read를 사용하고 실제 변경이 필요한 경우에만 manage를 명시적으로 선택하세요. 클라이언트의 도구 승인도 켜 두세요.']
				},
				{
					title: '만료일을 정하고 한 번만 표시되는 비밀을 보관합니다',
					text: [
						'만료일을 비우면 서버 기본 기간이 적용됩니다. 기본 정책은 30일, 최대 90일이지만 운영자가 mcp.default_grant_ttl_days와 mcp.max_grant_ttl_days를 바꿀 수 있습니다. 서버가 허용하는 미래 만료일을 사용하세요. 무기한 키가 아닙니다.',
						'발급 직후 창에서 개인 키 또는 실제 Authorization이 포함된 JSON을 복사하세요. 평문은 한 번만 표시되며 창을 닫거나 로그인·프로젝트가 바뀌면 화면에서 지워지고 다시 조회할 수 없습니다. 클립보드나 직접 저장한 파일은 자동으로 지워지지 않으니 직접 정리하세요. 비밀 관리 도구에 보관하고 저장소·공유 설정·스크린샷·지원 요청에 올리지 마세요.'
					]
				},
				{
					title: '분실·만료·유출 시 교체하고 폐기합니다',
					text: ['분실하면 기존 키를 폐기하고 새 키를 발급하세요. 만료·폐기된 키는 더 이상 인증되지 않습니다. 클라이언트의 로컬 설정도 제거하거나 교체하세요. 계정 화면에서 개인 키와 OAuth 연결을 각각 회수할 수 있습니다.']
				}
			]
		},
		{
			id: 'http-config',
			title: '3. 계정 엔드포인트로 HTTP 설정하기',
			paragraphs: [
				'실제 URL은 계정 화면의 MCP 엔드포인트와 복사한 설정을 사용하세요. 아래 https://mcp.cloud.dmslab.re.kr는 설정 형식 예시입니다. 운영자가 DNS·TLS와 서비스를 공개하기 전에는 접속되지 않을 수 있으며 이 문서는 운영 연결 성공을 보증하지 않습니다. <personal key>를 본인 키로 바꾸고 Authorization 값은 Bearer 다음에 공백 한 개를 둡니다.',
				'운영자가 mcp.public_url을 명시하면 그 URL 자체가 리소스입니다. https://mcp.cloud.dmslab.re.kr처럼 origin만 지정한 경우 루트 /를 사용하며 /api/v1/mcp를 덧붙이지 않습니다. 설정이 없으면 공개 API 기본 URL의 /api/v1/mcp가 기본값입니다. 임의 경로나 /sse로 바꾸지 마세요.'
			],
			commands: [
				{
					label: '인증된 HTTP mcpServers JSON 예시',
					code: '{\n  "mcpServers": {\n    "my-stream-server": {\n      "type": "http",\n      "url": "https://mcp.cloud.dmslab.re.kr",\n      "headers": {\n        "Authorization": "Bearer <personal key>"\n      }\n    }\n  }\n}'
				}
			],
			callout: {
				tone: 'warning',
				title: '이 JSON도 비밀입니다',
				text: '실제 키를 넣은 JSON은 키와 동일한 접근 권한을 가집니다. 개인 클라이언트 설정에만 보관하고 프로젝트 공용 파일이나 Lumen의 전역·공유 서버 헤더에 넣지 마세요.'
			}
		},
		{
			id: 'clients',
			title: '4. 클라이언트별 형식을 구분하기',
			paragraphs: [
				'아래 형식은 각 클라이언트 공식 문서를 기준으로 정리했습니다. Afterglow에서 클라이언트별 실제 연결을 시험한 결과가 아니므로 설치된 버전의 문서와 상태 화면을 함께 확인하세요.'
			],
			bullets: [
				'Claude Code는 type이 http인 url·headers 항목과 mcpServers 형식을 지원합니다. url만 있고 type이 없으면 stdio로 해석되어 건너뜁니다. CLI에서는 --transport http와 --header를 사용하고 개인용 기본 local 또는 --scope user를 선택하세요. 팀 공유 --scope project 파일에는 개인 키를 저장하지 마세요. 추가 성공은 설정 저장일 뿐이므로 claude mcp get 또는 /mcp에서 연결 상태를 확인하세요.',
				'Cursor의 mcp.json은 최상위 mcpServers 안에 url과 headers를 둡니다. 개인 전역 설정은 ~/.cursor/mcp.json이며 headers에서 ${env:NAME} 환경 변수 치환을 사용할 수 있습니다. 공식 원격 서버 예시에는 type이 없으므로 설치된 버전의 스키마에 맞춰 입력하고 활성화·연결 상태를 확인하세요.',
				'VS Code의 .vscode/mcp.json과 사용자 프로필 mcp.json은 최상위 servers를 사용하므로 위 mcpServers JSON을 그대로 붙이지 마세요. MCP: Open User Configuration으로 개인 설정을 열고 password 입력 변수를 사용하세요. 최신 VS Code는 별도의 portable .mcp.json에서 mcpServers도 읽으므로 사용하는 파일 형식을 먼저 확인하세요.',
				'Codex는 ~/.codex/config.toml의 [mcp_servers.my-stream-server]에 url을 설정하고 bearer_token_env_var로 개인 키가 들어 있는 환경 변수 이름을 지정할 수 있습니다. Codex 프로세스에 그 변수를 안전하게 전달하고 codex mcp list 또는 /mcp로 상태를 확인하세요. TOML은 위 JSON과 다른 형식입니다.',
				'Claude Desktop이나 호스팅 AI의 커넥터 화면이 임의 Authorization 헤더를 지원한다고 가정하지 마세요. OAuth만 지원하는 클라이언트는 계정 엔드포인트를 추가한 뒤 Afterglow 로그인·프로젝트 선택·사용자별 동의를 진행합니다. 개인 키를 OAuth client secret에 넣거나 다른 사람의 연결을 공유하지 마세요. 지원 여부와 조직 정책은 해당 제품의 공식 문서에서 확인하세요.'
			],
			commands: [
				{
					label: 'Claude Code 개인 범위 추가 예시',
					code: 'claude mcp add --transport http --scope user my-stream-server \\\n  https://mcp.cloud.dmslab.re.kr \\\n  --header "Authorization: Bearer <personal key>"'
				},
				{
					label: 'VS Code 사용자 mcp.json 예시',
					code: '{\n  "inputs": [\n    {\n      "type": "promptString",\n      "id": "afterglow-mcp-key",\n      "description": "Afterglow personal MCP key",\n      "password": true\n    }\n  ],\n  "servers": {\n    "my-stream-server": {\n      "type": "http",\n      "url": "https://mcp.cloud.dmslab.re.kr",\n      "headers": {\n        "Authorization": "Bearer ${input:afterglow-mcp-key}"\n      }\n    }\n  }\n}'
				},
				{
					label: 'Codex config.toml 예시',
					code: '[mcp_servers.my-stream-server]\nurl = "https://mcp.cloud.dmslab.re.kr"\nbearer_token_env_var = "AFTERGLOW_MCP_TOKEN"'
				}
			]
		},
		{
			id: 'verify',
			title: '5. 인증된 연결 확인과 실제 조회 구분하기',
			paragraphs: [
				'발급 창의 연결 확인을 누르거나 계정의 확인 입력란에 보관한 개인 키를 입력하세요. 브라우저 인증·동일 사이트 보호가 적용된 POST /api/v1/auth/mcp-tokens/verify는 {token}을 받고 현재 로그인 사용자·프로젝트의 키인지 먼저 확인한 후 운영자가 설정한 공개 URL에 접속합니다. 임의 URL은 받지 않으며 TLS를 검증하고 redirect를 따라가지 않습니다.',
				'확인은 Bearer 인증으로 initialize → notifications/initialized → 전체 tools/list 페이지만 수행합니다. 결과의 endpoint, protocol_version, server_name, server_version, tool_count를 확인하세요. 키는 결과에 포함되지 않습니다. tools/call을 실행하지 않으므로 성공해도 OpenStack 조회·변경 성공이나 다른 AI 클라이언트의 연결을 증명하지 않습니다.',
				'실제 프로젝트 접근을 확인하려면 본인 클라이언트에서 read 키로 afterglow_quota_get 같은 조회 도구 하나를 승인하고 프로젝트·결과·발생 시각을 확인하세요. 계정 확인 성공, 클라이언트 초기화 성공, 실제 클라우드 조회 성공을 따로 기록하고 시험 목적으로 VM 삭제 같은 변경 도구를 호출하지 마세요.'
			]
		},
		{
			id: 'lumen',
			title: '6. Lumen 위임과 외부 서버 등록은 별도입니다',
			paragraphs: [
				'Afterglow 내 Lumen 채팅의 기본 클라우드 도구는 계정에서 선택한 Lumen 기본 개인 키의 위임 권한을 서버 측에서 사용합니다. 선택 해제·교체·폐기는 위임 실행에 영향을 줍니다. 이 내장 경로를 쓰려고 같은 Afterglow 서버를 외부 MCP 서버 목록에 다시 등록하거나 개인 키를 Lumen에 복사할 필요는 없습니다.',
				'Lumen → 외부 MCP 서버는 아웃바운드 연결입니다. 채팅 설정의 MCP 서버에서 이름·HTTP·외부 URL을 등록하고 필요한 경우 본인 OAuth 연결을 진행합니다. 관리자 전역 설정은 공개·사용자별 OAuth·관리자 공유 인증 정책을 구분하며 관리자만 공유 헤더를 설정합니다. 이는 외부 AI가 Afterglow에 접근하기 위한 계정 개인 키와 다른 기능입니다.'
			],
			links: [
				{ label: 'Lumen 사용 가이드', href: '/docs/lumen' },
				{ label: '채팅 설정', href: '/dashboard/chat/settings' }
			]
		},
		{
			id: 'troubleshooting',
			title: '7. 오류를 안전하게 해결하기',
			bullets: [
				'401: Bearer 헤더 누락, 잘못된 키, 만료·폐기를 확인하세요. 브라우저 토큰이나 Lumen API 키는 MCP 키가 아닙니다. 새 키를 발급하고 클라이언트 설정을 교체하세요.',
				'400 invalid_token / 403: 계정 연결 확인에서 키가 잘못됐거나 만료·폐기됐거나 현재 사용자·프로젝트 소유가 아니면 400 invalid_token으로 공개 엔드포인트 접속 전에 거부됩니다. 원래 프로젝트를 선택하거나 그 프로젝트용 새 키를 발급하세요. 동일 사이트 브라우저 요청이 아니거나 MCP 요청의 Origin이 공개 엔드포인트와 다르면 403입니다. 관리자 키를 공유해 해결하지 마세요.',
				'502·503·504·429: 계정 연결 확인 실패 화면의 원인을 확인하세요. 503은 운영자의 공개 MCP URL 설정 또는 키 저장소 문제입니다. 502는 공개 엔드포인트가 키를 거부했거나(rejected), redirect를 따르지 않아 중단했거나(redirect), 올바른 MCP 응답이 아닌 경우(protocol)입니다. 504는 Afterglow 서버에서 DNS·TLS·연결이 실패했거나 시간이 초과된 경우입니다. 429는 1분 6회 제한이므로 잠시 후 다시 시도하세요. 키를 반복 발급하기 전에 엔드포인트·프록시·인증서를 운영자와 확인하세요.',
				'404: MCP 서비스 비활성화 또는 잘못된 URL·경로일 수 있습니다. 계정의 정확한 엔드포인트를 확인하고 서비스 활성화·프록시 라우팅은 운영자에게 문의하세요. 루트 URL에 /api/v1/mcp를 임의로 붙이지 마세요.',
				'DNS·TLS·timeout: 호스트 이름이 공개 DNS에서 조회되는지, 네트워크·프록시와 인증서 이름·유효기간·신뢰 체인을 확인하세요. 연결 확인은 Afterglow 서버에서, AI 클라이언트는 자신의 네트워크에서 접속하므로 결과가 다를 수 있습니다. TLS 검증을 끄거나 redirect 대상으로 키를 보내지 마세요.',
				'400·405·406·415 또는 도구 0개: MCP 엔드포인트는 POST만 받으므로 브라우저 주소창이나 GET 요청은 405입니다. Streamable HTTP 클라이언트와 JSON 요청·Accept 협상을 확인하고 활성 서비스·권한을 검토하세요. 확인 성공 뒤 실제 조회가 실패하면 해당 OpenStack 서비스 상태와 사용자 역할을 따로 점검하세요. 도구 목록은 클라우드 응답이 아닙니다.',
				'도구 오류: read 키로 변경 도구를 호출하거나 사용자 역할·서비스 상태가 맞지 않으면 HTTP 403이 아니라 MCP 도구 오류로 표시됩니다. 변경이 꼭 필요한 경우에만 manage 키를 새로 발급하고 무조건 권한을 올리지 마세요.',
				'지원 요청에는 비밀을 제거한 엔드포인트, 클라이언트·버전, 실패 단계, 상태 코드와 발생 시각만 전달하세요. 개인 키·Authorization·복사한 인증 JSON은 첨부하지 말고 노출됐다면 즉시 폐기하세요.'
			]
		}
	],
	related: ['getting-started', 'lumen'],
	consoleLinks: [
		{ label: '계정의 외부 AI 접근', href: '/dashboard/account' },
		{ label: '채팅 설정', href: '/dashboard/chat/settings' }
	],
	externalLinks: [
		{ label: 'Claude Code 공식 MCP 문서', href: 'https://code.claude.com/docs/en/mcp' },
		{ label: 'Cursor 공식 MCP 문서', href: 'https://cursor.com/docs/mcp' },
		{ label: 'VS Code 공식 MCP 문서', href: 'https://code.visualstudio.com/docs/agent-customization/mcp-servers' },
		{ label: 'Codex 공식 MCP 문서', href: 'https://learn.chatgpt.com/docs/extend/mcp' }
	]
};
