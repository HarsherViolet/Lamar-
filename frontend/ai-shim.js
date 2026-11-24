/* Lamar on Vercel: replaces claude.ai's built-in AI with either the free cloud
   endpoint (/api/ai → Gemini, then Groq, then OpenAI if keys are set) or Ollama
   running on this computer. Also adds AI settings and backup/restore to the brief. */
{
const CFG_KEY='lamar-ai';
const cfg=()=>{try{return JSON.parse(localStorage.getItem(CFG_KEY))||{}}catch(e){return{}}};
const setCfg=c=>{try{localStorage.setItem(CFG_KEY,JSON.stringify(c))}catch(e){}};
const b64=blob=>new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]);r.onerror=rej;r.readAsDataURL(blob)});
function parseJSON(t){t=String(t||'').trim().replace(/^```(?:json)?\s*/i,'').replace(/```\s*$/,'');
  try{return JSON.parse(t)}catch(e){const m=t.match(/[\[{][\s\S]*[\]}]/);if(m){try{return JSON.parse(m[0])}catch(x){}}
  throw{code:'bad_json',message:'The AI reply wasn\'t in the expected format. Try again.'}}}

async function viaServer(prompt,json,images){
  let r;try{r=await fetch('/api/ai',{method:'POST',headers:{'Content-Type':'application/json','x-lamar-passcode':cfg().passcode||''},body:JSON.stringify({prompt,json,images})})}
  catch(e){throw{code:'unavailable',message:'You seem to be offline.'}}
  const d=await r.json().catch(()=>({error:'The AI service sent a bad reply.',code:'unavailable'}));
  if(r.status===401){const p=window.prompt('Enter your Lamar passcode');if(p){setCfg({...cfg(),passcode:p});return viaServer(prompt,json,images)}
    throw{code:'not_granted',message:'A passcode is needed to use AI here.'}}
  if(!r.ok)throw{code:d.code||'unavailable',message:d.error};
  return d.text}
