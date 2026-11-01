(() => {
  'use strict';
  const formats = window.AfterglowCharacterFormats;
  const media = matchMedia('(prefers-reduced-motion: reduce)');
  let step=14, paused=media.matches, unknown=false, amount=42, timer=0;
  const types=[['spinner','문자 회전 · 기본','[ | ]'],['dots','점 이동','[ : · · ]'],['bars','세로 막대','[ | : | ]'],['brackets','대괄호 채움','[ : : ]'],['wave','물결표','[ ~ ]']];
  const signals=document.querySelector('#signals');
  for(const [type,label,example] of types){
    const article=document.createElement('article');article.className='signal-card';
    const title=document.createElement('h3');title.textContent=label;
    const strip=document.createElement('div');strip.className='strip';strip.setAttribute('role','status');
    const glyph=document.createElement('span');glyph.className='signal';glyph.dataset.signal=type;glyph.setAttribute('aria-hidden','true');
    const copy=document.createElement('span');copy.textContent='프로젝트 정보를 불러오고 있습니다.';
    strip.append(glyph,copy);const code=document.createElement('small');code.textContent='indicator="'+type+'"'+(type==='spinner'?' · 앱 기본값':'');article.append(title,strip,code);signals.append(article);
  }
  for(const node of document.querySelectorAll('[data-settled]'))node.textContent=formats.settledSignal(node.dataset.settled)+' '+node.dataset.label;
  function draw(){
    document.querySelector('#linear pre').textContent=formats.linearProgress(unknown?null:amount,step,true);
    document.querySelector('#circular pre').textContent=formats.circularProgress(unknown?null:amount,step,true);
    for(const glyph of document.querySelectorAll('[data-signal]'))glyph.textContent=formats.statusSignal(glyph.dataset.signal,step);
  }
  function values(){
    for(const id of ['linear','circular']){
      const node=document.getElementById(id);node.querySelector('.amount-label').textContent=unknown?'진행률 미확정':amount+'%';
      for(const [key,value]of Object.entries({'aria-valuemin':'0','aria-valuemax':'100','aria-valuenow':String(amount)})){if(unknown)node.removeAttribute(key);else node.setAttribute(key,value);}
    }
    document.querySelector('#value').textContent=amount+'%';document.querySelector('#amount').disabled=unknown;
    document.querySelector('#unknown').setAttribute('aria-pressed',String(unknown));draw();
  }
  function sync(){clearInterval(timer);timer=0;const button=document.querySelector('#motion');button.setAttribute('aria-pressed',String(paused));button.textContent=paused?'애니메이션 재생':'애니메이션 일시정지';if(!paused&&!document.hidden)timer=setInterval(()=>{step++;draw();},140);}
  document.querySelector('#motion').addEventListener('click',()=>{paused=!paused;sync();});
  document.querySelector('#unknown').addEventListener('click',()=>{unknown=!unknown;values();});
  document.querySelector('#amount').addEventListener('input',event=>{amount=Number(event.target.value);values();});
  media.addEventListener('change',()=>{paused=media.matches;sync();});document.addEventListener('visibilitychange',sync);
  window.addEventListener('pagehide',()=>clearInterval(timer));window.addEventListener('pageshow',sync);
  values();sync();
})();
