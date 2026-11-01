/* Standalone component studies. No timed fake progress or network requests. */
(() => {
  'use strict';
  const $ = (selector) => document.querySelector(selector);
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  let paused = reduce.matches, loaded = false, timer = 0, step = 0, disposed = false;
  const noise = (n) => { const v = Math.sin(n * 127.1 + 311.7) * 43758.5453; return v - Math.floor(v); };
  const terms = 'OpenStackNovaNeutronCinderGlanceKeystoneAfterglowPalimpsestLumen';
  const ramp = '.:;+=*#%@';
  function orbit() {
    const lines = [];
    for (let row = 0; row < 28; row++) {
      let line = '';
      for (let column = 0; column < 64; column++) {
        const x = (column - 31.5) / 1.95, y = row - 12;
        const radius = Math.hypot(x, y);
        const ring = Math.exp(-(((radius - 9) / 1.15) ** 2));
        const reflection = row > 22 ? Math.exp(-(((Math.hypot(x + Math.sin(row + step * .2), 24 - row) - 9) / 1.5) ** 2)) * .35 : 0;
        const light = Math.max(ring, reflection);
        line += light > .08 ? (noise(column * 137 + row * 353) > .7 ? terms[(column + row + Math.floor(step / 4)) % terms.length] : ramp[Math.min(7, Math.floor(light * 8))]) : ' ';
      }
      lines.push(line);
    }
    $('.ascii-orbit').textContent = lines.join('\n');
  }
  function setProgress(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    const bounded = Math.max(0, Math.min(100, numeric));
    const cells = 26, filled = Math.round(bounded / 100 * cells);
    $('.character-bar').textContent = '[' + '#'.repeat(filled) + '·'.repeat(cells - filled) + ']';
    $('.percent').textContent = bounded + '%';
    $('#task-progress').setAttribute('aria-valuenow', String(bounded));
    $('#progress-value').value = String(bounded); $('#progress-output').textContent = bounded + '%';
    $('#task-label').textContent = bounded === 100 ? '작업 공간 준비가 완료되었습니다.' : bounded === 0 ? '작업 공간 준비를 기다리고 있습니다.' : '이미지와 네트워크를 확인하고 있습니다.';
    const states = bounded === 100 ? ['done','done','done'] : bounded === 0 ? ['waiting','waiting','waiting'] : ['done','active','waiting'];
    document.querySelectorAll('.steps li').forEach((li, i) => { li.dataset.step=states[i];li.querySelector('span').textContent=states[i]==='done'?'✓':states[i]==='active'?'›':'·';li.querySelector('small').textContent=states[i]==='done'?'완료':states[i]==='active'?'진행 중':'대기'; });
  }
  const statusValues = {
    loading: ['[~]', '프로젝트 정보를 동기화하고 있습니다.', '진행 중'],
    success: ['[✓]', '프로젝트 정보 동기화가 완료되었습니다.', '완료'],
    error: ['[!]', '동기화에 실패했습니다. 연결 상태를 확인해 주세요.', '실패']
  };
  function setStatus(state) {
    if (!Object.hasOwn(statusValues,state)) return;
    const values=statusValues[state];
    $('.status-glyph').textContent=values[0];$('.status-copy').textContent=values[1];$('.status-tag').textContent=values[2];
    document.querySelectorAll('[data-status]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.status===state)));
  }
  function table(showData) {
    loaded = Boolean(showData);
    $('#instances').setAttribute('aria-busy', String(!loaded));
    $('#table-status').textContent=loaded?'예시 인스턴스 3개를 표시하고 있습니다.':'인스턴스 목록을 불러오고 있습니다.';
    $('#table-toggle').textContent=loaded?'로딩 화면 표시':'예시 데이터 표시';
    $('#instance-rows').replaceChildren();
    const rows=loaded?[
      ['demo-web-01','실행 중','2 vCPU / 4 GiB','private-net','nova'],
      ['demo-worker-01','실행 중','4 vCPU / 8 GiB','private-net','nova'],
      ['demo-build-01','중지됨','8 vCPU / 16 GiB','build-net','nova']
    ]:Array.from({length:5},()=>Array.from({length:5},()=>''));
    for(const row of rows){const tr=document.createElement('tr');if(!loaded)tr.setAttribute('aria-hidden','true');for(const value of row){const td=document.createElement('td');td.textContent=loaded?value:'··::··::··';if(!loaded)td.className='skeleton';tr.append(td);}$('#instance-rows').append(tr);}
    $('.table-foot').hidden=loaded;
  }
  function render(){
    orbit();
    const size=32, start=step%(size+9)-9;
    $('.flow-bar').textContent='['+Array.from({length:size},(_,i)=>i>=start&&i<start+8?'#':i>=start-3&&i<start?':':'·').join('')+']';
    if(!loaded)document.querySelectorAll('.skeleton').forEach((cell,i)=>{cell.textContent=Array.from({length:10},(_,j)=>((j+i+step)%9)<3?':':((j+i+step)%9)<5?'·':' ').join('');});
  }
  function sync(){clearInterval(timer);timer=0;$('#motion').setAttribute('aria-pressed',String(paused));$('#motion').textContent=paused?'애니메이션 재생':'애니메이션 일시정지';if(!paused&&!document.hidden&&!disposed)timer=setInterval(()=>{step++;render();},140);}
  const onMotion=()=>{paused=!paused;sync();};
  const onPreference=()=>{paused=reduce.matches;sync();};
  const onProgress=(event)=>setProgress(event.target.value);
  const onTable=()=>table(!loaded);
  const onStatus=(event)=>{const choice=event.target.closest('[data-status]');if(choice)setStatus(choice.dataset.status);};
  const reset=()=>{step=0;setProgress(42);setStatus('loading');table(false);render();};
  $('#motion').addEventListener('click',onMotion);$('#reset').addEventListener('click',reset);$('#progress-value').addEventListener('input',onProgress);$('#table-toggle').addEventListener('click',onTable);$('.status-options').addEventListener('click',onStatus);reduce.addEventListener('change',onPreference);document.addEventListener('visibilitychange',sync);
  reset();sync();
  window.afterglowProgress=Object.freeze({setProgress,setStatus,setTableLoaded:table,destroy(){disposed=true;clearInterval(timer);$('#motion').removeEventListener('click',onMotion);$('#reset').removeEventListener('click',reset);$('#progress-value').removeEventListener('input',onProgress);$('#table-toggle').removeEventListener('click',onTable);$('.status-options').removeEventListener('click',onStatus);reduce.removeEventListener('change',onPreference);document.removeEventListener('visibilitychange',sync);delete window.afterglowProgress;}});
})();
