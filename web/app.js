const $=id=>document.getElementById(id);
const fragment=new URLSearchParams(location.hash.slice(1));
if(fragment.has('token')){sessionStorage.setItem('observerToken',fragment.get('token'));history.replaceState(null,'',location.pathname);}
let hosts={}, selected='dev-backend', tab='overview', busy=false, generation=0, previousCPU=null, cpuHistory=[], logBuffer='', metricHistory={};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bytes=n=>Number.isFinite(n)?(n/1024/1024/1024).toFixed(2)+' GB':'—';
const clock=at=>new Date(at).toLocaleTimeString('pt-BR');
function spark(values){if(values.length<2)return '';const max=Math.max(...values,1),min=Math.min(...values,0);return `<svg viewBox="0 0 240 30" preserveAspectRatio="none" aria-label="Histórico desta sessão"><polyline fill="none" stroke="#36ad94" stroke-width="2" points="${values.map((v,i)=>`${i*240/(values.length-1)},${28-(v-min)/(max-min)*25}`).join(' ')}"/></svg>`;}
async function api(path,body){const response=await fetch('/api/'+path,{method:body?'POST':'GET',body:body?JSON.stringify(body):undefined,headers:{...(body?{'Content-Type':'application/json'}:{}),'X-Observer-Token':sessionStorage.getItem('observerToken')||''}});const data=await response.json();if(!response.ok)throw Error(data.error||'Falha na consulta');return data;}
function showNotice(text,error=false){$('notice').textContent=text;$('notice').classList.toggle('error',error);}
function switchHost(id){stopLiveLogs();selected=id;generation++;previousCPU=null;cpuHistory=[];metricHistory={};const h=hosts[id];$('title').textContent=h.label;$('crumb').textContent=h.label;$('subtitle').textContent=h.hostname+' · '+h.address+' · '+h.description;document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.host===id));$('logUnit').innerHTML=h.services.map(s=>`<option>${esc(s)}</option>`).join('');$('services').innerHTML='<tr><td colspan="4">Aguardando consulta deste host.</td></tr>';$('identity').textContent='';$('tunnelCards').innerHTML='';$('tunnelStatus').textContent='';$('metricCards').innerHTML='';$('rawMetrics').textContent='';$('logText').textContent='Aguardando consulta.';logBuffer='';for(const n of ['cpu','memory','disk','running'])$(n).textContent='—';$('memoryBar').style.width='0';$('diskBar').style.width='0';$('memoryDetail').textContent='Aguardando conexão SSH';$('cpuChart').innerHTML='';$('connection').textContent='○ Aguardando consulta';$('updated').textContent='Ainda sem dados';$('sshCommand').textContent=`sh connect.command ${h.user}@${h.address}`;refresh();}
async function refresh(){if(busy)return;busy=true;$('refresh').disabled=true;const id=selected,g= generation;try{const s=await api(id+'/snapshot');if(g!==generation)return;$('connection').textContent='● SSH conectado';$('connection').className='ok';$('updated').textContent='Última consulta · '+clock(s.at);$('memory').textContent=s.memoryPercent===null?'—':s.memoryPercent+'%';$('memoryDetail').textContent=bytes(s.memoryUsed)+' de '+bytes(s.memoryTotal);$('memoryBar').style.width=(s.memoryPercent||0)+'%';$('disk').textContent=s.diskPercent===null?'—':s.diskPercent+'%';$('diskBar').style.width=(s.diskPercent||0)+'%';if(previousCPU&&s.cpuTicks.length){const delta=s.cpuTicks.map((v,i)=>v-(previousCPU[i]||0));const total=delta.slice(0,8).reduce((a,b)=>a+b,0);if(total>0){const used=Math.max(0,Math.min(100,100*(1-((delta[3]||0)+(delta[4]||0))/total)));$('cpu').textContent=used.toFixed(1)+'%';cpuHistory.push(used);cpuHistory=cpuHistory.slice(-40);$('cpuChart').innerHTML=spark(cpuHistory);}}previousCPU=s.cpuTicks;const oldUnit=$('logUnit').value;$('logUnit').innerHTML=s.services.map(v=>`<option>${esc(v.Id)}</option>`).join('');if(s.services.some(v=>v.Id===oldUnit))$('logUnit').value=oldUnit;$('running').textContent=s.services.filter(v=>v.ActiveState==='active'&&v.SubState==='running').length+' / '+s.services.length;$('services').innerHTML=s.services.length?s.services.map(v=>`<tr><td>${esc(v.Id)}</td><td><span class="badge ${esc(v.ActiveState)}">${esc(v.ActiveState)}</span></td><td>${esc(v.SubState)}</td><td>${v.MainPID==='0'?'—':esc(v.MainPID)}</td></tr>`).join(''):'<tr><td colspan="4">Host consultado. Serviços ainda não cadastrados em hosts.json.</td></tr>';$('identity').textContent=s.identity;showNotice('Consulta concluída. Dados de processo não substituem testes funcionais da aplicação.');if(tab==='logs')await fetchLogs();if(tab==='metrics')await fetchMetrics();if(tab==='tunnels')await fetchTunnels();}catch(e){if(g===generation){$('connection').textContent='○ Falha de consulta · estado atual desconhecido';$('connection').className='warn';showNotice(e.message+'\nAbra a aba Acesso SSH para autenticar. Valores anteriores, se houver, estão desatualizados.',true);}}finally{busy=false;$('refresh').disabled=false;if(g!==generation)refresh();}}
let logLineLimit=200;
function trimLogBuffer(){
 if(logLineLimit==='all')return;
 const trailing=logBuffer.endsWith('\n');
 const lines=(trailing?logBuffer.slice(0,-1):logBuffer).split('\n');
 logBuffer=lines.slice(-logLineLimit).join('\n')+(trailing?'\n':'');
}
function visibleLogs(){const q=$('logFilter').value.toLowerCase();return logBuffer.split('\n').filter(l=>l.toLowerCase().includes(q)).join('\n');}
function filterLogs(){ $('logText').textContent=visibleLogs()||'Nenhuma linha encontrada.'; }

