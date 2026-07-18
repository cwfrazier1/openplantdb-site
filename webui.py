"""Community/social web UI: shared JS bundle (/app.js), CSS, and the /community page.

The catalog home page (INDEX_HTML in app.py) loads /app.js, which injects the
top-right auth nav, the sign-in modal, the "I planted this!" hook on the plant
detail modal, and the plant-request affordance. The /community page is the geo
timeline + following feed + notifications + profile views.

Everything talks to the FastAPI social endpoints in auth.py / social.py.
"""

# ---- shared CSS (matches the dark theme vars declared on the catalog page) ----
SOCIAL_CSS = r"""
:root{--bg:#0e1512;--bg2:#131e19;--card:#17241d;--line:#25382e;--ink:#e8f0ea;
 --dim:#93a89a;--accent:#7bc47f;--accent2:#d9b25f;--chip:#1e3128}
.opdb-nav{position:fixed;top:12px;right:14px;z-index:40;display:flex;gap:8px;align-items:center}
.opdb-nav a,.opdb-nav button{font:600 14px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.opdb-btn{background:var(--accent);color:#08130c;border:none;border-radius:10px;padding:9px 16px;font-weight:700;cursor:pointer}
.opdb-btn:hover{filter:brightness(1.08)}
.opdb-btn.ghost{background:var(--chip);color:var(--ink);border:1px solid var(--line)}
.opdb-navlink{color:var(--ink);text-decoration:none;background:var(--chip);border:1px solid var(--line);
 border-radius:10px;padding:9px 14px}
.opdb-navlink:hover{border-color:var(--accent)}
.opdb-bell{position:relative;background:var(--chip);border:1px solid var(--line);border-radius:10px;
 padding:8px 11px;cursor:pointer;color:var(--ink);font-size:16px;line-height:1}
.opdb-bell .dot{position:absolute;top:-5px;right:-5px;background:#e0605f;color:#fff;border-radius:999px;
 font-size:10px;font-weight:700;min-width:17px;height:17px;padding:0 4px;display:flex;align-items:center;justify-content:center}
.opdb-avatar{width:34px;height:34px;border-radius:999px;background:var(--accent);color:#08130c;
 display:flex;align-items:center;justify-content:center;font-weight:800;cursor:pointer;border:none;font-size:14px;overflow:hidden}
.opdb-avatar img{width:100%;height:100%;object-fit:cover}
.opdb-modal{position:fixed;inset:0;background:rgba(0,0,0,.66);display:none;align-items:flex-start;
 justify-content:center;padding:40px 16px;z-index:60;overflow:auto}
.opdb-modal.open{display:flex}
.opdb-sheet{background:var(--bg2);border:1px solid var(--line);border-radius:16px;max-width:520px;width:100%;padding:24px}
.opdb-sheet.wide{max-width:640px}
.opdb-sheet h2{margin:0 0 4px;font-size:22px}
.opdb-sheet .sub{color:var(--dim);margin:0 0 16px;font-size:14px}
.opdb-close{float:right;cursor:pointer;color:var(--dim);font-size:26px;line-height:1;margin:-4px -4px 0 0}
.opdb-field{display:block;margin:10px 0}
.opdb-field label{display:block;color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.04em;margin-bottom:5px}
.opdb-field input,.opdb-field textarea,.opdb-field select{width:100%;background:var(--bg);color:var(--ink);
 border:1px solid var(--line);border-radius:10px;padding:11px 12px;font-size:15px;outline:none;font-family:inherit}
.opdb-field input:focus,.opdb-field textarea:focus{border-color:var(--accent)}
.opdb-field textarea{min-height:84px;resize:vertical}
.opdb-err{color:#e88;font-size:13px;margin:8px 0 0;min-height:16px}
.opdb-switch{color:var(--dim);font-size:13px;margin-top:14px;text-align:center}
.opdb-switch a{cursor:pointer}
.opdb-dropdown{position:absolute;top:46px;right:0;width:340px;max-height:70vh;overflow:auto;background:var(--bg2);
 border:1px solid var(--line);border-radius:14px;padding:8px;display:none;box-shadow:0 12px 40px rgba(0,0,0,.5)}
.opdb-dropdown.open{display:block}
.opdb-noti{display:flex;gap:10px;padding:10px;border-radius:10px;cursor:pointer;text-decoration:none;color:var(--ink)}
.opdb-noti:hover{background:var(--card)}
.opdb-noti.unread{background:rgba(123,196,127,.09)}
.opdb-noti .b{font-size:13.5px;line-height:1.4}
.opdb-noti .t{color:var(--dim);font-size:11.5px;margin-top:3px}
/* planting cards / feed */
.opdb-feed{display:flex;flex-direction:column;gap:16px}
.pl-card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}
.pl-head{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.pl-head .who{font-weight:700}
.pl-head .who a{color:var(--ink);text-decoration:none}
.pl-head .who a:hover{color:var(--accent)}
.pl-head .meta{color:var(--dim);font-size:12.5px}
.pl-plant{color:var(--accent);font-weight:700;text-decoration:none}
.pl-plant:hover{text-decoration:underline}
.pl-note{margin:8px 0;line-height:1.55;white-space:pre-wrap}
.pl-photos{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;margin:10px 0}
.pl-photos img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:10px;cursor:pointer;border:1px solid var(--line)}
.pl-actions{display:flex;gap:16px;align-items:center;margin-top:10px;color:var(--dim);font-size:14px}
.pl-act{cursor:pointer;background:none;border:none;color:var(--dim);font-size:14px;display:flex;gap:6px;align-items:center;padding:4px}
.pl-act:hover{color:var(--ink)}
.pl-act.liked{color:#e0605f}
.pl-comments{margin-top:12px;border-top:1px solid var(--line);padding-top:12px;display:none}
.pl-comments.open{display:block}
.pl-comment{display:flex;gap:8px;margin-bottom:10px}
.pl-comment .body{font-size:14px;line-height:1.45}
.pl-comment .name{font-weight:700;margin-right:6px}
.pl-comment .time{color:var(--dim);font-size:11px}
.pl-cbox{display:flex;gap:8px;margin-top:8px}
.pl-cbox input{flex:1;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:999px;padding:9px 14px;outline:none}
.pl-cbox input:focus{border-color:var(--accent)}
.mini-av{width:30px;height:30px;border-radius:999px;background:var(--accent);color:#08130c;display:flex;
 align-items:center;justify-content:center;font-weight:800;font-size:12px;flex:0 0 auto;overflow:hidden}
.mini-av img{width:100%;height:100%;object-fit:cover}
.opdb-toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--card);
 border:1px solid var(--accent);color:var(--ink);padding:12px 20px;border-radius:12px;z-index:90;
 box-shadow:0 8px 30px rgba(0,0,0,.5);font-size:14px;opacity:0;transition:opacity .2s;pointer-events:none}
.opdb-toast.show{opacity:1}
.opdb-lightbox{position:fixed;inset:0;background:rgba(0,0,0,.9);display:none;align-items:center;
 justify-content:center;z-index:95;padding:20px}
.opdb-lightbox.open{display:flex}
.opdb-lightbox img{max-width:100%;max-height:100%;border-radius:8px}
.opdb-plantthis{margin:16px 0;padding:14px;background:var(--card);border:1px solid var(--line);border-radius:12px}
"""


