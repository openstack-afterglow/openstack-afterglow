(() => {
  'use strict';
  const states={
    working:{title:'로그아웃하고 있습니다.',description:'연결과 인증 정보를 정리하고 있습니다.',steps:['완료','정리 중','대기'],art:'[ : : · · ]',message:'진행 중 디자인 예시입니다. 실제 로그아웃은 실행하지 않습니다.',canLeave:false},
    done:{title:'로그아웃했습니다.',description:'모든 정리 단계가 완료된 상태의 예시입니다.',steps:['완료','완료','완료'],art:'[ + ]',message:'다시 사용할 때 로그인해 주세요. 자동으로 이동하지 않습니다.',canLeave:true},
    warning:{title:'일부 정리를 확인해 주세요.',description:'서버 확인이 완료되지 않은 상태의 예시입니다.',steps:['완료','미확인','완료'],art:'[ ! ]',message:'서버 세션 폐기를 확인하지 못했습니다. 기기의 인증 정보는 제거됐습니다.',canLeave:true},
    error:{title:'기기 정리를 확인해 주세요.',description:'로컬 인증 정보 제거가 확인되지 않은 상태의 예시입니다.',steps:['완료','완료','미확인'],art:'[ ! ]',message:'기기의 인증 정보 제거를 확인하지 못했습니다. 이 창을 닫아 주세요.',canLeave:false}
  };
  function render(){const key=document.querySelector('#logout-state').value,state=states[key];document.body.dataset.state=key;document.querySelector('#logout-title').textContent=state.title;document.querySelector('#logout-description').textContent=state.description;document.querySelector('.logout-art').textContent=state.art;document.querySelector('#logout-status').textContent=state.message;document.querySelectorAll('[data-step]').forEach((node,i)=>node.textContent=state.steps[i]);document.querySelector('.logout-steps').setAttribute('aria-busy',String(key==='working'));document.querySelector('#back-login').disabled=!state.canLeave;}
  document.querySelector('#logout-state').addEventListener('change',render);
  document.querySelector('#back-login').addEventListener('click',()=>{location.href='login.html';});
  document.querySelector('.appearance').addEventListener('click',()=>{const light=document.documentElement.dataset.appearance!=='light';document.documentElement.dataset.appearance=light?'light':'dark';const button=document.querySelector('.appearance');button.setAttribute('aria-pressed',String(light));button.setAttribute('aria-label',light?'다크 테마로 변경':'라이트 테마로 변경');document.querySelector('.appearance-copy').textContent=light?'다크':'라이트';window.afterglowLoading?.refresh();});
  render();
})();