async function fetchLogs(){if($('liveLogs').checked){startLiveLogs();return;}const id=selected,g=generation,unit=$('logUnit').value;if(!unit){$('logText').textContent='Cadastre os serviços deste host em hosts.json.';return;}try{const d=await api(id+'/logs?unit='+encodeURIComponent(unit));if(g!==generation||unit!==$('logUnit').value||$('liveLogs').checked)return;logBuffer=d.text;trimLogBuffer();filterLogs();$('logStatus').textContent='Consultado às '+clock(d.at)+' · leitura com a permissão sudo existente, sem alterações na VM.';}catch(e){if(g===generation){$('logStatus').textContent='Falha de consulta: '+e.message;$('logText').textContent='Logs indisponíveis nesta consulta.';}}}
async function fetchMetrics(){const id=selected,g=generation,names=Object.keys(hosts[id].metrics);if(!names.length){$('metricCards').textContent='Nenhum endpoint cadastrado para este host.';return;}const results=await Promise.all(names.map(async name=>{try{return {name,data:await api(id+'/metrics?name='+name)};}catch(e){return {name,error:e.message};}}));if(g!==generation)return;let raw=[];$('metricCards').innerHTML=results.map(({name,data,error})=>{const title={jboss:'JBoss · 8890',jvm2:'JVM não identificada · 8891',nginx:'Exportador Nginx · 9113'}[name]||name;if(error)return `<article class="metric-box"><h3>${esc(title)}</h3><p class="warn">Indisponível: ${esc(error)}</p></article>`;raw.push(title+'\n'+data.raw);const values=data.samples;const find=n=>values.find(x=>x.name===n)?.value;const heap=values.filter(s=>s.name.startsWith('jvm_memory_bytes_used{')&&s.name.includes('area="heap"')).reduce((a,b)=>a+b.value,0);const uptime=find('jvm_uptime_seconds');const up=find('nginx_up');const value=name==='nginx'?up:heap;metricHistory[name]=[...(metricHistory[name]||[]),value||0].slice(-40);return `<article class="metric-box"><h3>${esc(title)}</h3><strong>${name==='nginx'?(up===1?'Coleta OK':up===0?'Falha de coleta':'Sem nginx_up'):(heap?bytes(heap):'Heap não informado')}</strong><div class="spark">${spark(metricHistory[name])}</div><p>${name==='nginx'?'Estado do exportador; não representa a saúde do Nginx.':'Heap usado · '+(uptime!==undefined?'JVM ativa há '+Math.floor(uptime/60)+' min':values.length+' amostras disponíveis')}</p><p>Consultado às ${clock(data.at)}</p></article>`;}).join('');$('rawMetrics').textContent=raw.join('\n\n');}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{stopLiveLogs();tab=b.dataset.tab;document.querySelectorAll('[data-tab]').forEach(v=>v.classList.toggle('selected',v===b));['overview','metrics','logs','tunnels','access'].forEach(id=>$(id).classList.toggle('hidden',id!==tab));if(tab==='logs')fetchLogs();if(tab==='metrics')fetchMetrics();if(tab==='tunnels')fetchTunnels();});
$('connectSSH').onclick=()=>document.querySelector('[data-tab=access]').click();$('refresh').onclick=refresh;$('fetchLogs').onclick=fetchLogs;$('fetchMetrics').onclick=fetchMetrics;$('logUnit').onchange=()=>{stopLiveLogs();fetchLogs();};$('logFilter').oninput=filterLogs;$('copySSH').onclick=async()=>{try{await navigator.clipboard.writeText($('sshCommand').textContent);$('copySSH').textContent='Copiado';}catch{ $('copySSH').textContent='Selecione e copie o comando acima';}};
(async()=>{try{hosts=await api('hosts');$('hosts').innerHTML=Object.entries(hosts).map(([id,h])=>`<button data-host="${esc(id)}">${esc(h.label)}</button>`).join('');document.querySelectorAll('[data-host]').forEach(b=>b.onclick=()=>switchHost(b.dataset.host));switchHost(selected);}catch(e){showNotice(e.message,true);}})();
setInterval(()=>{if($('auto').checked&&!document.hidden)refresh();},15000);