async function viaOllama(prompt,json,images){const c=cfg();
  const base=(c.ollamaUrl||'http://localhost:11434').replace(/\/+$/,'');
  const model=(images.length&&c.ollamaVision)||c.ollamaModel;
  if(!model)throw{code:'not_configured',message:'Pick an Ollama model in AI settings.'};
  if(images.length&&!c.ollamaVision)throw{code:'no_images',message:'Pick an Ollama model for scans and photos in AI settings, or paste the text.'};
  const msg={role:'user',content:prompt};if(images.length)msg.images=images.map(i=>i.data);
  const body={model,stream:false,messages:[msg],options:{temperature:0.4}};if(json)body.format='json';
  let r;try{r=await fetch(base+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
  catch(e){throw{code:'unavailable',message:'Can\'t reach Ollama. Is it running, and does it allow this site? See AI settings.'}}
  if(!r.ok)throw{code:'unavailable',message:'Ollama error '+r.status+'. Check the model name in AI settings.'};
  const d=await r.json();return(d.message&&d.message.content)||''}
async function run(input,opts,json){
  const prompt=Array.isArray(input)?input.map(m=>m.content).join('\n\n'):String(input);
  const images=await Promise.all((opts&&opts.images||[]).map(async b=>({mime:b.type||'image/png',data:await b64(b)})));
  return cfg().engine==='ollama'?viaOllama(prompt,json,images):viaServer(prompt,json,images)}
const sample=async(input,opts={})=>({text:await run(input,opts,false),truncated:false});
sample.json=async(input,opts={})=>{let v=parseJSON(await run(input,opts,true));
  if(v&&typeof v==='object'&&!Array.isArray(v)){const ks=Object.keys(v);if(ks.length===1&&Array.isArray(v[ks[0]]))v=v[ks[0]]}return v};
sample.limits=async()=>({images:cfg().engine==='ollama'?!!cfg().ollamaVision:true});
window.claude={use:async n=>n==='sample'?sample:null};

/* ---------- settings panel ---------- */
const box=document.getElementById('aiSettings');
if(box){
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  box.innerHTML=`<details class="how" id="aiBox"><summary>AI settings and backup</summary>
  <div class="chips" style="margin-top:6px"><label><input type="radio" name="eng" value="cloud"> Free cloud</label><label><input type="radio" name="eng" value="ollama"> Ollama on this computer</label></div>
  <p class="hint" id="cloudNote">Uses the free AI key set up in Vercel. Works on every device.</p>
  <div id="olBox">
    <label for="olUrl">Ollama address</label><input type="url" id="olUrl" placeholder="http://localhost:11434">
    <div class="ract"><button class="btn small" id="olTest">Connect</button><span class="hint" id="olNote" role="status"></span></div>
    <label for="olModel">Model for text</label><select id="olModel"><option value="">Connect first</option></select>
    <label for="olVision">Model for scans and photos (optional)</label><select id="olVision"><option value="">None</option></select>
    <p class="hint">Ollama has to allow this site. Quit Ollama, set <code>OLLAMA_ORIGINS=${esc(location.origin)}</code>, and start it again. Only works on the computer running Ollama, in Chrome or Edge.</p>
  </div>
  <label>Your data</label><p class="hint" style="margin-top:0">Your brief, drafts and tracker are saved in this browser only. Back them up, or move them to another device.</p>
  <div class="ract"><button class="btn small" id="bkDl">Back up</button><label class="btn small" for="bkUp" style="display:inline-flex;align-items:center;margin:0">Restore</label><input class="sr" type="file" id="bkUp" accept=".json,application/json"></div>
  </details>`;
  const $=s=>box.querySelector(s);
  const fill=(sel,names,keep,none)=>{sel.innerHTML=(none?`<option value="">${none}</option>`:'')+names.map(n=>`<option${n===keep?' selected':''}>${esc(n)}</option>`).join('')};
  function show(){const c=cfg(),eng=c.engine||'cloud';box.querySelectorAll('[name=eng]').forEach(i=>i.checked=i.value===eng);
    $('#olBox').hidden=eng!=='ollama';$('#cloudNote').hidden=eng==='ollama';$('#olUrl').value=c.ollamaUrl||'http://localhost:11434';
    if(c.models){fill($('#olModel'),c.models,c.ollamaModel);fill($('#olVision'),c.models,c.ollamaVision,'None')}}
  async function connect(){const note=$('#olNote'),base=$('#olUrl').value.trim().replace(/\/+$/,'')||'http://localhost:11434';note.textContent='Connecting…';
    try{const r=await fetch(base+'/api/tags');if(!r.ok)throw 0;const d=await r.json();const models=(d.models||[]).map(m=>m.name);
      if(!models.length){note.textContent='Connected, but no models are installed. Run: ollama pull llama3.1';return}
      const c=cfg();const pick=c.ollamaModel&&models.includes(c.ollamaModel)?c.ollamaModel:models[0];
      const vis=models.find(m=>/llava|vision|vl|gemma3|minicpm-v|moondream/i.test(m))||'';
      setCfg({...c,ollamaUrl:base,models,ollamaModel:pick,ollamaVision:c.ollamaVision&&models.includes(c.ollamaVision)?c.ollamaVision:vis});
      show();note.textContent=`Connected. ${models.length} model${models.length>1?'s':''} found.`}
    catch(e){note.textContent='Couldn\'t connect. Check Ollama is running and OLLAMA_ORIGINS is set (see below).'}}
  box.addEventListener('change',e=>{const t=e.target,c=cfg();
    if(t.name==='eng'){setCfg({...c,engine:t.value});show();if(t.value==='ollama'&&!c.models)connect()}
    if(t.id==='olModel')setCfg({...c,ollamaModel:t.value});
    if(t.id==='olVision')setCfg({...c,ollamaVision:t.value});
    if(t.id==='olUrl')setCfg({...c,ollamaUrl:t.value.trim()});
    if(t.id==='bkUp'&&t.files[0]){const f=t.files[0];t.value='';f.text().then(txt=>{const d=JSON.parse(txt);if(!d||!d.profile)throw 0;
      if(!window.confirm('Replace everything in this browser with the backup?'))return;localStorage.setItem('lamar',JSON.stringify(d));location.reload()}).catch(()=>alert('That file isn\'t a Lamar backup.'))}});
  box.addEventListener('click',e=>{if(e.target.id==='olTest')connect();
    if(e.target.id==='bkDl'){const data=localStorage.getItem('lamar')||'{}';const a=document.createElement('a');
      a.href=URL.createObjectURL(new Blob([data],{type:'application/json'}));a.download=`lamar-backup-${new Date().toISOString().slice(0,10)}.json`;
      document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}});
  show();
}
if('serviceWorker' in navigator)window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}));
}