def app_js(site_url: str) -> str:
    return _APP_JS.replace("__SITE__", site_url)


# ---- the shared JS bundle served at /app.js ----------------------------------
_APP_JS = r"""
(function(){
'use strict';
const SITE="__SITE__";
const $=(s,r)=>(r||document).querySelector(s);
const el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
const esc=s=>(s==null?'':String(s)).replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
const init=(s)=>(s||'?').trim()[0]?.toUpperCase()||'?';

// ---- session ----
const tok=()=>localStorage.getItem('opdb_token');
const me=()=>{try{return JSON.parse(localStorage.getItem('opdb_user')||'null');}catch(e){return null;}};
function setSession(t,u){if(t)localStorage.setItem('opdb_token',t);if(u)localStorage.setItem('opdb_user',JSON.stringify(u));renderNav();document.dispatchEvent(new Event('opdb:auth'));}
function logout(){localStorage.removeItem('opdb_token');localStorage.removeItem('opdb_user');renderNav();document.dispatchEvent(new Event('opdb:auth'));}

async function api(method,path,body,form){
  const h={};const t=tok();if(t)h['Authorization']='Bearer '+t;
  const opt={method,headers:h};
  if(form)opt.body=form;
  else if(body!==undefined){h['Content-Type']='application/json';opt.body=JSON.stringify(body);}
  const r=await fetch(path,opt);
  let data=null;try{data=await r.json();}catch(e){}
  if(r.status===401&&t){logout();}
  if(!r.ok)throw Object.assign(new Error((data&&data.detail)||('HTTP '+r.status)),{status:r.status,data});
  return data;
}
window.OPDB={api,me,tok,requireAuth,toast,timeAgo,plantingCard,avatar};

// ---- toast ----
let toastEl;
function toast(msg){
  if(!toastEl){toastEl=el('div','opdb-toast');document.body.appendChild(toastEl);}
  toastEl.textContent=msg;toastEl.classList.add('show');
  clearTimeout(toastEl._t);toastEl._t=setTimeout(()=>toastEl.classList.remove('show'),2600);
}
function timeAgo(iso){
  const s=(Date.now()-new Date(iso).getTime())/1000;
  if(s<60)return'just now';if(s<3600)return Math.floor(s/60)+'m';
  if(s<86400)return Math.floor(s/3600)+'h';if(s<604800)return Math.floor(s/86400)+'d';
  return new Date(iso).toLocaleDateString();
}
function avatar(user,cls){
  const c=cls||'mini-av';
  if(user&&user.avatar_key)return `<span class="${c}"><img src="/media/${esc(user.avatar_key)}"></span>`;
  return `<span class="${c}">${esc(init(user&&(user.display_name||user.username)))}</span>`;
}

// ---- nav ----
function renderNav(){
  let nav=$('.opdb-nav');
  if(!nav){nav=el('div','opdb-nav');document.body.appendChild(nav);}
  const u=me();
  const onCommunity=location.pathname.startsWith('/community');
  let h='';
  if(!onCommunity)h+=`<a class="opdb-navlink" href="/community">&#127793; Community</a>`;
  else h+=`<a class="opdb-navlink" href="/">&#8592; Catalog</a>`;
  if(u){
    h+=`<button class="opdb-bell" id="opdb-bell">&#128276;<span class="dot" id="opdb-dot" style="display:none">0</span></button>`;
    h+=`<button class="opdb-avatar" id="opdb-me" title="${esc(u.username)}">${u.avatar_key?`<img src="/media/${esc(u.avatar_key)}">`:esc(init(u.display_name||u.username))}</button>`;
  }else{
    h+=`<button class="opdb-btn ghost" id="opdb-login">Log in</button><button class="opdb-btn" id="opdb-signup">Sign up</button>`;
  }
  nav.innerHTML=h;
  const dd=$('#opdb-bell');if(dd){dd.appendChild(notiDropdown());dd.onclick=toggleNoti;refreshNoti();}
  const b1=$('#opdb-login');if(b1)b1.onclick=()=>authModal('login');
  const b2=$('#opdb-signup');if(b2)b2.onclick=()=>authModal('signup');
  const mb=$('#opdb-me');if(mb)mb.onclick=()=>profileMenu();
}

// ---- auth modal ----
let modalEl;
function modal(){
  if(!modalEl){modalEl=el('div','opdb-modal');modalEl.addEventListener('click',e=>{if(e.target===modalEl)closeModal();});document.body.appendChild(modalEl);}
  return modalEl;
}
function closeModal(){if(modalEl)modalEl.classList.remove('open');}
function openSheet(html,wide){const m=modal();m.innerHTML=`<div class="opdb-sheet${wide?' wide':''}">${html}</div>`;m.classList.add('open');return m;}
function requireAuth(msg){if(me())return true;authModal('login',msg);return false;}

function authModal(mode,note){
  const m=openSheet(`
    <span class="opdb-close">&times;</span>
    <h2>${mode==='signup'?'Create your account':'Welcome back'}</h2>
    <p class="sub">${note?esc(note):(mode==='signup'?'Join the community — post what you planted, comment, and follow gardeners near you.':'Log in to post, comment and follow.')}</p>
    <form id="opdb-authform">
      ${mode==='signup'?`
      <div class="opdb-field"><label>Email</label><input name="email" type="email" required autocomplete="email"></div>
      <div class="opdb-field"><label>Username</label><input name="username" required autocomplete="username" placeholder="3-24 chars"></div>
      <div class="opdb-field"><label>Display name (optional)</label><input name="display_name" autocomplete="name"></div>
      <div class="opdb-field"><label>ZIP (optional — sets your zone)</label><input name="zip" inputmode="numeric" maxlength="5"></div>
      <div class="opdb-field"><label>Password</label><input name="password" type="password" required minlength="8" autocomplete="new-password"></div>
      `:`
      <div class="opdb-field"><label>Email or username</label><input name="email" required autocomplete="username"></div>
      <div class="opdb-field"><label>Password</label><input name="password" type="password" required autocomplete="current-password"></div>
      `}
      <div class="opdb-err" id="opdb-autherr"></div>
      <button class="opdb-btn" style="width:100%;padding:12px;margin-top:6px" type="submit">${mode==='signup'?'Create account':'Log in'}</button>
    </form>
    <div class="opdb-switch">${mode==='signup'?'Already have an account? <a id="opdb-toggle">Log in</a>':"New here? <a id=\"opdb-toggle\">Create an account</a>"}</div>
  `);
  $('.opdb-close',m).onclick=closeModal;
  $('#opdb-toggle',m).onclick=()=>authModal(mode==='signup'?'login':'signup',note);
  $('#opdb-authform',m).onsubmit=async e=>{
    e.preventDefault();
    const f=Object.fromEntries(new FormData(e.target).entries());
    const err=$('#opdb-autherr',m);err.textContent='';
    const btn=e.target.querySelector('button');btn.disabled=true;
    try{
      const path=mode==='signup'?'/api/auth/signup':'/api/auth/login';
      const res=await api('POST',path,f);
      setSession(res.token,res.user);
      // adopt a locally-saved ZIP if the account has none
      if(mode==='signup'){const z=localStorage.getItem('opdb_zip');if(z&&!f.zip){try{await api('PATCH','/api/me',{zip:z});}catch(e){}}}
      closeModal();toast(mode==='signup'?'Welcome to the community!':'Logged in');
      document.dispatchEvent(new Event('opdb:auth'));
    }catch(ex){err.textContent=ex.message;btn.disabled=false;}
  };
}

// ---- profile menu ----
function profileMenu(){
  const u=me();
  const m=openSheet(`
    <span class="opdb-close">&times;</span>
    <div style="display:flex;gap:12px;align-items:center;margin-bottom:10px">
      ${avatar(u,'opdb-avatar')}
      <div><div style="font-weight:800;font-size:18px">${esc(u.display_name||u.username)}</div>
      <div style="color:var(--dim);font-size:13px">@${esc(u.username)}</div></div>
    </div>
    <div class="opdb-field"><label>Display name</label><input id="pf-name" value="${esc(u.display_name||'')}"></div>
    <div class="opdb-field"><label>Bio</label><textarea id="pf-bio">${esc(u.bio||'')}</textarea></div>
    <div class="opdb-field"><label>ZIP (your zone &amp; feed center)</label><input id="pf-zip" inputmode="numeric" maxlength="5" value="${esc(u.zip||'')}"></div>
    <label style="display:flex;gap:8px;align-items:center;color:var(--dim);font-size:14px;margin:10px 0"><input type="checkbox" id="pf-email" ${u.notify_email!==false?'checked':''}> Email notifications</label>
    <label style="display:flex;gap:8px;align-items:center;color:var(--dim);font-size:14px;margin-bottom:14px"><input type="checkbox" id="pf-push" ${u.notify_push!==false?'checked':''}> Push notifications</label>
    <div class="opdb-err" id="pf-err"></div>
    <button class="opdb-btn" style="width:100%;padding:12px" id="pf-save">Save</button>
    <div style="display:flex;justify-content:space-between;margin-top:14px">
      <a href="/community?u=${esc(u.username)}" style="color:var(--accent);font-size:14px">View my profile &#8594;</a>
      <a id="pf-logout" style="color:var(--dim);cursor:pointer;font-size:14px">Log out</a>
    </div>
  `);
  $('.opdb-close',m).onclick=closeModal;
  $('#pf-logout',m).onclick=()=>{logout();closeModal();toast('Logged out');};
  $('#pf-save',m).onclick=async()=>{
    const body={display_name:$('#pf-name',m).value,bio:$('#pf-bio',m).value,zip:$('#pf-zip',m).value,
      notify_email:$('#pf-email',m).checked,notify_push:$('#pf-push',m).checked};
    try{
      if(body.zip){try{const g=await api('GET','/api/geo/zip?zip='+encodeURIComponent(body.zip));body.lat=g.lat;body.lng=g.lng;body.home_zone=g.zone;}catch(e){}}
      await api('PATCH','/api/me',body);
      const u2=me();Object.assign(u2,body);localStorage.setItem('opdb_user',JSON.stringify(u2));
      renderNav();closeModal();toast('Saved');
    }catch(ex){$('#pf-err',m).textContent=ex.message;}
  };
}

// ---- notifications ----
function notiDropdown(){
  let d=$('#opdb-notidd');if(d)return d;
  d=el('div','opdb-dropdown');d.id='opdb-notidd';d.innerHTML='<div style="padding:16px;color:var(--dim)">Loading…</div>';
  d.addEventListener('click',e=>e.stopPropagation());
  return d;
}
async function toggleNoti(e){
  e.stopPropagation();
  const dd=$('#opdb-notidd');const open=dd.classList.toggle('open');
  if(!open)return;
  try{
    const res=await api('GET','/api/notifications');
    dd.innerHTML=res.notifications.length?'':'<div style="padding:16px;color:var(--dim)">No notifications yet.</div>';
    res.notifications.forEach(n=>{
      const a=el('a','opdb-noti'+(n.read?'':' unread'));
      a.href=n.planting_id?('/community?p='+n.planting_id):'#';
      a.innerHTML=`${avatar(n.actor)}<div><div class="b">${esc(n.body)}</div><div class="t">${timeAgo(n.created_at)}</div></div>`;
      dd.appendChild(a);
    });
    await api('POST','/api/notifications/read');
    const dot=$('#opdb-dot');if(dot)dot.style.display='none';
  }catch(ex){dd.innerHTML='<div style="padding:16px;color:#e88">'+esc(ex.message)+'</div>';}
}
async function refreshNoti(){
  if(!me())return;
  try{const res=await api('GET','/api/notifications');const dot=$('#opdb-dot');
    if(dot){if(res.unread>0){dot.textContent=res.unread>99?'99+':res.unread;dot.style.display='';}else dot.style.display='none';}}catch(e){}
}
document.addEventListener('click',()=>{const dd=$('#opdb-notidd');if(dd)dd.classList.remove('open');});
setInterval(refreshNoti,60000);

// ---- lightbox ----
let lb;
function lightbox(src){if(!lb){lb=el('div','opdb-lightbox');lb.onclick=()=>lb.classList.remove('open');document.body.appendChild(lb);}
  lb.innerHTML=`<img src="${esc(src)}">`;lb.classList.add('open');}

// ---- planting card (shared feed + detail) ----
function plantingCard(p,opts){
  opts=opts||{};
  const card=el('div','pl-card');card.dataset.pid=p.id;
  const dist=p.distance_mi!=null?` · ${p.distance_mi} mi away`:'';
  const when=p.planted_on?('planted '+new Date(p.planted_on+'T00:00:00').toLocaleDateString(undefined,{month:'short',day:'numeric'})):('posted '+timeAgo(p.created_at));
  card.innerHTML=`
    <div class="pl-head">
      ${avatar(p.author)}
      <div><div class="who"><a href="/community?u=${esc(p.author.username)}">${esc(p.author.display_name||p.author.username)}</a></div>
        <div class="meta">${when}${dist}${p.zone?' · zone '+esc(p.zone):''}</div></div>
    </div>
    <div>planted <a class="pl-plant" href="/${''}#" data-slug="${esc(p.plant_slug)}">${esc(p.plant_name||p.plant_slug)}</a></div>
    ${p.note?`<div class="pl-note">${esc(p.note)}</div>`:''}
    ${p.photos&&p.photos.length?`<div class="pl-photos">${p.photos.map(u=>`<img src="${esc(u)}" loading="lazy">`).join('')}</div>`:''}
    <div class="pl-actions">
      <button class="pl-act like${p.liked_by_me?' liked':''}">${p.liked_by_me?'&#10084;&#65039;':'&#9825;'} <span class="lc">${p.like_count}</span></button>
      <button class="pl-act cbtn">&#128172; <span class="cc">${p.comment_count}</span></button>
    </div>
    <div class="pl-comments"></div>`;
  card.querySelectorAll('.pl-photos img').forEach(im=>im.onclick=()=>lightbox(im.src));
  card.querySelector('.pl-plant').onclick=e=>{e.preventDefault();location.href='/#plant='+encodeURIComponent(p.plant_slug);};
  const likeBtn=card.querySelector('.like');
  likeBtn.onclick=async()=>{
    if(!requireAuth('Log in to like posts.'))return;
    const liked=likeBtn.classList.contains('liked');const lc=likeBtn.querySelector('.lc');
    try{
      if(liked){await api('DELETE','/api/plantings/'+p.id+'/like');likeBtn.classList.remove('liked');likeBtn.innerHTML='&#9825; <span class="lc">'+Math.max(0,(+lc.textContent)-1)+'</span>';}
      else{await api('POST','/api/plantings/'+p.id+'/like');likeBtn.classList.add('liked');likeBtn.innerHTML='&#10084;&#65039; <span class="lc">'+((+lc.textContent)+1)+'</span>';}
    }catch(ex){toast(ex.message);}
  };
  const cbox=card.querySelector('.pl-comments');
  card.querySelector('.cbtn').onclick=()=>{const o=cbox.classList.toggle('open');if(o&&!cbox.dataset.loaded)loadComments(p,cbox,card);};
  if(opts.openComments){cbox.classList.add('open');loadComments(p,cbox,card);}
  return card;
}

async function loadComments(p,box,card){
  box.dataset.loaded='1';
  box.innerHTML='<div style="color:var(--dim);font-size:13px">Loading…</div>';
  let list;try{list=(await api('GET','/api/plantings/'+p.id+'/comments')).comments;}catch(e){box.innerHTML='';list=[];}
  const render=()=>{
    box.innerHTML=list.map(c=>`<div class="pl-comment">${avatar(c.author)}<div><div class="body"><span class="name">${esc(c.author.display_name||c.author.username)}</span>${esc(c.body)}</div><div class="time">${timeAgo(c.created_at)}</div></div></div>`).join('');
    const cb=el('div','pl-cbox');
    cb.innerHTML=`<input placeholder="${me()?'Add a comment…':'Log in to comment'}" ${me()?'':'disabled'}><button class="opdb-btn" ${me()?'':'disabled'}>Post</button>`;
    box.appendChild(cb);
    const inp=cb.querySelector('input'),btn=cb.querySelector('button');
    if(!me())btn.onclick=inp.onclick=()=>requireAuth('Log in to comment.');
    else{
      const send=async()=>{const v=inp.value.trim();if(!v)return;btn.disabled=true;
        try{await api('POST','/api/plantings/'+p.id+'/comments',{body:v});
          list.push({body:v,created_at:new Date().toISOString(),author:me()});
          const cc=card.querySelector('.cc');if(cc)cc.textContent=(+cc.textContent)+1;render();}
        catch(ex){toast(ex.message);btn.disabled=false;}};
      btn.onclick=send;inp.onkeydown=e=>{if(e.key==='Enter')send();};
    }
  };
  render();
}

// ---- "I planted this!" composer ----
function plantComposer(slug,name){
  if(!requireAuth('Log in to post what you planted.'))return;
  const u=me();
  const m=openSheet(`
    <span class="opdb-close">&times;</span>
    <h2>&#127793; I planted ${esc(name||slug)}!</h2>
    <p class="sub">Share it with gardeners near you.</p>
    <div class="opdb-field"><label>Note (how's it going?)</label><textarea id="ct-note" placeholder="Started from seed, second try this year…"></textarea></div>
    <div class="opdb-field"><label>Date planted</label><input id="ct-date" type="date" value="${new Date().toISOString().slice(0,10)}"></div>
    <div class="opdb-field"><label>Photos (optional)</label><input id="ct-photos" type="file" accept="image/*" multiple></div>
    <div class="opdb-err" id="ct-err"></div>
    <button class="opdb-btn" style="width:100%;padding:12px" id="ct-save">Post it</button>
  `,true);
  $('.opdb-close',m).onclick=closeModal;
  $('#ct-save',m).onclick=async()=>{
    const btn=$('#ct-save',m);btn.disabled=true;btn.textContent='Posting…';
    try{
      const body={plant_slug:slug,plant_name:name||slug,note:$('#ct-note',m).value,planted_on:$('#ct-date',m).value};
      if(u.lat!=null){body.lat=u.lat;body.lng=u.lng;}
      const res=await api('POST','/api/plantings',body);
      const files=$('#ct-photos',m).files;
      for(const f of files){const fd=new FormData();fd.append('file',f);try{await api('POST','/api/plantings/'+res.id+'/photos',null,fd);}catch(e){}}
      closeModal();toast('Posted! &#127793;');
      document.dispatchEvent(new CustomEvent('opdb:planted',{detail:{slug,id:res.id}}));
    }catch(ex){$('#ct-err',m).textContent=ex.message;btn.disabled=false;btn.textContent='Post it';}
  };
}
window.OPDB.plantComposer=plantComposer;

// ---- hook into catalog plant-detail modal (#sheet on the home page) ----
function hookPlantModal(){
  const sheet=document.getElementById('sheet');
  if(!sheet)return;
  const mo=new MutationObserver(()=>{
    if(sheet.querySelector('.opdb-plantthis'))return;
    const codeEl=sheet.querySelector('.src code');const h2=sheet.querySelector('h2');
    if(!codeEl||!h2)return;
    const slug=codeEl.textContent.trim();const name=h2.textContent.trim();
    const box=el('div','opdb-plantthis');
    box.innerHTML=`<button class="opdb-btn" style="width:100%;padding:12px" id="opdb-plantthis-btn">&#127793; I planted this!</button>
      <div id="opdb-plant-feed" style="margin-top:14px"></div>`;
    sheet.querySelector('.directions').after(box);
    $('#opdb-plantthis-btn',box).onclick=()=>plantComposer(slug,name);
    loadPlantFeed(slug);
  });
  mo.observe(sheet,{childList:true,subtree:true});
}
async function loadPlantFeed(slug){
  const box=document.getElementById('opdb-plant-feed');if(!box)return;
  try{
    const res=await api('GET','/api/plants/'+encodeURIComponent(slug)+'/plantings?limit=10');
    if(!res.plantings.length){box.innerHTML='<div style="color:var(--dim);font-size:13px">No one has posted this yet — be the first!</div>';return;}
    box.innerHTML=`<div style="color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">${res.plantings.length} in the community</div>`;
    const feed=el('div','opdb-feed');res.plantings.forEach(p=>feed.appendChild(plantingCard(p)));box.appendChild(feed);
  }catch(e){}
}

// ---- request-a-plant when catalog search comes up empty ----
function hookRequest(){
  const grid=document.getElementById('grid'),q=document.getElementById('q');
  if(!grid||!q)return;
  const mo=new MutationObserver(()=>{
    const hasCards=grid.querySelector('.card');
    const query=q.value.trim();
    let box=document.getElementById('opdb-request');
    if(hasCards||query.length<2){if(box)box.remove();return;}
    if(box&&box.dataset.q===query)return;
    if(box)box.remove();
    box=el('div','opdb-plantthis');box.id='opdb-request';box.dataset.q=query;
    box.style.maxWidth='420px';box.style.margin='16px auto 0';box.style.textAlign='center';
    box.innerHTML=`<div style="margin-bottom:10px">Not in the catalog yet? Request <b>${esc(query)}</b> and we'll add it — requests are built first each night.</div>
      <button class="opdb-btn" id="opdb-reqbtn">&#10133; Request "${esc(query)}"</button>`;
    grid.after(box);
    $('#opdb-reqbtn',box).onclick=async()=>{
      const btn=$('#opdb-reqbtn',box);btn.disabled=true;
      try{const r=await api('POST','/api/requests',{query});toast(r.status==='voted'?'Already requested — added your vote!':'Requested! We\'ll grow it soon. &#127793;');
        btn.textContent=r.status==='voted'?'Vote added \u2713':'Requested \u2713';}
      catch(ex){toast(ex.message);btn.disabled=false;}
    };
  });
  mo.observe(grid,{childList:true});
}

// ---- deep-link: /#plant=<slug> opens the catalog modal for that plant ----
function handlePlantHash(){
  const m=location.hash.match(/plant=([^&]+)/);
  if(m&&typeof window.open==='function'&&document.getElementById('sheet')){
    try{window.open(decodeURIComponent(m[1]));}catch(e){}
  }
}

// ---- boot ----
function boot(){
  if(document.querySelector('link[data-opdb]'))return;
  const l=el('link');l.rel='stylesheet';l.href='/social.css';l.setAttribute('data-opdb','1');document.head.appendChild(l);
  renderNav();
  if(document.getElementById('sheet')){hookPlantModal();hookRequest();setTimeout(handlePlantHash,400);window.addEventListener('hashchange',handlePlantHash);}
  if(document.getElementById('opdb-community'))window.__opdbCommunity&&window.__opdbCommunity();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
"""