async function fetchTunnels(){const id=selected,g=generation;try{const entries=await api(id+'/tunnels');if(g!==generation)return;$('tunnelCards').innerHTML=entries.length?entries.map(t=>`<article class="metric-box"><h3>${esc(t.label)}</h3><p><span class="badge ${t.active?'active':''}">${t.active?'Túnel aberto':'Fechado'}</span></p><pre>127.0.0.1:${t.localPort}
→ ${esc(hosts[id].address)}:${t.remotePort}</pre>${t.note?`<p>${esc(t.note)}</p>`:''}<button data-forward="${esc(t.id)}" data-action="${t.active?'stop':'start'}">${t.active?'Encerrar túnel':'Abrir túnel'}</button>${t.active&&t.kind==='http'?`<p><a href="http://127.0.0.1:${t.localPort}${esc(t.path||'/')}" target="_blank" rel="noopener noreferrer">Abrir endpoint ↗</a></p>`:''}</article>`).join(''):'<p>Nenhuma porta confirmada cadastrada para este host. O app não presume portas de debug. Configure forwards em hosts.json após confirmar o listener.</p>';$('tunnelCards').querySelectorAll('[data-forward]').forEach(b=>b.onclick=async()=>{b.disabled=true;$('tunnelStatus').textContent='Processando túnel…';try{await api(id+'/tunnels',{id:b.dataset.forward,action:b.dataset.action});if(g===generation){$('tunnelStatus').textContent=b.dataset.action==='start'?'Túnel aberto. Isso não confirma a saúde do serviço remoto.':'Túnel encerrado.';await fetchTunnels();}}catch(e){if(g===generation){$('tunnelStatus').textContent=e.message+' Se a porta local já está ocupada por um túnel manual, encerre-o primeiro. Para autenticar, use Conectar SSH.';b.disabled=false;}}});}catch(e){if(g===generation)$('tunnelStatus').textContent=e.message;}}
$('refreshTunnels').onclick=fetchTunnels;

let liveController=null,liveKey='';
function stopLiveLogs(){if(liveController)liveController.abort();liveController=null;liveKey='';}
async function startLiveLogs(){
 const unit=$('logUnit').value,key=selected+'/'+unit;
 if(liveController&&liveKey===key)return;
 stopLiveLogs();
 if(!unit||tab!=='logs')return;
 const controller=new AbortController();liveController=controller;liveKey=key;
 logBuffer='';filterLogs();$('logStatus').textContent='Conectando ao acompanhamento em tempo real…';
 try{
  const response=await fetch('/api/'+selected+'/logs-stream?unit='+encodeURIComponent(unit),{headers:{'X-Observer-Token':sessionStorage.getItem('observerToken')||''},signal:controller.signal});
  if(!response.ok){const data=await response.json();throw Error(data.error||'Falha no acompanhamento');}
  if(liveController!==controller)return;
  $('logStatus').textContent='● Tempo real ativo · limite de linhas conforme seleção · desmarque para parar.';
  const reader=response.body.getReader(),decoder=new TextDecoder();let pending='';
  while(true){
   const {value,done}=await reader.read();if(liveController!==controller)return;
   if(done)throw Error('A conexão de tempo real foi encerrada. Desmarque e marque Tempo real para reconectar.');
   pending+=decoder.decode(value,{stream:true});
   let end;
   while((end=pending.indexOf('\n'))>=0){
    const event=JSON.parse(pending.slice(0,end));pending=pending.slice(end+1);
    if(event.text){logBuffer+=event.text;trimLogBuffer();filterLogs();if($('logScroll').checked)$('logText').scrollTop=$('logText').scrollHeight;}
    if(event.error)throw Error(event.error);
   }
  }
 }catch(error){if(liveController===controller&&error.name!=='AbortError'){$('logStatus').textContent='Tempo real interrompido: '+error.message;$('liveLogs').checked=false;}}
 finally{controller.abort();if(liveController===controller){liveController=null;liveKey='';}}
}
$('liveLogs').onchange=()=>{stopLiveLogs();fetchLogs();};
window.addEventListener('pagehide',stopLiveLogs);

$('clearLogs').onclick=()=>{logBuffer='';$('logText').textContent='';};

document.querySelectorAll('[data-log-limit]').forEach(button=>button.onclick=()=>{
 logLineLimit=button.dataset.logLimit==='all'?'all':Number(button.dataset.logLimit);
 document.querySelectorAll('[data-log-limit]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
 trimLogBuffer();filterLogs();
 if($('logScroll').checked)$('logText').scrollTop=$('logText').scrollHeight;
});
$('copyLogs').onclick=async()=>{
 const text=visibleLogs();
 if(!text){$('logCopyStatus').textContent='Nenhum log visível para copiar.';return;}
 try{await navigator.clipboard.writeText(text);$('logCopyStatus').textContent='Logs copiados.';}
 catch{$('logCopyStatus').textContent='Não foi possível copiar. Selecione os logs e copie manualmente.';}
};
