'use strict';
const $ = id => document.getElementById(id);
const apiRoot = '/api/cloud';
let busy = false, conversation = null;
const el = (tag, text, cls) => { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; };
// Render only simple bold emphasis; all model text stays in text nodes.
function formatted(tag,value){
  const node=el(tag), text=typeof value==='string'?value:'', pattern=/\*\*([^*\r\n]+)\*\*/g;
  let start=0;
  for(const match of text.matchAll(pattern)){
    node.append(document.createTextNode(text.slice(start,match.index)),el('strong',match[1]));
    start=match.index+match[0].length;
  }
  node.append(document.createTextNode(text.slice(start)));
  return node;
}
function status(message, error=false){$('status').textContent=message;$('status').classList.toggle('error',error);}
function signedOut(){
  $('conv-title').textContent='';$('workspace').hidden=true;$('auth').hidden=false;$('logout').hidden=true;conversation=null;
  for(const id of ['doc-list','conv-list','messages','agent-list','agent-detail','qa-result','chat-result','structured-result'])$(id).replaceChildren();
  for(const id of ['conv-detail','agent-detail','qa-result','chat-result','structured-result'])$(id).hidden=true;
  document.querySelectorAll('form').forEach(f=>f.reset());
  show('overview');
}
function signedIn(){ $('auth').hidden=true;$('workspace').hidden=false;$('logout').hidden=false;$('login-form').reset();show('overview'); }
async function api(path, method='GET', body){
  const options={method,credentials:'same-origin',cache:'no-store',redirect:'error',headers:{Accept:'application/json'}};
  if(body!==undefined){options.headers['Content-Type']='application/json';options.body=JSON.stringify(body);}
  const res=await fetch(apiRoot+path,options);
  if(!res.ok){
    if(res.status===401&&path!=='/login'){signedOut();throw Error('Session expired. Please sign in.');}
    const data=await res.json().catch(()=>({}));
    const detail=typeof data.detail==='string'?data.detail:`Request failed (${res.status})`;
    throw Error(detail==='Daily request budget reached'?detail+' — daily limits reset at 00:00 UTC.':detail);
  }
  return res.json();
}
async function task(fn){
  if(busy)return;busy=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);status('Working…');
  try{const message=await fn();status(message||'Ready.');}catch(e){status(e.message||'Request failed.',true);}finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);}
}
function show(name){
  document.querySelectorAll('[data-panel]').forEach(p=>p.hidden=p.dataset.panel!==name);
  document.querySelectorAll('nav [data-view]').forEach(b=>{if(b.dataset.view===name)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
}
function button(label,action,cls='secondary'){const b=el('button',label,cls);b.type='button';b.disabled=busy;b.addEventListener('click',()=>task(action));return b;}
function row(container,label,...buttons){const r=el('div',undefined,'row');r.append(el('span',label),...buttons);container.append(r);}
function form(id,fn){$(id).addEventListener('submit',e=>{e.preventDefault();const f=e.currentTarget;const values=new FormData(f);const action=e.submitter?.dataset.action;task(()=>fn(values,action,f));});}
function consent(v){if(v.get('consent')!=='on')throw Error('Explicit consent is required.');return true;}
function renderAnswer(id,data){const target=$(id);target.replaceChildren(el('h2','KnowledgeAI answer'),formatted('p',data.answer||'No answer returned.'));if(data.status)target.append(el('p',`Status: ${data.status}`,'hint'));if(data.topic)target.append(el('p',`Topic: ${data.topic} · General knowledge, no document sources`,'hint'));if(Array.isArray(data.sources)&&data.sources.length){target.append(el('h2','Supporting sources'));for(const s of data.sources){target.append(el('strong',`${s.source} · Chunk ${s.chunk_number}`),el('p',s.evidence_quote));}}target.hidden=false;}
async function listDocs(){const d=await api('/documents');const box=$('doc-list');box.replaceChildren();if(!d.documents.length)box.append(el('p','No indexed documents yet.'));for(const doc of d.documents)row(box,doc.source,button('Delete',async()=>{if(!confirm('Delete this document and its index?'))return;await api('/documents/'+encodeURIComponent(doc.document_id),'DELETE');$('qa-result').replaceChildren();$('qa-result').hidden=true;await listDocs();return 'Document deleted.';},'danger'));}
async function listConv(){const data=await api('/conversations');const box=$('conv-list');box.replaceChildren(el('h2','Saved conversations'));if(!data.conversations.length)box.append(el('p','No conversations yet.'));for(const c of data.conversations)row(box,c.title,button('Open',()=>openConv(c.id)),button('Delete',async()=>{if(!confirm('Delete this conversation?'))return;await api('/conversations/'+encodeURIComponent(c.id),'DELETE');if(conversation===c.id){conversation=null;$('conv-detail').hidden=true;$('messages').replaceChildren();$('send-conv').reset();}await listConv();return 'Conversation deleted.';},'danger'));}
async function openConv(id){const c=await api('/conversations/'+encodeURIComponent(id));conversation=c.id;$('conv-title').textContent=c.title;const box=$('messages');box.replaceChildren();for(const m of c.messages){const msg=el('div',undefined,m.role==='assistant'?'message assistant':'message');msg.append(el('strong',m.role==='assistant'?'KnowledgeAI':'You'),m.role==='assistant'?formatted('div',m.content):el('div',m.content));box.append(msg);}$('conv-detail').hidden=false;return 'Conversation loaded.';}
async function listAgents(){const data=await api('/agents');const box=$('agent-list');box.replaceChildren(el('h2','Saved workflows'));if(!data.workflows.length)box.append(el('p','No workflows yet.'));for(const a of data.workflows)row(box,`${a.title} · ${a.status}`,button('Open',()=>openAgent(a.id)),button('Delete',async()=>{if(!confirm('Delete this workflow?'))return;await api('/agents/'+encodeURIComponent(a.id),'DELETE');$('agent-detail').replaceChildren();$('agent-detail').hidden=true;await listAgents();return 'Workflow deleted.';},'danger'));}
async function openAgent(id){const path='/agents/'+encodeURIComponent(id);const a=await api(path);const box=$('agent-detail');box.replaceChildren(el('h2',a.title),el('p',`Status: ${a.status}`),el('div',a.draft,'draft'));if(a.status==='pending'){for(const approve of [true,false])box.append(button(approve?'Approve report':'Reject report',async()=>{if(!confirm(approve?'Approve this reviewed report?':'Reject this draft?'))return;await api(path+'/decision','POST',{approve});await listAgents();await openAgent(id);return approve?'Report approved.':'Report rejected.';},approve?'secondary':'danger'));}else if(a.status==='approved'){const link=el('a','Download approved Markdown report');link.href=apiRoot+path+'/report';box.append(link);}box.hidden=false;return 'Workflow loaded.';}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>task(async()=>{const view=b.dataset.view;show(view);if(view==='documents')await listDocs();if(view==='conversations')await listConv();if(view==='agents')await listAgents();})));
form('login-form',async(v,action,f)=>{const data={email:v.get('email'),password:v.get('password')};try{if(action==='register'){await api('/register','POST',data);return 'Account created. Enter your credentials to sign in.';}await api('/login','POST',data);signedIn();return 'Signed in.';}finally{f.elements.password.value='';}});
$('logout').addEventListener('click',()=>task(async()=>{await api('/logout','POST',{});signedOut();return 'Signed out.';}));
form('upload',async(v,_,f)=>{const file=v.get('file');const agreed=consent(v);if(!file||!file.name||!file.size||file.size>12000||! /\.(txt|md)$/i.test(file.name))throw Error('Choose a nonempty TXT or MD file, maximum 12,000 bytes.');const text=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());await api('/documents','POST',{filename:file.name,text,consent:agreed});f.reset();await listDocs();return 'Document indexed.';});
for(const [id,field] of [['ask','question'],['chat','message'],['structured','question']])form(id,async(v,_,f)=>{const target=id==='ask'?'qa-result':id+'-result';$(target).replaceChildren();$(target).hidden=true;const data=await api('/'+id,'POST',{[field]:v.get(field),consent:consent(v)});renderAnswer(target,data);f.elements.consent.checked=false;return 'Answer received.';});
form('new-conv',async(v,_,f)=>{const data=await api('/conversations','POST',{title:v.get('title')});f.reset();await listConv();await openConv(data.id);return 'Conversation created.';});
form('send-conv',async(v,_,f)=>{if(!conversation)throw Error('Open a conversation first.');const id=conversation;await api('/conversations/'+encodeURIComponent(id)+'/messages','POST',{message:v.get('message'),consent:consent(v)});f.reset();await openConv(id);await listConv();return 'Message saved.';});
form('new-agent',async(v,_,f)=>{const raw=v.get('numbers').trim();const numbers=raw?raw.split(',').map(s=>{if(!s.trim())throw Error('Enter valid comma-separated numbers.');return Number(s);}):[];if(numbers.length>20||numbers.some(n=>!Number.isFinite(n)||Math.abs(n)>1000000))throw Error('Enter at most 20 numbers between -1,000,000 and 1,000,000.');const a=await api('/agents','POST',{title:v.get('title'),text:v.get('text'),numbers,consent:consent(v)});f.reset();await listAgents();await openAgent(a.id);return 'Draft created. Review before approving.';});
window.addEventListener('pageshow',e=>{if(e.persisted)location.reload();});
task(async()=>{try{await api('/me');signedIn();return 'Signed in.';}catch(e){signedOut();return e.message==='Session expired. Please sign in.'?'Sign in to your private workspace.':e.message;}});
