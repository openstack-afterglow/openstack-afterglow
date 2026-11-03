(() => {
  'use strict';
  // This local design study never reads credentials, sends requests or grants access.
  const page = document.body.dataset.flow;
  const registry = {
    signup: {
      initial: ['01 / CREATE ACCOUNT', '새로운 시작을 함께.', '이메일을 확인한 뒤 계정 정보를 설정합니다.', 'email', '확인 링크 보내기', 'sent'],
      sent: ['02 / CHECK YOUR INBOX', '메일함을 확인하세요.', '인증 링크로 가입을 계속할 수 있습니다.', 'mail', '인증 화면 예시 보기', '@verify-email'],
      error: ['CREATE ACCOUNT / ERROR', '잠시 후 다시 시도하세요.', '발송 실패 상태의 디자인 예시입니다.', 'error', '이메일 다시 입력', 'initial']
    },
    'verify-email': {
      initial: ['02 / VERIFY EMAIL', '이메일을 확인할 차례.', '실제 서비스에서는 메일의 확인 링크를 사용합니다.', 'mail', '인증 완료 예시 보기', 'done'],
      done: ['EMAIL / VERIFIED', '이메일 확인 완료.', '이제 사용자 이름과 비밀번호를 설정하세요.', 'success', '계정 설정 예시 보기', '@account-setup'],
      expired: ['EMAIL / LINK EXPIRED', '인증 링크가 만료됐어요.', '이메일을 다시 입력해 새 링크를 요청하세요.', 'error', '새 링크 요청 화면', '@signup'],
      error: ['EMAIL / INVALID LINK', '링크를 확인할 수 없어요.', '유효하지 않은 링크의 오류 화면 예시입니다.', 'error', '가입 화면으로', '@signup']
    },
    'account-setup': {
      initial: ['03 / YOUR WORKSPACE', '계정을 완성하세요.', '개인 프로젝트는 자동 생성됩니다. 조직은 초대가 필요합니다.', 'profile', '계정 만들기 예시', 'done'],
      done: ['ACCOUNT / READY', '시작할 준비가 됐어요.', '가입 완료 화면 예시입니다. 실제 계정은 생성되지 않았습니다.', 'success', '로그인 화면으로', '@login'],
      error: ['ACCOUNT / NAME IN USE', '다른 이름을 선택하세요.', '사용자 이름 중복 안내 예시입니다. 비밀번호를 다시 입력하세요.', 'profile', '다시 설정하기 예시', 'done']
    },
    'reset-password': {
      initial: ['RECOVER / ACCOUNT', '다시 연결할 수 있도록.', '계정 이메일로 비밀번호 재설정 링크를 요청하세요.', 'email', '재설정 링크 보내기', 'sent'],
      sent: ['RECOVER / CHECK INBOX', '메일함을 확인하세요.', '해당 계정이 있다면 재설정 안내가 전송됩니다.', 'mail', '새 비밀번호 화면 예시', '@new-password'],
      error: ['RECOVER / TRY AGAIN', '요청을 처리하지 못했어요.', '재설정 요청 실패 상태의 디자인 예시입니다.', 'error', '다시 요청하기', 'initial']
    },
    'new-password': {
      initial: ['RECOVER / NEW PASSWORD', '새 비밀번호를 설정하세요.', '비밀번호 정책과 유효성 검사는 실제 앱에서 유지합니다.', 'passwords', '비밀번호 변경 예시', 'done'],
      done: ['RECOVER / COMPLETE', '비밀번호 변경 완료.', '완료 화면 예시입니다. 실제 비밀번호는 변경되지 않았습니다.', 'success', '로그인 화면으로', '@login'],
      expired: ['RECOVER / LINK EXPIRED', '재설정 링크가 만료됐어요.', '보안을 위해 새로운 재설정 링크를 요청하세요.', 'error', '새 링크 요청 화면', '@reset-password'],
      error: ['RECOVER / CHECK INPUT', '입력 내용을 확인하세요.', '비밀번호 불일치 안내 예시입니다.', 'passwords', '다시 변경하기 예시', 'done']
    },
    mcp: {
      initial: ['01 / MCP CONNECTION', '도구와 워크스페이스 연결.', '요청한 클라이언트와 복귀 주소를 먼저 확인하세요.', 'client', '프로젝트·권한 확인', 'permissions'],
      permissions: ['02 / REVIEW ACCESS', '허용할 범위를 선택하세요.', '클라이언트 정보는 이전 단계에서 다시 확인할 수 있습니다.', 'permissions', '연결 허용 예시', 'done'],
      done: ['MCP / APPROVED PREVIEW', '연결 승인 화면 예시.', '권한은 부여되지 않았으며 외부 앱으로 이동하지 않습니다.', 'success', '연결 요청 다시 보기', 'initial'],
      denied: ['MCP / ACCESS DENIED', '연결을 허용하지 않았어요.', '접근 거절 화면 예시입니다. 실제 권한 변경은 없습니다.', 'locked', '연결 요청 다시 보기', 'initial'],
      error: ['MCP / REQUEST EXPIRED', '연결 요청이 만료됐어요.', '클라이언트에서 새 연결을 시작해야 합니다.', 'error', '요청 화면 예시 보기', 'initial']
    }
  };
  const glyphs = {mail:'  .------------- .\n  | \\  EMAIL  / |\n  |   \\_____/   |\n  \'-------------\'', success:'     [ + ]\n  .  VERIFIED  .\n     /  OK  /', error:'     [ ! ]\n  .  CHECK  .\n     / RETRY /', locked:'     .---.\n     |___|\n    [ DENY ]'};
  const labels = {initial:'기본',sent:'메일 안내',done:'완료 예시',expired:'링크 만료',error:'오류 예시',permissions:'권한 선택',denied:'연결 거절'};
  const states = registry[page];
  const selector = document.querySelector('#flow-state');
  for (const state of Object.keys(states)) { const o = document.createElement('option'); o.value = state; o.textContent = labels[state]; selector.append(o); }
  let current = 'initial';
  const fields = document.querySelector('#flow-fields');
  const actions = document.querySelector('.flow-actions');
  function field(id,label,type='text',placeholder='') {
    const box=document.createElement('div'); box.className='flow-field';
    const l=document.createElement('label'); l.htmlFor=id; l.textContent=label;
    const input=document.createElement('input'); input.id=id; input.type=type; input.autocomplete='off'; input.placeholder=placeholder; input.spellcheck=false;
    // No name attributes: native form fallback cannot serialize credential values.
    box.append(l,input); fields.append(box);
  }
  function detail(label,value) {const row=document.createElement('div'); row.className='flow-detail'; const l=document.createElement('span');l.textContent=label;const v=document.createElement('code');v.textContent=value;row.append(l,v);fields.append(row);}
  function select(id,label,options) {const box=document.createElement('div');box.className='flow-field';const l=document.createElement('label');l.htmlFor=id;l.textContent=label;const s=document.createElement('select');s.id=id;for(const [value,text] of options){const o=document.createElement('option');o.value=value;o.textContent=text;s.append(o);}box.append(l,s);fields.append(box);}
  function go(target) { if(target.startsWith('@')) { location.href=target.slice(1)+'.html'; } else render(target,true); }
  function button(label,target,secondary=false) {const b=document.createElement('button');b.type='button';b.className=secondary?'flow-secondary':'flow-primary';b.textContent=label;b.addEventListener('click',()=>go(target));actions.append(b);}
  function render(state,focus=false) {
    current=state;selector.value=state;
    const [kicker,title,description,kind,action,target]=states[state];
    document.querySelector('#flow-kicker').textContent=kicker;
    const heading=document.querySelector('#flow-title');heading.textContent=title;
    document.querySelector('#flow-description').textContent=description;
    const glyph=document.querySelector('.flow-glyph');glyph.textContent=glyphs[kind]||'';glyph.hidden=!glyphs[kind];
    fields.replaceChildren();actions.replaceChildren();fields.dataset.kind=kind;
    if(kind==='email') field('email','이메일','email','you@example.com');
    if(kind==='profile') {field('username','사용자 이름','text','사용자 이름');field('password','비밀번호','password','실제 비밀번호 입력 금지');}
    if(kind==='passwords') {field('password','새 비밀번호','password','새 비밀번호');field('confirm-password','새 비밀번호 확인','password','한 번 더 입력');}
    if(kind==='client') {detail('클라이언트','Afterglow Desktop · 예시');detail('Client ID','afterglow-desktop-demo');detail('복귀 주소','https://client.example/callback');detail('요청 권한','mcp:read · 읽기 전용');}
    if(kind==='permissions') {select('project','프로젝트',[['demo','DMSLAB · 예시 프로젝트']]);select('permission','접근 권한',[['read','읽기 전용 · mcp:read']]);detail('연결 대상','Afterglow Desktop · 예시');detail('적용 범위','선택 프로젝트만 · 변경 권한 없음');}
    button(action,target);
    if(page==='mcp' && state==='initial') button('거절 예시','denied',true);
    if(page==='mcp' && state==='permissions') button('요청 정보로 돌아가기','initial',true);
    if((page==='signup'||page==='reset-password')&&state==='sent') button('재발송 화면 예시','initial',true);
    const status=document.querySelector('#flow-status');status.textContent='디자인 미리보기 · 실제 요청 및 정보 저장 없음';
    status.setAttribute('role',(state==='error'||state==='expired')?'alert':'status');
    document.body.dataset.state=state;
    if(focus) heading.focus();
  }
  document.querySelector('.flow-form').addEventListener('submit',e=>{e.preventDefault();go(states[current][5]);});
  selector.addEventListener('change',()=>render(selector.value,true));
  const appearance=document.querySelector('.appearance');
  appearance.addEventListener('click',()=>{const light=document.documentElement.dataset.appearance!=='light';document.documentElement.dataset.appearance=light?'light':'dark';appearance.setAttribute('aria-pressed',String(light));appearance.setAttribute('aria-label',light?'다크 테마로 변경':'라이트 테마로 변경');document.querySelector('.appearance-copy').textContent=light?'다크':'라이트';window.afterglowLoading?.refresh();});
  render('initial');
})();
