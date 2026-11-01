/* Reviewable state assets only: no requests, capture, audio or simulated progress. */
(() => {
  'use strict';
  const assets = {
    chat: {title:'Chat',label:'01 / CHAT RESPONSE',initial:'waiting',states:{
      waiting:['pending','응답을 준비하고 있습니다','첫 응답을 기다립니다. 생성 중단 동작은 유지합니다.'],
      thinking:['pending','내용을 검토하고 있습니다','실제 추론·도구 활동이 있으면 해당 상태를 표시합니다.'],
      sending:['pending','답변을 전송하고 있습니다','선택한 응답을 처리하고 있습니다.'],
      blocked:['blocked','도구 실행 권한을 확인해 주세요','승인 요청이 처리 중인 상태와 구분합니다.'],
      ready:['ready','응답이 도착했습니다','로딩 장식을 멈추고 실제 응답 내용을 표시합니다.'],
      failed:['error','응답을 가져오지 못했습니다','이전 대화는 유지하고 명시적으로 다시 시도합니다.']}},
    image:{title:'Image',label:'02 / IMAGE PIPELINE',initial:'downloading',states:{
      queued:['pending','이미지 작업이 대기 중입니다','서버가 보고한 대기 상태를 표시합니다.'],
      generating:['pending','이미지를 생성하고 있습니다','확인되지 않은 백분율은 표시하지 않습니다.'],
      downloading:['pending','생성된 이미지를 가져오고 있습니다','생성 완료와 미리보기 다운로드는 별도 단계입니다.'],
      decoding:['pending','이미지 미리보기를 준비하고 있습니다','브라우저에서 이미지를 읽을 때까지 기다립니다.'],
      ready:['ready','이미지를 표시할 준비가 됐습니다','이 에셋 영역은 실제 생성 결과로 교체합니다.'],
      failed:['error','이미지를 불러오지 못했습니다','이 이미지의 로딩을 끝내고 개별 재시도를 제공합니다.'],
      canceled:['blocked','이미지 작업이 취소됐습니다','실패 또는 진행 중으로 표시하지 않습니다.']}},
    audio:{title:'Audio',label:'03 / AUDIO STUDIO',initial:'buffering',states:{
      uploading:['pending','음성을 업로드하고 확인하고 있습니다','녹음·업로드·전사를 서로 다른 상태로 구분합니다.'],
      synthesizing:['pending','음성을 생성하고 있습니다','생성이 끝나면 재생 준비 상태로 전환합니다.'],
      transcribing:['pending','음성을 텍스트로 변환하고 있습니다','전사가 완료된 후 실제 결과를 표시합니다.'],
      buffering:['pending','재생할 음성을 불러오고 있습니다','이 문자 패턴은 상징적 표시이며 실제 음성 파형이 아닙니다.'],
      ready:['ready','음성을 재생할 준비가 됐습니다','브라우저 canplay 상태 이후 재생 제어를 제공합니다.'],
      failed:['error','음성을 재생할 수 없습니다','생성 실패와 미디어 재생 오류를 별도로 처리합니다.']}},
    realtime:{title:'Realtime voice',label:'04 / REALTIME HANDSHAKE',initial:'socket',states:{
      permission:['pending','마이크 사용 권한을 확인하고 있습니다','사용자의 실제 권한 응답을 기다립니다.'],
      session:['pending','음성 세션을 준비하고 있습니다','세션 발급 요청을 처리하고 있습니다.'],
      socket:['pending','음성 서버에 연결하고 있습니다','소켓 생성만으로 연결 완료 처리하지 않습니다.'],
      device:['pending','오디오 장치를 준비하고 있습니다','서버 준비 응답과 오디오 장치 준비까지 연결 중을 유지합니다.'],
      waiting:['pending','응답 음성을 기다리고 있습니다','실제 발화가 시작되면 응답 대기를 종료합니다.'],
      ready:['ready','실시간 음성이 연결됐습니다','마이크·출력 장치가 준비된 실제 연결 상태입니다.'],
      failed:['error','음성 연결이 중단됐습니다','연결 중 표시를 종료하고 재연결 동작을 제공합니다.']}}
  };
  const art = {
    chat:['   . : : : : : : : : .   ',' :                     : ',' :  L u m e n          : ',' :  . . .  : : :       : ',' :                     : ','   : : : : : : : : : :   ','        : :              ','       :                 '],
    image:['   : : : : : : : : : :   ','   :                 :   ','   :    . : : .      :   ','   :  :         :    :   ','   : :    : :    :   :   ','   :  :         :    :   ','   :    : : : :      :   ','   : : : : : : : : : :   '],
    audio:['                         ','            :            ','      :     :     :      ','   :  :  :  :  :  :  :   ',' : :  :  :  :  :  :  : : ','   :  :  :  :  :  :  :   ','      :     :     :      ','            :            '],
    realtime:['       . : : : .         ','    :             :      ','  :     : : :       :    ',' :    :       :      :   ',' :   :   : :   :     :   ','  :    :     :      :    ','    :    : :      :      ','       : : : :           ']
  };
  let step=0,paused=matchMedia('(prefers-reduced-motion: reduce)').matches,timer=0,disposed=false;
  const motion=matchMedia('(prefers-reduced-motion: reduce)');
  const cards=new Map();
  for(const [key,asset] of Object.entries(assets)){
    const card=document.createElement('section');card.className='asset-card';
    card.innerHTML='<div class="card-head"><p class="eyebrow"></p><label class="state-select">예시 상태 <select></select></label></div><div class="stage"><pre class="art" aria-hidden="true"></pre><div class="signal" aria-hidden="true"></div><div class="status" role="status" aria-live="polite" aria-atomic="true"><h3></h3><p></p></div></div><div class="state-code"><span></span><button class="retry" type="button" hidden>예시 다시 시도</button></div>';
    card.querySelector('.eyebrow').textContent=asset.label;
    const select=card.querySelector('select');select.setAttribute('aria-label',asset.title+' 예시 상태');
    for(const [name,state] of Object.entries(asset.states)){const option=document.createElement('option');option.value=name;option.textContent=state[1];select.append(option);}
    select.value=asset.initial;
    const item={card,select,key,state:asset.initial};cards.set(key,item);
    select.addEventListener('change',()=>setState(key,select.value));
    card.querySelector('.retry').addEventListener('click',()=>setState(key,asset.initial));
    document.querySelector('main').append(card);setState(key,asset.initial);
  }
  function setState(key,state){
    const item=cards.get(key),config=assets[key]?.states[state];if(!item||!config)return;
    item.state=state;item.select.value=state;item.card.dataset.kind=config[0];
    item.card.querySelector('h3').textContent=config[1];item.card.querySelector('.status p').textContent=config[2];
    item.card.querySelector('.state-code span').textContent=key+' / '+state+' / '+(config[0]==='pending'?'busy':'settled');
    item.card.querySelector('.retry').hidden=config[0]!=='error';
    renderItem(item);
  }
  function renderItem(item){
    const kind=assets[item.key].states[item.state][0];
    const symbol=kind==='error'?'!':kind==='blocked'?'/':kind==='ready'?'+':':';
    item.card.querySelector('.art').textContent=art[item.key].map((row,i)=>kind==='pending'?row.replaceAll(':',(step+i)%7===0?'.':':'):row.replaceAll(':',symbol)).join('\n');
    const position=step%26;
    item.card.querySelector('.signal').textContent=kind==='pending'?'['+Array.from({length:26},(_,i)=>i>=position&&i<position+4?'#':'·').join('')+']':kind==='error'?'[ ! ] FAILED':kind==='blocked'?'[ / ] NOT RUNNING':'[ + ] READY';
  }
  function sync(){clearInterval(timer);timer=0;const button=document.querySelector('#motion');button.setAttribute('aria-pressed',String(paused));button.textContent=paused?'애니메이션 재생':'애니메이션 일시정지';if(!paused&&!document.hidden&&!disposed)timer=setInterval(()=>{step++;for(const item of cards.values())if(assets[item.key].states[item.state][0]==='pending')renderItem(item);},160);}
  const toggle=()=>{paused=!paused;sync();};const preference=()=>{paused=motion.matches;sync();};
  document.querySelector('#motion').addEventListener('click',toggle);motion.addEventListener('change',preference);document.addEventListener('visibilitychange',sync);sync();
  window.lumenAssets=Object.freeze({setState,states:assets,destroy(){disposed=true;clearInterval(timer);document.querySelector('#motion').removeEventListener('click',toggle);motion.removeEventListener('change',preference);document.removeEventListener('visibilitychange',sync);delete window.lumenAssets;}});
})();