# ---- the /community timeline page --------------------------------------------
COMMUNITY_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Community — What Can I Plant Now</title>
<meta name="description" content="See what gardeners near you are planting right now. A live timeline within your radius, powered by OpenPlantDB.">
<link rel="stylesheet" href="/social.css">
<style>
*{box-sizing:border-box}
body{margin:0;font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink)}
a{color:var(--accent)}
.chead{padding:40px 20px 20px;text-align:center;background:radial-gradient(1200px 400px at 50% -120px,#1c3327 0%,var(--bg) 70%);border-bottom:1px solid var(--line)}
.chead h1{margin:0;font-size:clamp(26px,5vw,40px);letter-spacing:-.02em}
.chead h1 .leaf{color:var(--accent)}
.chead p{color:var(--dim);margin:10px auto 0;max-width:560px}
.cwrap{max-width:680px;margin:0 auto;padding:22px 16px 90px}
.ctabs{display:flex;gap:8px;justify-content:center;margin:0 0 18px;flex-wrap:wrap}
.ctab{cursor:pointer;background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:8px 18px;font-size:14px;color:var(--dim);font-weight:600;user-select:none}
.ctab.active{background:var(--accent);color:#08130c;border-color:var(--accent)}
.crow{display:flex;gap:10px;align-items:center;justify-content:center;margin-bottom:18px;flex-wrap:wrap}
.crow label{color:var(--dim);font-size:13px}
.crow select,.crow input{background:var(--bg2);color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:9px 12px;outline:none}
.cempty{text-align:center;color:var(--dim);padding:50px 20px}
.cmore{display:block;margin:18px auto 0;background:var(--chip);color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:11px 24px;cursor:pointer;font-weight:600}
.cprofile{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;margin-bottom:20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.cprofile .stats{display:flex;gap:18px;color:var(--dim);font-size:13px}
.cprofile .stats b{color:var(--ink);font-size:18px;display:block}
</style>
</head>
<body>
<div class="chead">
  <h1><span class="leaf">&#127793;</span> Community</h1>
  <p>See what gardeners near you are planting right now.</p>
</div>
<div class="cwrap" id="opdb-community">
  <div id="c-profile"></div>
  <div class="ctabs" id="c-tabs">
    <span class="ctab active" data-tab="nearby">&#128205; Nearby</span>
    <span class="ctab" data-tab="following">&#128101; Following</span>
  </div>
  <div class="crow" id="c-controls">
    <label>Within</label>
    <select id="c-radius">
      <option value="25">25 mi</option><option value="50">50 mi</option>
      <option value="100" selected>100 mi</option><option value="250">250 mi</option>
      <option value="500">500 mi</option><option value="3000">Anywhere</option>
    </select>
    <input id="c-zip" inputmode="numeric" maxlength="5" placeholder="ZIP" style="width:90px">
    <button class="opdb-btn ghost" id="c-locate">&#128225; Use my location</button>
  </div>
  <div id="c-feed" class="opdb-feed"></div>
  <div id="c-empty" class="cempty" style="display:none"></div>
</div>
<script src="/app.js"></script>
<script>
window.__opdbCommunity=function(){
  const $=s=>document.querySelector(s);
  const OPDB=window.OPDB;
  let tab='nearby',center=null,loading=false,done=false,before=null;
  const feed=$('#c-feed'),empty=$('#c-empty');
  const params=new URLSearchParams(location.search);

  function setCenter(lat,lng,zip){center={lat,lng};if(zip)localStorage.setItem('opdb_zip',zip);reload();}
  async function fromZip(zip){if(!zip||zip.length<5)return;try{const g=await OPDB.api('GET','/api/geo/zip?zip='+zip);setCenter(g.lat,g.lng,zip);}catch(e){OPDB.toast('Could not resolve that ZIP');}}
  function locate(){
    if(!navigator.geolocation){OPDB.toast('Location not available');return;}
    OPDB.toast('Getting your location…');
    navigator.geolocation.getCurrentPosition(
      p=>setCenter(p.coords.latitude,p.coords.longitude),
      ()=>OPDB.toast('Location denied — enter a ZIP instead'),{timeout:8000});
  }

  function reset(){feed.innerHTML='';empty.style.display='none';done=false;before=null;}
  function reload(){reset();load();}
  async function load(){
    if(loading||done)return;loading=true;
    try{
      let res;
      if(tab==='following'){
        if(!OPDB.me()){empty.textContent='Log in to see people you follow.';empty.style.display='';loading=false;return;}
        res=await OPDB.api('GET','/api/feed/following?limit=20'+(before?'&before='+encodeURIComponent(before):''));
      }else{
        if(!center){
          const u=OPDB.me();
          if(u&&u.lat!=null){center={lat:u.lat,lng:u.lng};}
          else{empty.innerHTML='Set your location to see nearby plantings.<br>Use the button or enter a ZIP above.';empty.style.display='';loading=false;return;}
        }
        const rad=$('#c-radius').value;
        res=await OPDB.api('GET',`/api/feed?lat=${center.lat}&lng=${center.lng}&radius=${rad}&limit=20`+(before?'&before='+encodeURIComponent(before):''));
      }
      const items=res.plantings||[];
      if(!items.length&&!before){empty.innerHTML=tab==='following'?'You\'re not following anyone yet, and haven\'t posted.<br>Find gardeners in the Nearby tab.':'No plantings here yet — be the first to plant something!';empty.style.display='';}
      items.forEach(p=>feed.appendChild(OPDB.plantingCard(p)));
      if(items.length<20)done=true;else before=items[items.length-1].created_at;
      if(done&&feed.children.length){const b=document.querySelector('.cmore');if(b)b.remove();}
      else if(!document.querySelector('.cmore')&&feed.children.length){const b=document.createElement('button');b.className='cmore';b.textContent='Load more';b.onclick=load;feed.after(b);}
    }catch(e){OPDB.toast(e.message);}
    loading=false;
  }

  document.querySelectorAll('.ctab').forEach(t=>t.onclick=()=>{
    document.querySelectorAll('.ctab').forEach(x=>x.classList.remove('active'));t.classList.add('active');
    tab=t.dataset.tab;$('#c-controls').style.display=tab==='following'?'none':'flex';reload();
  });
  $('#c-radius').onchange=reload;
  $('#c-locate').onclick=locate;
  $('#c-zip').addEventListener('keydown',e=>{if(e.key==='Enter')fromZip(e.target.value.trim());});
  document.addEventListener('opdb:auth',reload);

  // deep-links: ?u=username (profile) or ?p=planting_id (single post)
  const uParam=params.get('u'),pParam=params.get('p');
  if(uParam){showProfile(uParam);}
  else if(pParam){showSingle(pParam);}
  else{
    const savedZip=localStorage.getItem('opdb_zip');const u=OPDB.me();
    if(u&&u.lat!=null){load();}
    else if(savedZip){$('#c-zip').value=savedZip;fromZip(savedZip);}
    else{load();}
  }

  async function showSingle(pid){
    $('#c-tabs').style.display='none';$('#c-controls').style.display='none';
    try{const p=await OPDB.api('GET','/api/plantings/'+pid);feed.appendChild(OPDB.plantingCard(p,{openComments:true}));done=true;}
    catch(e){empty.textContent='That post could not be found.';empty.style.display='';}
    const back=document.createElement('div');back.style.textAlign='center';back.style.marginTop='20px';
    back.innerHTML='<a href="/community">&#8592; Back to the community feed</a>';$('#opdb-community').appendChild(back);
  }
  async function showProfile(username){
    $('#c-tabs').style.display='none';$('#c-controls').style.display='none';done=true;
    try{
      const res=await OPDB.api('GET','/api/users/'+encodeURIComponent(username));
      const u=res.user,mine=OPDB.me()&&OPDB.me().username.toLowerCase()===username.toLowerCase();
      const box=$('#c-profile');
      box.innerHTML=`<div class="cprofile">${OPDB.avatar(u,'opdb-avatar')}
        <div style="flex:1"><div style="font-weight:800;font-size:20px">${esc(u.display_name||u.username)}</div>
        <div style="color:var(--dim);font-size:13px">@${esc(u.username)}${u.home_zone?' · zone '+esc(u.home_zone):''}</div>
        ${u.bio?`<div style="margin-top:6px">${esc(u.bio)}</div>`:''}</div>
        <div class="stats"><span><b>${res.counts.plantings}</b>plantings</span><span><b>${res.counts.followers}</b>followers</span><span><b>${res.counts.following}</b>following</span></div>
        ${mine?'':`<button class="opdb-btn${res.following?' ghost':''}" id="c-follow">${res.following?'Following':'Follow'}</button>`}</div>`;
      const fb=document.getElementById('c-follow');
      if(fb)fb.onclick=async()=>{
        if(!OPDB.me()){OPDB.requireAuth('Log in to follow gardeners.');return;}
        const following=fb.textContent==='Following';
        try{await OPDB.api(following?'DELETE':'POST','/api/users/'+u.username+'/follow');
          fb.textContent=following?'Follow':'Following';fb.classList.toggle('ghost',!following);}catch(e){OPDB.toast(e.message);}
      };
      res.plantings.forEach(p=>feed.appendChild(OPDB.plantingCard(p)));
      if(!res.plantings.length){empty.textContent='No plantings yet.';empty.style.display='';}
    }catch(e){empty.textContent='User not found.';empty.style.display='';}
    const back=document.createElement('div');back.style.textAlign='center';back.style.marginTop='20px';
    back.innerHTML='<a href="/community">&#8592; Back to the community feed</a>';$('#opdb-community').appendChild(back);
  }
};
</script>
</body>
</html>"""
