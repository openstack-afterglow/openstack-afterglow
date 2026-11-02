(() => {
  'use strict';
  const root = document.documentElement;
  const appearance = document.querySelector('.appearance');
  appearance.addEventListener('click', () => {
    const light = root.dataset.appearance !== 'light';
    root.dataset.appearance = light ? 'light' : 'dark';
    appearance.setAttribute('aria-pressed', String(light));
    appearance.setAttribute('aria-label', light ? '다크 테마로 변경' : '라이트 테마로 변경');
    document.querySelector('.appearance-copy').textContent = light ? '다크' : '라이트';
    window.afterglowLoading?.refresh();
  });
  const password = document.querySelector('#password');
  document.querySelector('#visibility').addEventListener('click', event => {
    const shown = password.type === 'password'; password.type = shown ? 'text' : 'password';
    event.currentTarget.setAttribute('aria-pressed', String(shown));
    event.currentTarget.setAttribute('aria-label', shown ? '비밀번호 숨기기' : '비밀번호 표시');
    event.currentTarget.querySelector('span').textContent = shown ? '[ : ]' : '[ · ]';
  });
  const status = document.querySelector('#demo-status');
  document.querySelector('form').addEventListener('submit', event => {
    event.preventDefault();
    // Never read, send, log or persist the preview's credential values.
    status.textContent = '디자인 미리보기입니다. 실제 인증 요청은 보내지 않았습니다.';
  });
  for (const button of document.querySelectorAll('[data-example]')) button.addEventListener('click', () => {
    status.textContent = ({ recovery: '실제 앱에서는 기존 계정 복구 화면으로 연결합니다.', sso: 'SSO 버튼 예시입니다. 실제 인증은 시작하지 않습니다.', help: '시작 가이드 연결 위치 예시입니다.' })[button.dataset.example];
  });
})();
