const api = () => window.pywebview.api;
const $ = s => document.querySelector(s);
let STATE = {}, QUOTA = null;
// Detect the boot language from the OS locale so the very first paint is not a
// hardcoded Turkish flash: tr only when the locale starts with 'tr', else en.
function detectLang(){
  try{ return (navigator.language||'').toLowerCase().startsWith('tr') ? 'tr' : 'en'; }
  catch(_){ return 'en'; }
}
let LANG = detectLang();
document.documentElement.lang = LANG;  // set before render to avoid a lang flash
function T(k){ return (I18N[LANG] && I18N[LANG][k]) ?? I18N.en[k] ?? I18N.tr[k] ?? k; }
// Terms box: mirror the ENGINE's own parse rule (one term per line, blanks and
// #comments skipped) so the count on screen is the count that will actually be
// sent, and warn rather than silently truncate at the 50 the engine keeps.
const HOTWORDS_MAX_TERMS = 50;
// The prepacked proper-noun list (config.DEFAULT_TERMS), filled from the bridge.
let BUILTIN_TERMS = [];
function countHotwords(text){
  return (text||'').split('\n')
    .map(l=>l.trim())
    .filter(l=>l && !l.startsWith('#') && l.split('=')[0].trim())
    .length;
}
function renderHotwordCount(){
  const hw=$('#hotwords'), out=$('#hotwords-count');
  if(!hw||!out) return;
  const user=countHotwords(hw.value);
  // The prepacked list fills whatever room the user's own terms leave — same
  // rule as config.merge_hotwords, so this never promises more than is sent.
  const builtin = ($('#builtin-terms')||{}).checked ? Math.max(0, Math.min(BUILTIN_TERMS.length, HOTWORDS_MAX_TERMS-user)) : 0;
  const total=user+builtin, over=user>HOTWORDS_MAX_TERMS;
  out.textContent = over ? T('hotwords_over').replace('{n}', user).replace('{max}', HOTWORDS_MAX_TERMS)
                         : T('terms_count').replace('{total}', total).replace('{max}', HOTWORDS_MAX_TERMS)
                                           .replace('{user}', user).replace('{builtin}', builtin);
  out.style.color = over ? 'var(--amber)' : '';
  const lbl=$('#builtin-terms-lbl');
  if(lbl) lbl.textContent = T('terms_builtin').replace('{n}', BUILTIN_TERMS.length);
}
// At rest (on save, or when Settings opens) the number comes from the bridge,
// which runs the SAME merge the session handshake gets — so the count above,
// which is only a local mirror for live typing, can never quietly drift from it.
async function syncHotwordCount(){
  const hw=$('#hotwords'), out=$('#hotwords-count');
  if(!hw||!out) return;
  let s=null;
  try{ s = await api().hotword_stats(hw.value); }catch(_){ return; }
  if(!s || s.user>s.limit) return;      // over-limit keeps the warning above
  out.textContent = T('terms_count').replace('{total}', s.total).replace('{max}', s.limit)
                                    .replace('{user}', s.user).replace('{builtin}', s.builtin);
}
// Voice gender. Lives in Settings › Translation only — it is set once for a
// meeting, not adjusted per session, so a picker beside the language selects
// crowded the main screen for a rarely-touched choice. Only Qwen-routed targets
// can honor it (the Gemini translate model ignores the voice field outright —
// measured), so the picker stays visible and a hint says so rather than the
// setting silently doing nothing.
const VOICE_GENDERS = ['auto','female','male'];
function fillVoiceSelects(){
  ['#voice-in-s','#voice-out-s'].forEach(sel=>{
    const el=$(sel); if(!el) return;
    const cur=el.value;
    el.innerHTML='';
    VOICE_GENDERS.forEach(g=>{
      const o=document.createElement('option');
      o.value=g; o.textContent=T('vg_'+g);
      el.appendChild(o);
    });
    if(cur) el.value=cur;
  });
}
function renderBuiltinTerms(){
  BUILTIN_TERMS = Array.isArray(STATE.builtin_terms_list) ? STATE.builtin_terms_list : [];
  const box=$('#builtin-terms-list');
  // textContent, never innerHTML: the list is ours, but a term box is exactly
  // where injected markup would hide.
  if(box) box.textContent = BUILTIN_TERMS.join(' · ');
}
function voiceChoiceOk(lang){
  const list=STATE.voice_choice_langs;
  // No list (old bridge) => say nothing rather than claim the setting is dead.
  return !Array.isArray(list) || list.length===0 || list.indexOf(lang)>=0;
}
function renderVoiceChoiceHints(){
  const cfg=STATE.cfg||{};
  const inOk=voiceChoiceOk(cfg.target_language_incoming||'');
  const outOk=voiceChoiceOk(cfg.target_language_outgoing||'');
  const el=$('#voice-s-hint');
  if(el) el.style.display = (inOk && outOk) ? 'none' : '';
}
function applyI18n(lang){
  LANG = I18N[lang] ? lang : 'en';
  document.documentElement.lang = LANG;
  document.querySelectorAll('[data-i18n]').forEach(el=>{ el.textContent = T(el.dataset.i18n); });
  // data-i18n-html is reserved for the single empty_small string (the only one
  // carrying a <br>); anything else stays textContent so a translation value can
  // never inject markup.
  document.querySelectorAll('[data-i18n-html]').forEach(el=>{
    const k = el.dataset.i18nHtml;
    if(k==='empty_small') el.innerHTML = T(k); else el.textContent = T(k);
  });
  document.querySelectorAll('[data-i18n-ph]').forEach(el=>{ el.placeholder = T(el.dataset.i18nPh); });
  document.querySelectorAll('[data-i18n-title]').forEach(el=>{ el.title = T(el.dataset.i18nTitle); });
  document.querySelectorAll('[data-i18n-aria]').forEach(el=>{ el.setAttribute('aria-label', T(el.dataset.i18nAria)); });
  // The spotlight tour text is driven by step state, not a fixed data-i18n
  // value; re-render it so a live language switch keeps the current step.
  if(typeof renderTour==='function' && !$('#tour').hidden) renderTour();
  // Privacy modal's lead/detail are build-aware (set in JS, not via data-i18n on
  // a single fixed key), so re-render it on a live language switch while open.
  if(typeof renderPrivacy==='function' && $('#privacy-modal').classList.contains('open')) renderPrivacy();
  // Settings Membership/About tab labels, links and the plan cards are set by id
  // (not data-i18n), so re-localize them on a live language switch while open.
  if($('#drawer').classList.contains('open')){
    if(typeof localizeSettings==='function') localizeSettings();
    if(typeof renderMembership==='function') renderMembership();
  }
  // Option labels and the two counted strings are built in JS, so a live language
  // switch has to rebuild them — data-i18n only reaches static nodes.
  if(typeof fillVoiceSelects==='function'){
    fillVoiceSelects();
    const cfg=STATE.cfg||{};
    [['#voice-in-s','incoming'],['#voice-out-s','outgoing']].forEach(([sel,leg])=>{
      const el=$(sel); if(el) el.value = cfg['voice_gender_'+leg] || 'auto';
    });
  }
  if(typeof renderHotwordCount==='function') renderHotwordCount();
}
/* ---------- tema ---------- */
function applyTheme(t){
  document.documentElement.dataset.theme = t;
  $('#iconmoon').style.display = t==='dark' ? 'block' : 'none';
  $('#iconsun').style.display  = t==='dark' ? 'none'  : 'block';
}
$('#themebtn').onclick = () => {
  const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  applyTheme(t);
  try{ api().set_cfg('ui_theme', t); }catch(e){}
};
/* ---------- yardımcılar ---------- */
// Language picker labels use each language's own endonym, not the bare code.
const LANG_NAMES = {
  "tr":"Türkçe", "en":"English", "es":"Español", "fr":"Français",
  "de":"Deutsch", "it":"Italiano", "pt":"Português", "pt-BR":"Português (Brasil)",
  "pt-PT":"Português (Portugal)", "ru":"Русский", "ar":"العربية", "zh-Hans":"简体中文",
  "ja":"日本語", "ko":"한국어", "hi":"हिन्दी", "id":"Bahasa Indonesia",
  "vi":"Tiếng Việt", "th":"ไทย", "pl":"Polski", "uk":"Українська",
  "af":"Afrikaans", "ak":"Akan", "sq":"Shqip", "am":"አማርኛ",
  "hy":"Հայերեն", "az":"Azərbaycan dili", "eu":"Euskara", "be":"Беларуская",
  "bn":"বাংলা", "bg":"Български", "my":"မြန်မာ", "ca":"Català",
  "zh-Hant":"繁體中文", "hr":"Hrvatski", "cs":"Čeština", "da":"Dansk",
  "nl":"Nederlands", "et":"Eesti", "fil":"Filipino", "fi":"Suomi",
  "gl":"Galego", "ka":"ქართული", "el":"Ελληνικά", "gu":"ગુજરાતી",
  "ha":"Hausa", "he":"עברית", "hu":"Magyar", "is":"Íslenska",
  "jv":"Basa Jawa", "kn":"ಕನ್ನಡ", "kk":"Қазақ тілі", "km":"ខ្មែរ",
  "rw":"Ikinyarwanda", "lo":"ລາວ", "lv":"Latviešu", "lt":"Lietuvių",
  "mk":"Македонски", "ms":"Bahasa Melayu", "ml":"മലയാളം", "mr":"मराठी",
  "mn":"Монгол", "ne":"नेपाली", "nb":"Norsk bokmål", "fa":"فارسی",
  "pa":"ਪੰਜਾਬੀ", "ro":"Română", "sr":"Српски", "sd":"سنڌي",
  "si":"සිංහල", "sk":"Slovenčina", "sl":"Slovenščina", "su":"Basa Sunda",
  "sw":"Kiswahili", "sv":"Svenska", "ta":"தமிழ்", "te":"తెలుగు",
  "ur":"اردو", "uz":"Oʻzbekcha", "zu":"isiZulu",
};
function langPair(code){ return [code, LANG_NAMES[code] || code]; }
function opt(sel, items, val){
  sel.innerHTML = "";
  items.forEach(it=>{
    const [v,label] = Array.isArray(it)?it:[it,it];
    const o=document.createElement('option'); o.value=v; o.textContent=label;
    if(v===val) o.selected=true; sel.appendChild(o);
  });
}
function updRange(el, vid){
  el.style.setProperty('--p', (el.value/el.max*100)+'%');
  $('#'+vid).textContent = el.value + '%';
  el.setAttribute('aria-valuetext', el.value + '%');
}
/* ── AUTH ──────────────────────────────────────────────────────────────── */
// Boot vs card: the overlay shows a loading state until check_auth resolves so a
// returning user never sees the login form flash by.
function showAuthBoot(){ $('#auth-overlay').classList.remove('hidden'); $('#auth-boot').style.display=''; $('#auth-offline').style.display='none'; $('#auth-card').style.display='none'; }
function showLoginOverlay(tab){
  $('#auth-overlay').classList.remove('hidden');
  $('#auth-boot').style.display='none'; $('#auth-offline').style.display='none'; $('#auth-card').style.display='';
  $('#auth-error').style.display='none';
  openModal($('#auth-card'), null, null);
}
// Returning user with a valid session but a transient network drop at launch:
// offer Retry instead of a (misleading) logged-out login form.
function showAuthOffline(){
  $('#auth-overlay').classList.remove('hidden');
  $('#auth-boot').style.display='none'; $('#auth-card').style.display='none'; $('#auth-offline').style.display='';
  $('#auth-offline-txt').textContent = T('auth_offline');
  $('#auth-retry').textContent = T('auth_retry');
  $('#auth-retry').onclick = ()=>{ bootAuth(); };
}
function hideLoginOverlay(){ $('#auth-overlay').classList.add('hidden'); if(activeModal===$('#auth-card')) closeModal(); }
function showErr(msg){ const e=$('#auth-error'); e.textContent=msg; e.style.display='block'; }
function hideErr(){ $('#auth-error').style.display='none'; }
async function doLogin(){
  const email = $('#login-email').value.trim();
  const pw    = $('#login-pw').value;
  const btn   = $('#login-btn');
  if(!email||!pw){ showErr(T('err_need_credentials')); return; }
  btn.disabled=true; btn.textContent=T('logging_in'); hideErr();
  try{
    const r = await api().voxis_login(email, pw);
    if(r.ok){ QUOTA=r.quota; hideLoginOverlay(); await init(); renderQuotaBadge(QUOTA); applyQuotaGate(QUOTA); }
    else { showErr(r.error || T('err_login_failed')); }
  } catch(e){ showErr(T('err_conn')); }
  btn.disabled=false; btn.textContent=T('tab_login');
}
$('#login-btn').onclick = doLogin;
$('#login-pw').onkeydown  = e => { if(e.key==='Enter') doLogin(); };
// Browser-relay Google/email sign-in (D1): opens the system browser to
// voxislive.com/app-login where PocketBase mints the token natively (Google
// blocks OAuth inside this embedded webview), then relays it back to the app.
(function(){
  const g = $('#google-login-btn'); if(!g) return;
  const label = g.querySelector('span');
  g.onclick = async () => {
    g.disabled = true; $('#login-btn').disabled = true;
    if(label) label.textContent = T('auth_browser_wait');
    hideErr();
    try{
      const r = await api().google_login();
      if(r && r.ok){ QUOTA=r.quota; hideLoginOverlay(); await init(); renderQuotaBadge(QUOTA); applyQuotaGate(QUOTA); return; }
      showErr((r && r.error) || T('err_login_failed'));
    } catch(e){ showErr(T('err_conn')); }
    g.disabled=false; $('#login-btn').disabled=false;
    if(label) label.textContent = T('auth_google');
  };
})();
$('#terms-link').onclick  = e => { e.preventDefault(); try{api().open_url('https://voxislive.com');}catch(_){} };
const PACKS_URL='https://voxislive.com/account?panel=billing';  // ?panel survives the login bounce (auth.js drops #hash)
$('#quota-upgrade-link').onclick = e => { e.preventDefault(); try{api().open_url(PACKS_URL);}catch(_){} };
$('#limit-cta').onclick = () => { try{api().open_url(PACKS_URL);}catch(_){} };
$('#limit-dismiss').onclick = e => { e.preventDefault(); closeLimitModal(); };
// Login-only card: build the create-account / forgot links (sign-up & reset
// run on the website, opened in the system browser). TR/EN per LANG.
(function(){
  var foot = $('#auth-altlinks'); if(!foot) return;
  foot.innerHTML = T('auth_no_account')
    + '<a href="#" id="signup-link">'+T('auth_create')+'</a>'
    + ' &middot; <a href="#" id="forgot-link">'+T('auth_forgot')+'</a>';
  var su = document.getElementById('signup-link'), fp = document.getElementById('forgot-link');
  if(su) su.onclick = function(e){ e.preventDefault(); try{api().open_url('https://voxislive.com/signup');}catch(_){} };
  if(fp) fp.onclick = function(e){ e.preventDefault(); try{api().open_url('https://voxislive.com/forgot-password');}catch(_){} };
})();
// Custom frameless resize: drag the right/bottom/corner grips → win_resize
// bridge (pywebview 6.2.1 lacks native frameless resize). Anchored top-left.
(function(){
  var active=null, sx=0, sy=0, sw=0, sh=0, raf=0, pw=0, ph=0, pa='br';
  function flush(){ raf=0; try{ api().win_resize(pw, ph, pa); }catch(e){} }
  function onMove(e){
    if(!active) return;
    var dx=e.screenX-sx, dy=e.screenY-sy, w=sw, h=sh;
    if(active.indexOf('r')>=0) w = sw + dx;
    if(active.indexOf('l')>=0) w = sw - dx;
    if(active.indexOf('b')>=0) h = sh + dy;
    if(active.indexOf('t')>=0) h = sh - dy;
    pw = Math.max(940, Math.round(w));
    ph = Math.max(600, Math.round(h));
    pa = active;
    if(!raf) raf = requestAnimationFrame(flush);
  }
  function onUp(){ active=null; document.body.classList.remove('resizing'); window.removeEventListener('mousemove',onMove); window.removeEventListener('mouseup',onUp); }
  document.querySelectorAll('.rsz').forEach(function(g){
    g.addEventListener('mousedown', function(e){
      e.preventDefault();
      active = g.getAttribute('data-rsz');
      sx = e.screenX; sy = e.screenY;
      sw = window.innerWidth; sh = window.innerHeight;
      document.body.classList.add('resizing');
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    });
  });
})();
// Custom frameless drag for Linux (WebKitGTK never implements
// `-webkit-app-region: drag` the way WebView2 on Windows does -- see
// is_linux in get_init). Scoped to .pywebview-drag-region, explicitly
// skipping the same controls that region's own no-drag CSS excludes, so
// clicking a button/slider/resize-grip inside the topbar never starts a
// window move. Only wired when STATE.is_linux (init()).
//
// This hands off to the WM on the FIRST mousedown pixel via win_begin_drag
// (Gtk begin_move_drag / X11 _NET_WM_MOVERESIZE) and then gets out of the
// way -- no mousemove tracking, no per-frame IPC. Two prior approaches both
// failed on this desktop: pywebview's own `easy_drag` (binds to the whole
// webview, ignores no-drag, fights every button/grip) and a JS drag that
// polled gtk_window_move() every frame (looked right in isolation, but GTK's
// own docs say a WM is free to ignore/partially-honor programmatic moves on
// an already-mapped window -- it reliably dropped the X axis while Y kept
// working). Handing the whole gesture to the WM is the only path that
// actually tracks the cursor.
function wireLinuxWindowDrag(){
  var NO_DRAG = '.brand,.topcenter,.topactions,.windowctl,.iconbtn,.wbtn,button,select,input,.rsz';
  document.querySelectorAll('.pywebview-drag-region').forEach(function(region){
    // WebKitGTK acts on `-webkit-app-region: drag` natively and would
    // otherwise consume the mousedown before this handler ever saw it.
    region.style.webkitAppRegion = 'no-drag';
    region.addEventListener('mousedown', function(e){
      if(e.button !== 0 || e.target.closest(NO_DRAG)) return;
      e.preventDefault();
      try{ api().win_begin_drag(1, e.screenX, e.screenY, e.clientX, e.clientY); }catch(err){}
    });
  });
}
/* ── QUOTA BAR ──────────────────────────────────────────────────────────── */
function renderQuotaBadge(quota){ renderQuotaBar(quota); renderTasteChip(quota); maybeShowLadder(quota); }
function renderQuotaBar(quota){
  const wrap = $('#quota-bar-wrap'); const fill = $('#quota-bar-fill'); const label = $('#quota-bar-label');
  if(!quota){ wrap.style.display='none'; return; }
  wrap.style.display='flex';
  if(quota.unlimited){
    wrap.className='quota-bar-wrap unlimited';
    fill.style.width='100%'; fill.style.background='var(--accent-strong)';
    label.textContent=T('unlimited');
  } else {
    const allowed = quota.allowed_minutes || 0;
    const used    = quota.used_minutes    || 0;
    const rem     = quota.remaining ?? Math.max(0, allowed - used);
    // On the free tier past the taste there is no license balance left to show,
    // and a red "0 minutes left" would flatly contradict the chip next to it,
    // which is busy explaining that Voxis still works. The chip carries the state.
    if(rem <= 0 && quota.cascade_ready === true){ wrap.style.display='none'; return; }
    const pct     = allowed > 0 ? Math.min(1, used / allowed) : 1;
    wrap.className = 'quota-bar-wrap' + (rem <= 0 ? ' exhausted' : '');
    fill.style.width = (pct * 100).toFixed(1) + '%';
    fill.style.background = pct >= 0.9 ? 'var(--red)' : (pct >= 0.7 ? 'var(--amber)' : 'var(--green)');
    label.textContent = rem <= 0 ? T('quota_exhausted') : (Math.round(rem) + T('min_left'));
  }
}
function isQuotaOk(quota){
  if(!quota) return true;
  if(quota.unlimited) return true;
  const rem = quota.remaining ?? Math.max(0, (quota.allowed_minutes ?? 1) - (quota.used_minutes ?? 0));
  if(rem > 0) return true;
  // Out of minutes is not out of Voxis. A free tier whose taste is spent keeps
  // translating on the cascade — the server will hand it over on request. Greying
  // the Start button out here made the entire free tier unreachable: the server
  // was ready to serve it and the client never asked.
  //
  // But "has a free tier" is not "has minutes today": gating on cascade_ready let
  // a user whose daily 10 were gone press Start straight into a 402 error line.
  // freeAvailableNow falls back to cascade_ready on an old server, so the tier
  // stays reachable either way — it can never grey the whole free tier out again.
  return freeAvailableNow(quota);
}
// The free voice speaks 35 of the 79 targets; the rest still translate, but as
// captions only. That used to be discoverable exactly one way — start a session
// in, say, Japanese and hear nothing. Say it at the moment the language is
// picked instead. Only free-tier licences see it: the paid engines voice every
// target, so for them the hint would be a lie.
function renderVoiceHint(){
  const el = $('#hear-novoice');
  if(!el) return;
  const voiced = STATE.voiced_langs;
  // No list (old bridge / broken registry) => say nothing rather than guess.
  const known = Array.isArray(voiced) && voiced.length > 0;
  const target = (STATE.cfg && STATE.cfg.target_language_incoming) || '';
  const silent = known && target && voiced.indexOf(target) < 0;
  el.style.display = (silent && isTasteTier(QUOTA)) ? '' : 'none';
}
function applyQuotaGate(quota){
  const ok = isQuotaOk(quota);
  $('#quota-gate').style.display = ok ? 'none' : '';
  renderVoiceHint();   // free-tier status just changed — the hint depends on it
  // Two very different reasons to be blocked, and the banner used to tell only
  // the paid one ("your monthly quota is used up — upgrade your licence"). A free
  // user who has simply spent today's ten minutes is not out of quota and has
  // nothing to upgrade: their minutes come back in a few hours. Say THAT.
  if(!ok){
    const msg = $('#quota-gate .qg-msg'), link = $('#quota-upgrade-link');
    const dailyOut = quota && quota.cascade_ready === true;   // free tier, day spent
    if(msg) msg.textContent = dailyOut
      ? (T('dw_title') + ' ' + T('dw_body')
          .replace('{n}', String(Math.round(freeDailyMinutes(quota))))
          .replace('{t}', resetsInText(quota)))
      : T('quota_gate_msg');
    if(link) link.textContent = dailyOut ? T('limit_cta') : T('upgrade_plan');
  }
  document.querySelectorAll('.scenario').forEach(b=>{
    if(!ok){ b.dataset.quotaBlocked='1'; } else { delete b.dataset.quotaBlocked; }
    b.classList.toggle('quota-blocked', !ok);
    b.setAttribute('aria-disabled', !ok ? 'true' : 'false');
  });
}
// Real feedback for a click on a quota-blocked tile: surface + flash the gate
// banner and shake the tile, instead of a silent no-op.
function rejectQuota(tile){
  const gate=$('#quota-gate');
  if(gate){
    gate.style.display='';
    gate.scrollIntoView({block:'nearest', behavior:'smooth'});
    gate.classList.remove('flash'); void gate.offsetWidth; gate.classList.add('flash');
    try{ gate.focus({preventScroll:true}); }catch(_){}
  }
  if(tile){ tile.classList.remove('denypulse'); void tile.offsetWidth; tile.classList.add('denypulse'); }
}
async function refreshQuotaAfterSession(){
  try{ const q = await api().voxis_quota(); if(q){ QUOTA=q; renderQuotaBadge(q); applyQuotaGate(q); checkQuotaSoftWarn(q); } } catch(e){}
}
// Soft ~80% warning: a non-blocking, auto-dismissing toast fired once per live
// session (pure JS from the 6s-refreshed QUOTA; never touches the transcript).
function checkQuotaSoftWarn(q){
  if(!SESSION_LIVE || !q || q.unlimited) return;
  const allowed = q.allowed_minutes || 0;
  const rem = q.remaining ?? Math.max(0, allowed - (q.used_minutes||0));
  const pct = allowed>0 ? (allowed-rem)/allowed : 0;
  if(pct>=0.8 && rem>0 && !warn80Shown){
    warn80Shown=true;
    const el=$('#quota-toast'); if(!el) return;
    el.textContent = T('limit_warn_prefix') + Math.round(rem) + T('min_left');
    el.style.display='flex';
    clearTimeout(el._t); el._t=setTimeout(()=>{ el.style.display='none'; }, 6500);
  }
}
/* ---------- init ---------- */
async function init(){
  STATE = await api().get_init() || {};
  if(STATE.is_linux) wireLinuxWindowDrag();
  // Defensive defaults: a partial bridge response must never throw mid-render.
  const cfg = STATE.cfg = STATE.cfg || {};
  cfg.devices = cfg.devices || {};
  cfg.hotkeys = cfg.hotkeys || {};
  $('#ver').textContent = STATE.version ? `Voxis v${STATE.version} · voxislive.com` : 'Voxis · voxislive.com';
  const topver = $('#topver');
  if(topver && STATE.version){ topver.textContent = 'v'+STATE.version; topver.style.display=''; }
  applyTheme(cfg.ui_theme || 'dark');
  applyI18n(cfg.ui_language || LANG);
  opt($('#out'),  STATE.outputs||[], cfg.devices.headphones_output_label);
  opt($('#mic'),  STATE.mics||[],    cfg.devices.microphone_label);
  opt($('#hear'), (STATE.langs||[]).map(langPair), cfg.target_language_incoming);
  opt($('#send'), (STATE.langs||[]).map(langPair), cfg.target_language_outgoing);
  renderVoiceHint();
  opt($('#profile'), STATE.profiles||[],  cfg.active_profile);
  duck.value = Math.round((cfg.duck_gain ?? 0.3)*100);  updRange(duck,'duckv');
  vol.value  = Math.round((cfg.tts_volume ?? 1)*100); updRange(vol,'volv');
  $('#subs').checked    = !!cfg.show_subtitles;
  $('#overlay').checked = !!cfg.overlay_enabled;
  $('#obs').checked     = !!cfg.obs_subtitle_enabled;
  { const ra = $('#record-audio'); if(ra) ra.checked = !!cfg.record_audio; }
  { const e = $('#auto-export-txt'); if(e) e.checked = !!cfg.auto_export_txt; }
  { const e = $('#auto-export-srt'); if(e) e.checked = !!cfg.auto_export_srt; }
  { const e = $('#auto-export-vtt'); if(e) e.checked = !!cfg.auto_export_vtt; }
  { const sl = $('#spk-labels'); if(sl) sl.checked = cfg.speaker_labels !== false; }
  { const bt = $('#builtin-terms'); if(bt) bt.checked = cfg.builtin_terms !== false; }
  { const hw = $('#hotwords');
    if(hw){ hw.value = (cfg.beta && cfg.beta.hotwords) || ''; } }
  renderBuiltinTerms(); renderHotwordCount();
  fillVoiceSelects();
  { const e = $('#voice-in-s');  if(e) e.value = cfg.voice_gender_incoming || 'auto'; }
  { const e = $('#voice-out-s'); if(e) e.value = cfg.voice_gender_outgoing || 'auto'; }
  renderVoiceChoiceHints();
  { const mi = $('#allow-multiple-instances'); if(mi) mi.checked = !!cfg.allow_multiple_instances; }
  { const mo = $('#monitor-outgoing'); if(mo) mo.checked = !!cfg.monitor_outgoing_translation; }
  // Badge removal is a paid perk: only an official build with a paid subscription
  // may turn it off. Everyone else (free official + OSS) gets a locked, forced-on
  // toggle with a "subscription required" tooltip on hover.
  const badgeRemovable = !!STATE.badge_removable;
  $('#brandbadge').checked  = badgeRemovable ? (cfg.branding_badge_enabled !== false) : true;
  $('#brandbadge').disabled = !badgeRemovable;
  { const sw = $('#brandbadge').closest('.switch'); if(sw) sw.title = badgeRemovable ? '' : T('brand_badge_locked'); }
  { const up = $('#badge-upgrade'); if(up){ up.style.display = (badgeRemovable || !STATE.official_release) ? 'none' : 'inline';
      up.textContent = T('badge_upgrade');
      up.onclick = ()=>{ try{api().open_url('https://voxislive.com/pricing');}catch(_){} }; } }
  $('#uilang').value    = cfg.ui_language || LANG;
  document.querySelectorAll('.k').forEach(k=>k.textContent=cfg.hotkeys[k.dataset.hk]||'—');
  updateTileTitles();
  // Official-release builds always run on the SaaS key — hide the BYOK input
  // entirely so the end-user UI never exposes a key field. Open-source builds
  // continue to expose it for developers.
  const byokSection = $('#byok-section');
  if(STATE.official_release){
    if(byokSection) byokSection.style.display = 'none';
    $('#gemkey').disabled = true;
    $('#logoutbtn').style.display = '';
    $('#manageplanbtn').style.display = '';
    // Referral invite — SaaS-only (referral is a server-account concept); opens the
    // account Refer & earn panel in the browser.
    { const ib=$('#invitebtn'); if(ib) ib.style.display=''; }
    // Store-delivered build: offer a shortcut to the listing (updates come via Store).
    { const sb=$('#storebtn'); if(sb) sb.style.display=''; }
    // Problem reporting is official-build only (the OSS build hard-gates the
    // network call, so the button would never succeed there). Surface it both in
    // the top bar (primary, always visible) and the About tab (secondary).
    { const rb=$('#reportbtn'); if(rb) rb.style.display=''; }
    { const rbt=$('#reportbtn-top'); if(rbt) rbt.style.display=''; }
  } else {
    const st = STATE.byok_status || {gemini: STATE.byok_set};
    $('#byok-badge').style.display = st.gemini ? 'inline' : 'none';
    $('#gemkey').value = '';
    $('#logoutbtn').style.display = 'none';
    bindByokHandlers();
  }
  // First-run onboarding once the app is ready (gated by the bridge flag).
  // A returning user gets the release notes instead — never both, and the bridge
  // decides which by looking at whether onboarding was ever completed.
  if(!STATE.onboarding_done) openOnboard();
  else maybeWhatsNew();
  poll();
}
/* ---------- kontroller ---------- */
const duck=$('#duck'), vol=$('#vol');
// Coalesce config writes while a slider is being dragged: the % label tracks
// the thumb with zero lag, but set_cfg (which persists to disk) only fires once
// the user pauses. Without this, a single drag fired dozens of disk writes.
function debounce(fn, ms){ let h; return (...a)=>{ clearTimeout(h); h=setTimeout(()=>fn(...a), ms); }; }
const saveDuck = debounce(v=>api().set_cfg('duck_gain', v), 180);
const saveVol  = debounce(v=>api().set_cfg('tts_volume', v), 180);
duck.oninput=()=>{updRange(duck,'duckv'); saveDuck(duck.value/100)};
vol.oninput =()=>{updRange(vol,'volv');   saveVol(vol.value/100)};
$('#hear').onchange   = e=>{
  if(STATE.cfg) STATE.cfg.target_language_incoming = e.target.value;
  renderVoiceHint(); renderVoiceChoiceHints();
  return api().set_cfg('target_language_incoming', e.target.value);
};
$('#send').onchange   = e=>{
  if(STATE.cfg) STATE.cfg.target_language_outgoing = e.target.value;
  renderVoiceChoiceHints();
  return api().set_cfg('target_language_outgoing', e.target.value);
};
$('#langswap').onclick = async()=>{
  const b=$('#langswap'); b.disabled=true;
  try{
    const r=await api().swap_languages();
    if(r && r.ok!==false){
      $('#hear').value=r.incoming; $('#send').value=r.outgoing;
      if(STATE.cfg){
        STATE.cfg.target_language_incoming=r.incoming;
        STATE.cfg.target_language_outgoing=r.outgoing;
      }
      renderVoiceHint(); renderVoiceChoiceHints();
    }
  }finally{ b.disabled=false; }
};
$('#profile').onchange= e=>api().set_profile(e.target.value).then(refreshFromCfg);
$('#out').onchange    = e=>api().set_device('output', e.target.value);
$('#mic').onchange    = e=>api().set_device('mic', e.target.value);
$('#subs').onchange   = e=>api().set_cfg('show_subtitles', e.target.checked);
$('#obs').onchange    = e=>api().set_cfg('obs_subtitle_enabled', e.target.checked);
{ const ra = $('#record-audio'); if(ra) ra.onchange = e=>api().set_cfg('record_audio', e.target.checked); }
{ const e = $('#auto-export-txt'); if(e) e.onchange = ev=>api().set_cfg('auto_export_txt', ev.target.checked); }
{ const e = $('#auto-export-srt'); if(e) e.onchange = ev=>api().set_cfg('auto_export_srt', ev.target.checked); }
{ const e = $('#auto-export-vtt'); if(e) e.onchange = ev=>api().set_cfg('auto_export_vtt', ev.target.checked); }
{ const sl = $('#spk-labels'); if(sl) sl.onchange = e=>api().set_cfg('speaker_labels', e.target.checked); }
{ const hw = $('#hotwords');
  if(hw){
    hw.oninput = renderHotwordCount;
    // Saved on blur, not per keystroke: this setting restarts a running
    // session, which must not happen between two letters of a word.
    hw.onchange = e=>{ api().set_hotwords(e.target.value); renderHotwordCount(); syncHotwordCount(); };
  } }
{ const bt = $('#builtin-terms');
  if(bt) bt.onchange = e=>{ if(STATE.cfg) STATE.cfg.builtin_terms = e.target.checked;
                            api().set_cfg('builtin_terms', e.target.checked);
                            renderHotwordCount(); syncHotwordCount(); }; }
{ const tg = $('#builtin-terms-toggle');
  if(tg) tg.onclick = ()=>{
    const box=$('#builtin-terms-list'); if(!box) return;
    const show = box.style.display==='none';
    box.style.display = show ? '' : 'none';
    tg.textContent = T(show ? 'terms_hide' : 'terms_show');
    tg.dataset.i18n = show ? 'terms_hide' : 'terms_show';
  }; }
// Writes through the validated bridge door (set_voice_gender), which restarts a
// live session because the voice is chosen during the session handshake.
function bindVoiceGender(sel, leg){
  const el=$(sel); if(!el) return;
  el.onchange = e=>{
    const v=e.target.value;
    if(STATE.cfg) STATE.cfg['voice_gender_'+leg] = v;
    return api().set_voice_gender(leg, v);
  };
}
bindVoiceGender('#voice-in-s','incoming');
bindVoiceGender('#voice-out-s','outgoing');
{ const mi = $('#allow-multiple-instances'); if(mi) mi.onchange = e=>api().set_cfg('allow_multiple_instances', e.target.checked); }
{ const mo = $('#monitor-outgoing'); if(mo) mo.onchange = e=>api().set_cfg('monitor_outgoing_translation', e.target.checked); }
$('#brandbadge').onchange = e=>api().set_cfg('branding_badge_enabled', e.target.checked);
$('#overlay').onchange= e=>api().toggle_overlay(e.target.checked);
$('#uilang').onchange = e=>{ applyI18n(e.target.value); try{api().set_cfg('ui_language', e.target.value);}catch(_){} };
async function refreshFromCfg(){
  const c = await api().get_cfg();
  duck.value = Math.round(c.duck_gain*100); updRange(duck,'duckv');
}
document.querySelectorAll('.scenario').forEach(b=>{
  b.addEventListener('pointermove',e=>{const r=b.getBoundingClientRect();b.style.setProperty('--mx',(e.clientX-r.left)+'px');b.style.setProperty('--my',(e.clientY-r.top)+'px');});
  // Preview which controls this scenario would leave inert, before it's even
  // picked -- "Karşı tarafın dili" only ever feeds Meeting, so dim it on a
  // Video/Game hover/focus. Skipped once a session is live: poll() (see
  // p.mode==='video' below) already owns the dim state then, and fighting it
  // on mouseleave would flicker the field back to full opacity mid-session.
  const previewSend=(on)=>{
    if(SESSION_LIVE) return;
    previewSendDim = on && b.dataset.mode==='video';
    applySendDim(previewSendDim);
  };
  b.addEventListener('mouseenter',()=>previewSend(true));
  b.addEventListener('mouseleave',()=>previewSend(false));
  b.addEventListener('focus',()=>previewSend(true));
  b.addEventListener('blur',()=>previewSend(false));
  b.onclick=async()=>{
    if(b.dataset.quotaBlocked==='1'){ rejectQuota(b); return; }
    const mode=b.dataset.mode;
    // Meeting is paid-only once the taste is spent, and the reason is quality,
    // not greed: in Meeting the OTHER person hears the synthetic voice speaking
    // as you. The free tier's local voice must never be sent to someone else.
    if(mode==='meeting' && tasteSpent(QUOTA)){ openMeetingLock(); return; }
    if(mode==='meeting'){
      // Meeting routes your translated voice through a virtual microphone; without
      // a virtual cable installed the two-way path cannot work. Gate on it first.
      let hasCable=true;
      try{ hasCable = await api().meeting_cable_available(); }catch(_){}
      if(!hasCable){ openCable(); return; }
      // Two-way (your voice is sent to the other party) also needs an explicit
      // consent acknowledgement the first time, unless the user opted out.
      if(!(STATE.cfg && STATE.cfg.meeting_consent_ack)){ openConsent(); return; }
    }
    invokeStart(mode);
  };
});
$('#stopbtn').onclick = ()=>api().stop();
async function saveTranscript(){
  let r=null; try{ r=await api().save_txt(); }catch(_){}
  if(r && r.ok && r.file) addTranscriptActions(r.file);
}
$('#savechip').onclick = saveTranscript;
$('#soundcheckbtn').onclick = ()=>{ if(!SESSION_LIVE) openSoundcheck(); };
$('#sc-close').onclick = closeSoundcheck;
$('#clearstream').onclick = ()=>resetTranscript();
/* ---------- transcript folder (Settings › General) ---------- */
async function refreshTxDir(){
  const el=$('#tx-dir-path'); if(!el) return;
  try{ const c=await api().get_cfg(); el.textContent=(c && c.transcript_dir_display) || ''; }catch(_){}
}
{
  const b=$('#tx-dir-browse'); if(b) b.onclick=async()=>{ try{ const r=await api().choose_transcript_dir(); if(r && r.ok) refreshTxDir(); }catch(_){}};
  const o=$('#tx-dir-open'); if(o) o.onclick=()=>{ try{api().open_transcript_folder();}catch(_){}};
  const rs=$('#tx-dir-reset'); if(rs) rs.onclick=async e=>{ e.preventDefault(); try{ await api().reset_transcript_dir(); refreshTxDir(); }catch(_){}};
}
{ const hf=$('#hist-open-folder'); if(hf) hf.onclick=()=>{ try{api().open_transcript_folder();}catch(_){}}; }
/* ---------- pencere + çekmece ---------- */
$('#win-min').onclick   = ()=>{ try{api().win_minimize();}catch(e){} };
// The bridge toggles maximize/restore; track the state client-side so the glyph
// and label reflect what the button will do next.
const MAX_GLYPH='<rect x="2" y="2" width="7" height="7" rx="1.2"/>';
const RESTORE_GLYPH='<rect x="3.4" y="3.4" width="5.6" height="5.6" rx="1.1"/><path d="M3.4 3.4V2.2A1 1 0 0 1 4.4 1.2h4.4"/>';
let winMaxed=false;
function applyWinMaxUI(){
  const btn=$('#win-max'); const svg=btn.querySelector('svg');
  svg.innerHTML = winMaxed ? RESTORE_GLYPH : MAX_GLYPH;
  const label = winMaxed ? T('title_restore') : T('title_max');
  btn.title=label; btn.setAttribute('aria-label', label);
  btn.dataset.i18nTitle = winMaxed ? 'title_restore' : 'title_max';
  btn.dataset.i18nAria  = winMaxed ? 'title_restore' : 'title_max';
}
$('#win-max').onclick   = ()=>{ try{api().win_toggle_max();}catch(e){} winMaxed=!winMaxed; applyWinMaxUI(); document.body.classList.toggle('win-maximized', winMaxed); };
$('#win-close').onclick = ()=>{ try{api().win_close();}catch(e){} };
$('#auth-win-min').onclick   = ()=>{ try{api().win_minimize();}catch(e){} };
$('#auth-win-close').onclick = ()=>{ try{api().win_close();}catch(e){} };
/* ---------- modal focus management (drawer, consent, onboarding, auth) ----- */
const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
// Modal STACK: a nested modal (e.g. topbar History/Privacy opened over the
// Settings drawer) must not blow away the parent's focus-trap/Escape on close.
// The top entry owns the trap, Escape and scrim; activeModal/modalOnEsc/
// modalReturnFocus mirror that top so existing references keep working.
let activeModal=null, modalReturnFocus=null, modalOnEsc=null;
const modalStack=[];
function syncModalTop(){
  const top=modalStack[modalStack.length-1]||null;
  activeModal      = top ? top.el : null;
  modalOnEsc       = top ? top.onEsc : null;
  modalReturnFocus = top ? top.returnFocus : null;
}
function trapTab(e){
  if(e.key!=='Tab' || !activeModal) return;
  const f=[...activeModal.querySelectorAll(FOCUSABLE)].filter(el=>el.offsetParent!==null || el===document.activeElement);
  if(!f.length) return;
  const first=f[0], last=f[f.length-1];
  if(e.shiftKey && document.activeElement===first){ e.preventDefault(); last.focus(); }
  else if(!e.shiftKey && document.activeElement===last){ e.preventDefault(); first.focus(); }
}
function openModal(el, onEsc, returnTo){
  modalStack.push({el, onEsc:onEsc||null, returnFocus:returnTo||document.activeElement});
  syncModalTop();
  const first=el.querySelector(FOCUSABLE); if(first) try{ first.focus(); }catch(_){}
}
function closeModal(){
  const top=modalStack.pop();
  syncModalTop();                       // restore the parent modal's trap/Esc, if any
  const ret=top ? top.returnFocus : null;
  if(ret) try{ ret.focus(); }catch(_){}
}
document.addEventListener('keydown', e=>{
  if(e.key==='Escape' && activeModal && modalOnEsc){ modalOnEsc(); }
  else trapTab(e);
});
function openDrawer(){ $('#scrim').classList.add('open'); $('#drawer').classList.add('open'); localizeSettings(); renderMembership(); refreshTxDir(); syncHotwordCount(); switchSettingsTab('general'); openModal($('#drawer'), closeDrawer, $('#gear')); }
function closeDrawer(){ $('#scrim').classList.remove('open'); $('#drawer').classList.remove('open'); closeModal(); }
// Settings tabs (Genel / Kısayollar / Üyelik / Hakkında)
function switchSettingsTab(pane){
  document.querySelectorAll('#drawer .dtab').forEach(b=>{
    const on = b.dataset.pane===pane;
    b.classList.toggle('active', on); b.setAttribute('aria-selected', on?'true':'false');
  });
  document.querySelectorAll('#drawer .dpane').forEach(p=>{ p.hidden = (p.dataset.pane!==pane); });
}
document.querySelectorAll('#drawer .dtab').forEach(b=>{
  b.onclick = ()=>{ switchSettingsTab(b.dataset.pane); if(b.dataset.pane==='membership') renderMembership(); };
});
// New-string localization (TR/EN; EN fallback for other UI languages) + About fields.
function localizeSettings(){
  const set=(id,t)=>{ const el=document.getElementById(id); if(el) el.textContent=t; };
  const ver = (STATE && STATE.version) ? ('v'+STATE.version) : '';
  const chMap = {store:'Microsoft Store', desktop:'Desktop', extension:'Extension'};
  const ch = (STATE && STATE.channel) ? (chMap[STATE.channel]||STATE.channel) : '';
  set('about-ver', [ver, ch].filter(Boolean).join(' · '));
  set('about-copy', '© '+(new Date().getFullYear())+' Voxis · voxislive.com');
}
// About links → system browser.
(function(){
  // al-credits: the free-tier voices are mostly CC0, but ~12 are CC-BY/CC-BY-SA
  // and those permit commercial use ONLY with credit. CC BY 4.0 §3(a)(2) lets a
  // hyperlink carry the attribution, so this link is what makes the licence hold.
  const L={'al-site':'https://voxislive.com','al-pricing':'https://voxislive.com/pricing','al-terms':'https://voxislive.com/terms','al-privacy':'https://voxislive.com/privacy','al-contact':'https://voxislive.com/contact','al-credits':'https://voxislive.com/voice-credits'};
  Object.keys(L).forEach(id=>{ const el=document.getElementById(id); if(el) el.onclick=(e)=>{ e.preventDefault(); try{api().open_url(L[id]);}catch(_){} }; });
})();
// Membership pane: current plan + quota + upgrade tiers (official build) or BYOK note (dev build).
function renderMembership(){
  const box = $('#membership-body'); if(!box) return;
  const official = !!(STATE && STATE.official_release);
  if(!official){
    box.innerHTML = '<div class="planbox"><div class="pcur"><span class="ptier">'+T('mem_dev_byok')+'</span><span class="ppill">'+T('mem_your_key')+'</span></div>'
      + '<div class="pquotmeta">'+T('mem_byok_note')+'</div></div>';
    return;
  }
  const q = QUOTA || {};
  const tier = String(q.tier || q.plan || (q.unlimited?'pro':'free')).toLowerCase();
  const tierName = ({free:'Free', creator:'Creator', pro:'Pro', enterprise:'Enterprise'})[tier] || (tier.charAt(0).toUpperCase()+tier.slice(1));
  let quotaLine;
  if(q.unlimited){ quotaLine = T('mem_unlimited'); }
  else if(tasteSpent(q)){
    // Past the taste there is no monthly balance to report — "0/15 min left" is a
    // true sentence that tells the user nothing and reads like a dead end. What
    // they actually have is TODAY's free minutes, so say that.
    quotaLine = T('free_left_today')
      .replace('{n}', String(freeLeftToday(q)))
      .replace('{m}', String(Math.round(freeDailyMinutes(q))));
  }
  else {
    const allowed=q.allowed_minutes||0, used=q.used_minutes||0, rem=(q.remaining!=null?q.remaining:Math.max(0,allowed-used));
    quotaLine = T('mem_this_month')+Math.round(rem)+'/'+Math.round(allowed)+T('min_left');
  }
  // The journey, permanently. The three rungs were explained exactly once — in a
  // modal, on first sign-in, never reachable again — so a returning free user had
  // no way to find out why the voice changed or what happens tomorrow (owner
  // report, 2026-07-13). Settings is where someone goes to ask that question.
  const ladder = !isTasteTier(q) ? '' :
    '<div class="planbox" style="margin-top:10px">'
    + '<div class="pcur"><span class="ptier">'+T('ladder_title')+'</span></div>'
    + '<ul class="ladder" style="margin-top:10px">'
    + '<li class="rung'+(tasteSpent(q)?'':' now')+'"><span class="rn">1</span><span>'+T('ladder_pro')+'</span></li>'
    + '<li class="rung'+(tasteSpent(q)?' now':'')+'"><span class="rn">2</span><span>'+T('ladder_free')+'</span></li>'
    + '<li class="rung"><span class="rn">3</span><span>'+T('ladder_paid')+'</span></li>'
    + '</ul></div>';
  // Voxis dropped monthly Creator/Pro subscriptions for prepaid minute
  // packages (2026-07-01) — pricing now lives on the website (5 packages ×
  // currency, promos included) so it isn't duplicated and re-staled here.
  box.innerHTML =
    '<div class="planbox"><div class="pcur"><span class="ptier">'+tierName+'</span><span class="ppill">'+T('mem_active_plan')+'</span></div>'
    + '<div class="pquotmeta">'+quotaLine+'</div></div>'
    + ladder
    + '<div class="planbox" style="margin-top:10px">'
    + '<div class="pcur"><span class="ptier">'+T('mem_buy_title')+'</span></div>'
    + '<div class="pquotmeta" style="margin-top:6px">'+T('mem_buy_body')+'</div>'
    + '<button class="btn btn-primary buy-minutes" style="width:100%;margin-top:12px">'+T('mem_see_pricing')+'</button>'
    + '</div>';
  box.querySelector('.buy-minutes').onclick = ()=>{ try{api().open_url('https://voxislive.com/pricing');}catch(_){} };
}
$('#gear').onclick = openDrawer;
$('#closedrawer').onclick = closeDrawer;
// Backdrop click dismisses whichever modal currently owns the scrim.
$('#scrim').onclick = ()=>{ if(modalOnEsc) modalOnEsc(); else closeDrawer(); };
/* ---------- consent + onboarding modals ---------- */
function openConsent(){ $('#scrim').classList.add('open'); $('#consent-modal').classList.add('open'); openModal($('#consent-modal'), closeConsent, $('#m-meeting')); }
function closeConsent(){ $('#consent-modal').classList.remove('open'); if(!$('#drawer').classList.contains('open')) $('#scrim').classList.remove('open'); closeModal(); }
// Free-limit paywall card (SaaS only — OSS builds never hit a server quota wall).
let SESSION_LIVE=false, limitShown=false, warn80Shown=false, sessionT0=0;
// Idle-state hover/focus preview of "Karşı tarafın dili" going inert on a
// Video/Game scenario. poll() also drives this class (from the LIVE session's
// mode) every 70-250ms, so it must OR this in rather than the hover handler
// setting the class directly -- otherwise the next poll tick clobbers it back
// to off mid-hover (looked like the dim flashing then reverting).
let previewSendDim=false;
// The explanatory line under "Karşı tarafın dili" is now always visible (see
// the fieldhint markup) rather than appearing only on hover -- a user could
// otherwise read "soluk" (dimmed) as merely "less important" and still guess
// it should hold the video's own language. This just adds the extra opacity
// cue on top, for a Video/Game hover/focus or a live Video/Game session.
function applySendDim(on){
  $('#send-item').classList.toggle('lang-dim', on);
}
/* ---------- sound check ("do I hear this device?") ---------- */
let scOpen=false, scHeard=false, scMicHeard=false, scOutputTimer=null;
function openSoundcheck(){
  api().soundcheck_start().then(r=>{
    scOpen=true; scHeard=false; scMicHeard=false;
    $('#sc-fill').style.width='0%';
    $('#sc-output-fill').style.width='0%';
    $('#sc-mic-fill').style.width='0%';
    $('#sc-tone').disabled=false;
    const st=$('#sc-status'), ost=$('#sc-output-status'), mst=$('#sc-mic-status');
    st.classList.remove('ok','err'); ost.classList.remove('ok','err'); mst.classList.remove('ok','err');
    ost.textContent=T('sound_check_output_wait');
    if(r && r.system_ok===false){ st.textContent=T('sound_check_fail'); st.classList.add('err'); }
    else { st.textContent=T('sound_check_wait'); }
    if(r && r.mic_ok===false){ mst.textContent=T('sound_check_fail'); mst.classList.add('err'); }
    else { mst.textContent=T('sound_check_wait'); }
    $('#scrim').classList.add('open'); $('#soundcheck-modal').classList.add('open');
    openModal($('#soundcheck-modal'), closeSoundcheck, $('#soundcheckbtn'));
  });
}
$('#sc-tone').onclick = async()=>{
  const b=$('#sc-tone'), fill=$('#sc-output-fill'), st=$('#sc-output-status');
  b.disabled=true; clearTimeout(scOutputTimer);
  st.classList.remove('ok','err'); st.textContent=T('sound_check_output_wait');
  fill.style.width='0%'; requestAnimationFrame(()=>{ fill.style.width='82%'; });
  try{
    const r=await api().soundcheck_play_tone();
    if(r && r.ok===false){
      fill.style.width='0%'; st.textContent=T('sound_check_fail'); st.classList.add('err');
    }else{ st.textContent=T('sound_check_sent'); st.classList.add('ok'); }
  }catch(_){
    fill.style.width='0%'; st.textContent=T('sound_check_fail'); st.classList.add('err');
  }finally{
    scOutputTimer=setTimeout(()=>{ fill.style.width='0%'; b.disabled=false; }, 550);
  }
};
function closeSoundcheck(){
  scOpen=false;
  clearTimeout(scOutputTimer); $('#sc-output-fill').style.width='0%'; $('#sc-tone').disabled=false;
  try{ api().soundcheck_stop(); }catch(_){}
  $('#soundcheck-modal').classList.remove('open');
  if(!$('#drawer').classList.contains('open')) $('#scrim').classList.remove('open');
  closeModal();
}
function driveSoundcheck(level, micLevel){
  if(typeof level==='number'){
    $('#sc-fill').style.width=Math.min(100, Math.round(level*130))+'%';
    if(!scHeard && level>0.05){
      scHeard=true;
      const st=$('#sc-status'); st.textContent=T('sound_check_ok'); st.classList.add('ok');
    }
  }
  if(typeof micLevel==='number'){
    $('#sc-mic-fill').style.width=Math.min(100, Math.round(micLevel*130))+'%';
    if(!scMicHeard && micLevel>0.05){
      scMicHeard=true;
      const st=$('#sc-mic-status'); st.textContent=T('sound_check_ok'); st.classList.add('ok');
    }
  }
}
function openLimitModal(){ $('#scrim').classList.add('open'); $('#limit-modal').classList.add('open'); openModal($('#limit-modal'), closeLimitModal, null); }
function closeLimitModal(){ $('#limit-modal').classList.remove('open'); if(!$('#drawer').classList.contains('open')) $('#scrim').classList.remove('open'); closeModal(); }
function showPaywallCard(){
  if(limitShown) return; limitShown=true;   // once per session; re-armed on session start
  const cap = (QUOTA && QUOTA.allowed_minutes) ? Math.round(QUOTA.allowed_minutes) : 15;
  const el=$('#limit-min'); if(el) el.textContent=String(cap);
  openLimitModal();
}
/* Release notes: ask the bridge whether anything is pending (it owns the
   seen-version bookkeeping and the language fallback), render, and mark seen only
   when the card is actually shown — a bridge hiccup must not burn the version. */
async function maybeWhatsNew(){
  let wn=null;
  try{ wn = await api().whatsnew(); }catch(_){ return; }
  // entries = one block per version the user hasn't read, newest first. A Store
  // update can skip several releases at once, and showing only the running
  // version's notes made every release in between invisible.
  const entries = (wn && Array.isArray(wn.entries) ? wn.entries : [])
    .filter(e => e && Array.isArray(e.bullets) && e.bullets.length);
  if(!entries.length) return;
  const body=$('#whatsnew-body'); if(!body) return;
  body.innerHTML='';
  entries.forEach(e=>{
    const g=document.createElement('div'); g.className='wn-group';
    // The version label only earns its space when there is more than one block;
    // for a single version the header chip already says which one it is.
    if(entries.length>1){
      const h=document.createElement('div'); h.className='wn-ver';
      h.textContent=T('wn_ver').replace('{v}', e.version||''); g.appendChild(h);
    }
    const ul=document.createElement('ul'); ul.style.margin='0'; ul.style.paddingLeft='18px';
    e.bullets.forEach(b=>{ const li=document.createElement('li');
                           li.style.marginBottom='8px'; li.textContent=b; ul.appendChild(li); });
    g.appendChild(ul); body.appendChild(g);
  });
  const ver=$('#whatsnew-ver');
  if(ver) ver.textContent = T('wn_ver').replace('{v}', (wn && wn.version) || entries[0].version || '');
  $('#scrim').classList.add('open'); $('#whatsnew-modal').classList.add('open');
  openModal($('#whatsnew-modal'), closeWhatsNew, null);
  try{ api().mark_whatsnew_seen(); }catch(_){}
}
function closeWhatsNew(){ $('#whatsnew-modal').classList.remove('open'); if(!$('#drawer').classList.contains('open')) $('#scrim').classList.remove('open'); closeModal(); }
{ const ok=$('#whatsnew-ok'); if(ok) ok.onclick = closeWhatsNew; }
/* The card only carries what THIS user missed; the site page is the full history,
   for someone who skipped further back than the table goes. The site is published
   in 7 languages (fewer than the app's 23) and Turkish uses localized slugs, so
   anything else falls back to the English page rather than a 404. */
const CHANGELOG_PATHS = {en:"/changelog", de:"/de/changelog", es:"/es/changelog",
                         fr:"/fr/changelog", ko:"/ko/changelog", pt:"/pt/changelog",
                         tr:"/tr/degisiklikler"};
function changelogUrl(){
  return "https://voxislive.com" + (CHANGELOG_PATHS[LANG] || CHANGELOG_PATHS.en);
}
{ const a=$('#whatsnew-all');
  if(a) a.onclick = e => { e.preventDefault(); try{ api().open_url(changelogUrl()); }catch(_){} }; }
function closeReviewModal(){ $('#review-modal').classList.remove('open'); if(!$('#drawer').classList.contains('open')) $('#scrim').classList.remove('open'); closeModal(); }
function showReviewCard(){
  // Python decides WHEN (third clean session, Store build, asked once ever) and
  // has already persisted that it asked — so this only has to render.
  $('#scrim').classList.add('open'); $('#review-modal').classList.add('open');
  openModal($('#review-modal'), closeReviewModal, null);
}
/* ── FREE-TIER JOURNEY: taste chip · three-rung ladder · inverse demo ──────
   The whole point of these three: a user must never reach the wall without
   having (a) known they were on the paid voice, (b) known what replaces it,
   and (c) HEARD the difference while it was still reversible. */
function isTasteTier(q){
  // The taste is a FREE-tier state: a paying user is not tasting anything.
  // Fails CLOSED on an unknown/absent tier — telling a paying customer their
  // voice is about to be taken away is a far worse error than staying quiet.
  if(!STATE.official_release || !q || q.unlimited) return false;
  if(String(q.tier || q.plan || '').toLowerCase() !== 'free') return false;
  // And ONLY once the server says the free tier actually exists (cascade_ready).
  // Everything downstream of this — the countdown, the ladder, the inverse demo,
  // the Meeting lock — promises a free voice after the taste. Ship that promise
  // before the server can keep it and the user hits the OLD wall instead, having
  // been told twice that something else was coming. So the whole journey lights
  // up server-side, the day the switch is thrown, with no new build.
  return q.cascade_ready === true;
}
// Has the one-time Pro taste been spent? That is the whole difference between a
// first-month user and a second-month one, and today the app said NOTHING about
// it — the returning user just found a robot voice and no explanation.
function tasteSpent(q){
  if(!isTasteTier(q)) return false;
  const rem = q.remaining ?? Math.max(0, (q.allowed_minutes||0) - (q.used_minutes||0));
  return rem <= 0;
}
function freeDailyMinutes(q){ return (q && q.cascade_daily_minutes) || 10; }
// Minutes left in TODAY's free allowance. The server now sends this on every
// quota refresh (~6 s); before, it only ever sent the ALLOWANCE, so the app could
// print "10 min/day" but never "you have 4 left" — and a user could not tell how
// close they were to the daily wall until they hit it (owner report, 2026-07-13).
// Old server / missing field → fall back to the full allowance rather than 0, so
// a stale backend never claims the day is spent when it is not.
function freeLeftToday(q){
  const left = q && q.cascade_remaining_today;
  const n = (typeof left === 'number') ? left : freeDailyMinutes(q);
  return Math.max(0, Math.round(n));
}
// Is the free tier usable RIGHT NOW (vs. merely existing)? cascade_ready says the
// license HAS a free tier; cascade_available says today's minutes are not gone.
// Gating a Start on the former invites a start the server then refuses with a 402.
function freeAvailableNow(q){
  if(!q) return false;
  if(typeof q.cascade_available === 'boolean') return q.cascade_available;
  return q.cascade_ready === true;   // server predates the field
}
function renderTasteChip(q){
  const chip = $('#taste-chip'); if(!chip) return;
  if(!isTasteTier(q)){ chip.style.display='none'; chip.classList.remove('free'); return; }
  const allowed = q.allowed_minutes || 0;
  const rem = q.remaining ?? Math.max(0, allowed - (q.used_minutes||0));
  chip.style.display='inline-flex';
  if(rem <= 0){
    // The free tier's own chip: quiet, permanent, and the only thing in the UI
    // that explains why the voice sounds the way it does — plus the way back.
    chip.classList.add('free'); chip.classList.remove('low');
    const left = freeLeftToday(q), cap = Math.round(freeDailyMinutes(q));
    chip.classList.toggle('low', left <= 2);
    $('#taste-pro').textContent   = T('free_voice_label');
    // Today's BALANCE, not the allowance. "10 min/day" never changed, so it read
    // as a slogan; "3 / 10 min left today" is the number the user actually needs.
    $('#taste-count').textContent = T('free_left_today')
      .replace('{n}', String(left)).replace('{m}', String(cap));
    $('#taste-next').textContent  = T('free_back_to_pro');
    chip.title = T('free_chip_tip');
    return;
  }
  chip.classList.remove('free');
  chip.classList.toggle('low', rem <= 3);
  $('#taste-pro').textContent  = T('taste_pro');
  $('#taste-count').textContent= Math.max(1, Math.round(rem)) + T('min_left');
  $('#taste-next').textContent = T('taste_next');
  chip.title = T('taste_tip');
}
// The free chip is also the way back — clicking it is the cheapest possible
// upgrade path for someone who already misses the voice.
$('#taste-chip').onclick = () => {
  if($('#taste-chip').classList.contains('free')){
    try{ api().open_url(PACKS_URL); }catch(_){}
  }
};
function closeLadder(){ $('#ladder-modal').classList.remove('open'); if(!$('#drawer').classList.contains('open')) $('#scrim').classList.remove('open'); closeModal(); }
function maybeShowLadder(q){
  // Once, on a free user's first sign-in — BEFORE the minutes start burning.
  if(!isTasteTier(q) || (STATE.cfg && STATE.cfg.ladder_seen)) return;
  if(STATE.cfg) STATE.cfg.ladder_seen = true;
  try{ api().mark_seen('ladder_seen'); }catch(_){}
  $('#scrim').classList.add('open'); $('#ladder-modal').classList.add('open');
  openModal($('#ladder-modal'), closeLadder, null);
}
$('#ladder-ok').onclick = e => { e.preventDefault(); closeLadder(); };
const CONTRAST_AFTER_MS = 120000;   // let them settle into the content first
let contrastArmed=false, contrastLines=0, contrastHeard=false;
function hideContrast(){ const c=$('#contrast-card'); if(c) c.style.display='none'; }
function contrastEligible(){
  // Free tier · never asked before · Voxis has actually produced a line worth
  // replaying. Asking before it works would demo silence. And never while the
  // taste wall is up — the wall carries its own comparison; two cards pitching
  // at once reads as a popup storm.
  if($('#taste-wall-modal').classList.contains('open')) return false;
  if($('#device-block-modal').classList.contains('open')) return false;
  if(contrastArmed || !isTasteTier(QUOTA)) return false;
  if(STATE.cfg && STATE.cfg.contrast_shown) return false;
  return contrastLines >= 1;
}
function ccStatus(key){
  const s=$('#contrast-status'); if(!s) return;
  if(!key){ s.style.display='none'; s.textContent=''; return; }
  s.style.display=''; s.textContent=T(key);
}
function offerContrast(){
  if(!contrastEligible()) return;
  contrastArmed = true; contrastHeard = false;
  if(STATE.cfg) STATE.cfg.contrast_shown = true;
  try{ api().mark_seen('contrast_shown'); }catch(_){}   // asked = spent, even if dismissed
  const c=$('#contrast-card'); if(!c) return;
  c.classList.remove('busy');
  ccStatus(null);
  $('#contrast-title').textContent = T('contrast_title');
  $('#contrast-body').textContent  = T('contrast_body');
  $('#contrast-cta').style.display = '';
  $('#contrast-ab').style.display  = 'none';
  $('#contrast-upgrade').style.display = 'none';
  c.style.display='flex';
}
function maybeOfferContrast(){
  // The card is useless behind a fullscreen film. Someone who set Voxis up and
  // went to watch is NOT looking at this window — so mid-session we only ask
  // when the window actually has focus, and otherwise wait for the moment they
  // come back to press Stop. An offer nobody sees is an offer spent.
  if(!SESSION_LIVE || (Date.now() - sessionT0) < CONTRAST_AFTER_MS) return;
  if(!document.hasFocus()) return;
  offerContrast();
}
$('#contrast-dismiss').onclick = e => { e.preventDefault(); hideContrast(); };
async function playFreeVoice(btn){
  $('#contrast-card').classList.add('busy');
  document.querySelectorAll('.ccbtn').forEach(b=>b.classList.remove('playing'));
  if(btn) btn.classList.add('playing');
  ccStatus('contrast_loading');
  try{
    const r = await api().free_voice_preview();
    if(r && r.ok === false) onPreviewEvent({state:'error', code:r.code});
  }catch(_){ onPreviewEvent({state:'error', code:'failed'}); }
}
$('#contrast-cta').onclick  = e => { e.preventDefault(); playFreeVoice(null); };
$('#contrast-free').onclick = e => { e.preventDefault(); playFreeVoice($('#contrast-free')); };
// Replay the paid voice, so the two sit back to back in the ear — in either
// direction, as many times as it takes. A one-shot demo helps nobody who missed it.
$('#contrast-pro').onclick = async e => {
  e.preventDefault();
  $('#contrast-card').classList.add('busy');
  document.querySelectorAll('.ccbtn').forEach(b=>b.classList.remove('playing'));
  $('#contrast-pro').classList.add('playing');
  ccStatus('contrast_loading');
  try{
    const r = await api().pro_voice_replay();
    if(r && r.ok === false) onPreviewEvent({state:'error', code:r.code});
  }catch(_){ onPreviewEvent({state:'error', code:'failed'}); }
};
$('#contrast-upgrade').onclick = e => { e.preventDefault(); try{ api().open_url(PACKS_URL); }catch(_){} };
// Once they have HEARD the free voice, the card stops being an offer and becomes
// the pitch: the paid voice is back (they lost nothing), both voices stay one
// click apart, and here is how to keep the good one. This is the freshest the
// contrast will ever be, and the highest-intent moment of the whole taste.
function contrastToPitch(){
  contrastHeard = true;
  $('#contrast-title').textContent = T('contrast_back_title');
  $('#contrast-body').textContent  = T('contrast_back_body');
  $('#contrast-cta').style.display = 'none';
  $('#contrast-ab').style.display  = 'flex';
  $('#contrast-upgrade').style.display = '';
}
// Progress from the Python side. It sends codes, never strings, so the copy
// stays in one place (the i18n tables) and this stays localizable.
function onPreviewEvent(p){
  if(!p) return;
  const c=$('#contrast-card'), body=$('#contrast-body');
  if(p.state==='loading'){    ccStatus('contrast_loading'); return; }
  if(p.state==='playing'){    ccStatus('contrast_playing'); return; }
  if(p.state==='playing_pro'){ccStatus('contrast_playing_pro'); return; }
  if(p.state==='done'){
    if(c) c.classList.remove('busy');
    ccStatus(null);
    document.querySelectorAll('.ccbtn').forEach(b=>b.classList.remove('playing'));
    if(!contrastHeard) contrastToPitch();
    return;
  }
  if(p.state==='error'){
    if(c) c.classList.remove('busy');
    ccStatus(null);
    if(body) body.textContent = (p.code==='no_voice') ? T('contrast_novoice') : T('contrast_failed');
    $('#contrast-cta').style.display='none';
    $('#contrast-ab').style.display='none';
    setTimeout(hideContrast, 6000);
  }
}
/* ── THE TASTE WALL ─────────────────────────────────────────────────────────
   The session has already stopped (the Pro voice finished its sentence first).
   This card is the decision point: hear the last sentence in both voices, then
   continue on the free voice — a NEW session the server routes to the cascade —
   or buy minutes. One session, one engine, so what the UI says is playing and
   what the ear hears can never disagree again. */
let tasteWallMode = 'video';
function openTasteWall(mode){
  tasteWallMode = mode || 'video';
  hideContrast();                       // one pitch at a time
  // Never offer a continuation the server will refuse. If the taste and today's
  // free minutes ran out together, "Continue with the free voice" would start a
  // session straight into a 402 — so the offer is withdrawn and only the way
  // forward (buy) is left. The card still explains what happened.
  const cont = $('#tw-continue');
  if(cont) cont.style.display = freeAvailableNow(QUOTA) ? '' : 'none';
  $('#scrim').classList.add('open'); $('#taste-wall-modal').classList.add('open');
  openModal($('#taste-wall-modal'), closeTasteWall, null);
}
function closeTasteWall(){ $('#taste-wall-modal').classList.remove('open'); if(!$('#drawer').classList.contains('open')) $('#scrim').classList.remove('open'); closeModal(); }
$('#tw-buy').onclick = e => { e.preventDefault(); try{ api().open_url(PACKS_URL); }catch(_){} };
/* ── THE DAILY WALL ─────────────────────────────────────────────────────────
   Raised when the CASCADE ran out of today's minutes (the engine was already the
   free voice, so this can only be the daily allowance — see webui._on_quota_
   exceeded). The taste wall's offer would be absurd here: you cannot hand someone
   the free voice they have been listening to for ten minutes. */
function closeDailyWall(){ $('#daily-wall-modal').classList.remove('open'); if(!$('#drawer').classList.contains('open')) $('#scrim').classList.remove('open'); closeModal(); }
// "in 4 hours" beats "tomorrow" for a user in UTC+3 at 22:00, for whom tomorrow is
// two hours away — the allowance resets at UTC midnight, not at theirs. The server
// sends the real reset instant; Intl renders it in the UI language so this needs
// no per-locale unit strings. Without the field (old server), say the honest vague
// thing rather than invent a number.
function resetsInText(q){
  const at = q && q.cascade_resets_at;
  if(typeof at !== 'number' || !at) return T('dw_tomorrow');
  const mins = Math.round((at * 1000 - Date.now()) / 60000);
  if(mins <= 0) return T('dw_tomorrow');
  try{
    const rtf = new Intl.RelativeTimeFormat(LANG, {numeric:'auto'});
    return mins >= 60 ? rtf.format(Math.round(mins/60), 'hour') : rtf.format(mins, 'minute');
  }catch(_){ return T('dw_tomorrow'); }
}
function openDailyWall(){
  const q = QUOTA || {};
  hideContrast();
  const body = $('#dw-body');
  if(body) body.textContent = T('dw_body')
    .replace('{n}', String(Math.round(freeDailyMinutes(q))))
    .replace('{t}', resetsInText(q));
  $('#scrim').classList.add('open'); $('#daily-wall-modal').classList.add('open');
  openModal($('#daily-wall-modal'), closeDailyWall, null);
}
$('#dw-ok').onclick  = e => { e.preventDefault(); closeDailyWall(); };
$('#dw-buy').onclick = e => { e.preventDefault(); try{ api().open_url(PACKS_URL); }catch(_){} };
/* ── THE DEVICE-BLOCK WALL ─────────────────────────────────────────────────
   Raised when THIS account can't start because its device's one free tier was
   already claimed by a different account (Tier A3b — webui._start's
   DeviceBlockedError, first_account set). Distinct from the taste/daily wall:
   nothing was spent by this account, so the fix is "sign in over there", not
   "buy more" — though buying is still offered for a user who'd rather keep
   this account. info = {first_account, remaining_minutes} from the 402 body;
   remaining_minutes may be absent or -1 (the other account is unlimited), in
   which case the short body (no minute count) is used instead. */
function closeDeviceBlockWall(){ $('#device-block-modal').classList.remove('open'); if(!$('#drawer').classList.contains('open')) $('#scrim').classList.remove('open'); closeModal(); }
function openDeviceBlockWall(info){
  hideContrast();
  const account = (info && info.first_account) || '';
  const min = info && typeof info.remaining_minutes === 'number' && info.remaining_minutes >= 0
    ? Math.round(info.remaining_minutes) : null;
  const body = $('#db-body');
  if(body) body.textContent = (min != null ? T('db_body') : T('db_body_short'))
    .replace('{account}', account).replace('{min}', String(min));
  $('#scrim').classList.add('open'); $('#device-block-modal').classList.add('open');
  openModal($('#device-block-modal'), closeDeviceBlockWall, null);
}
$('#db-buy').onclick = e => { e.preventDefault(); try{ api().open_url(PACKS_URL); }catch(_){} };
$('#db-switch').onclick = async e => {
  e.preventDefault();
  closeDeviceBlockWall();
  // Same sequence as the drawer's logout button (below): drop the token,
  // clear the quota chip, and raise the login card for the right account.
  try{ await api().voxis_logout(); }catch(_){}
  QUOTA=null;
  renderQuotaBar(null);
  $('#quota-gate').style.display='none';
  resetTranscript();
  showLoginOverlay('login');
};
$('#tw-continue').onclick = async e => {
  e.preventDefault();
  closeTasteWall();
  try{ await invokeStart(tasteWallMode); }catch(_){}
};
// The same last sentence, in either voice — the session is stopped, so these
// play through the standalone player (proven path).
$('#tw-pro').onclick  = async e => { e.preventDefault(); try{ await api().pro_voice_replay(); }catch(_){} };
$('#tw-free').onclick = async e => { e.preventDefault(); try{ await api().free_voice_preview(); }catch(_){} };
function closeMeetingLock(){ $('#meeting-lock-modal').classList.remove('open'); if(!$('#drawer').classList.contains('open')) $('#scrim').classList.remove('open'); closeModal(); }
function openMeetingLock(){
  $('#scrim').classList.add('open'); $('#meeting-lock-modal').classList.add('open');
  openModal($('#meeting-lock-modal'), closeMeetingLock, null);
}
$('#mlock-dismiss').onclick = e => { e.preventDefault(); closeMeetingLock(); };
$('#mlock-cta').onclick = e => { e.preventDefault(); closeMeetingLock(); try{ api().open_url(PACKS_URL); }catch(_){} };
$('#review-dismiss').onclick = e => { e.preventDefault(); closeReviewModal(); };
$('#review-cta').onclick = async e => {
  e.preventDefault();
  closeReviewModal();
  try{ await api().rate_voxis(); }catch(_){}
};
$('#consent-cancel').onclick = closeConsent;
$('#consent-accept').onclick = async()=>{
  if($('#consent-dontshow').checked){
    if(STATE.cfg) STATE.cfg.meeting_consent_ack=true;
    try{ await api().set_cfg('meeting_consent_ack', true); }catch(_){}
  }
  closeConsent();
  // consented=true: this acceptance authorizes this start even when the user
  // declined "don't show again" (so meeting_consent_ack was not persisted).
  invokeStart('meeting', true);
};
// Each step points the spotlight at a real element (sel); sel:null = a centered
// welcome/closing step (full dim, no ring). Kept to 3 steps so a new user reaches
// "Get started" in seconds. The VB-CABLE note is intentionally NOT here — it only
// makes sense once the user actually opens Meeting, where openCable() shows it;
// surfacing it earlier scared people off the (cable-free) driverless video path.
const TOUR_STEPS = [
  {sel:null,         titleKey:'onboard_title',  textKey:'onboard_welcome'},
  {sel:'#m-video',   titleKey:'video_t1',       textKey:'onboard_video'},
  {sel:null,         titleKey:'tour_ready_t',   textKey:'tour_ready_d'},
];
let onboardStep=0;
// Size/place the lit hole around the target and float the callout beside it.
function positionTour(){
  const s=TOUR_STEPS[onboardStep], spot=$('#tour-spot'), pop=$('#tour-pop');
  const vw=window.innerWidth, vh=window.innerHeight, m=16;
  const el = s.sel ? document.querySelector(s.sel) : null;
  const r = el ? el.getBoundingClientRect() : null;
  // No target, or the target is hidden/zero-size (e.g. a locked tile pre-login):
  // fall back to a centered, fully-dimmed step instead of a stray hole.
  if(!r || (r.width<2 && r.height<2)){
    spot.classList.add('center');
    spot.style.width='0px'; spot.style.height='0px';
    spot.style.left=(vw/2)+'px'; spot.style.top=(vh/2)+'px';
    pop.style.left=Math.round((vw-pop.offsetWidth)/2)+'px';
    pop.style.top =Math.round((vh-pop.offsetHeight)/2)+'px';
    return;
  }
  spot.classList.remove('center');
  const pad=8;
  const sx=Math.max(0,r.left-pad), sy=Math.max(0,r.top-pad);
  spot.style.left=sx+'px'; spot.style.top=sy+'px';
  spot.style.width=(Math.min(vw,r.right+pad)-sx)+'px';
  spot.style.height=(Math.min(vh,r.bottom+pad)-sy)+'px';
  const pw=pop.offsetWidth, ph=pop.offsetHeight, gap=16;
  let left, side=true;
  if(r.right+gap+pw <= vw-m) left=r.right+gap;              // prefer right of target
  else if(r.left-gap-pw >= m) left=r.left-gap-pw;           // else left
  else { left=Math.min(Math.max(m,r.left),vw-pw-m); side=false; } // else stack
  let top;
  if(side) top=Math.min(Math.max(m,r.top),vh-ph-m);         // align to target vertically
  else top=(r.bottom+gap+ph <= vh-m) ? r.bottom+gap : Math.max(m,r.top-gap-ph); // below else above
  pop.style.left=Math.round(left)+'px'; pop.style.top=Math.round(top)+'px';
}
function renderTour(){
  const total=TOUR_STEPS.length, s=TOUR_STEPS[onboardStep];
  $('#tour-title').textContent = T(s.titleKey);
  $('#tour-text').textContent  = T(s.textKey);
  $('#tour-note').style.display = s.cable ? 'flex' : 'none';
  if(s.cable) $('#tour-note-txt').textContent = T('cable_required');
  $('#tour-eyebrow').textContent = T('onboard_eyebrow');
  $('#tour-step').textContent = T('onboard_step_fmt').replace('{n}', onboardStep+1).replace('{total}', total);
  $('#tour-back').style.visibility = onboardStep===0 ? 'hidden' : 'visible';
  $('#tour-next').textContent = onboardStep===total-1 ? T('onboard_get_started') : T('onboard_next');
  const el = s.sel ? document.querySelector(s.sel) : null;
  if(el && el.scrollIntoView) try{ el.scrollIntoView({block:'nearest'}); }catch(_){}
  // Two frames so the callout has measured its final size before we place it.
  requestAnimationFrame(()=>requestAnimationFrame(positionTour));
}
// openOnboard/finishOnboard names are kept so the first-run gate and the
// "show tour again" button keep working unchanged.
function openOnboard(){
  onboardStep=0;
  $('#tour').hidden=false;
  renderTour();
  try{ $('#tour-next').focus(); }catch(_){}
}
function finishOnboard(){
  $('#tour').hidden=true;
  STATE.onboarding_done=true;
  try{ api().mark_onboarding_done(); }catch(_){}
  try{ $('#gear').focus(); }catch(_){}
}
$('#tour-back').onclick = ()=>{ if(onboardStep>0){ onboardStep--; renderTour(); } };
$('#tour-next').onclick = ()=>{ if(onboardStep<TOUR_STEPS.length-1){ onboardStep++; renderTour(); } else { finishOnboard(); } };
$('#tour-skip').onclick = ()=>finishOnboard();
// Keyboard: Esc skips, arrows navigate. Enter is left to the focused button so
// it isn't handled twice.
document.addEventListener('keydown', e=>{
  if($('#tour').hidden) return;
  if(e.key==='Escape') finishOnboard();
  else if(e.key==='ArrowRight') $('#tour-next').click();
  else if(e.key==='ArrowLeft') $('#tour-back').click();
});
window.addEventListener('resize', ()=>{ if(!$('#tour').hidden) positionTour(); });
/* ---------- meeting cable-required modal ---------- */
function openCable(){
  // Official (Store) build only informs — Store policy 10.1.5 bars the app from
  // facilitating acquisition of a non-Microsoft driver, so hide the in-app
  // download/install button there. The OSS build keeps the convenience link.
  const inst=$('#cable-install'); if(inst) inst.style.display = STATE.official_release ? 'none' : '';
  // With no in-app install button on the Store build, show the manual how-to.
  const man=$('#cable-manual-note'); if(man) man.style.display = STATE.official_release ? 'flex' : 'none';
  $('#scrim').classList.add('open'); $('#cable-modal').classList.add('open'); openModal($('#cable-modal'), closeCable, $('#m-meeting'));
}
function closeCable(){ $('#cable-modal').classList.remove('open'); if(!$('#drawer').classList.contains('open')) $('#scrim').classList.remove('open'); closeModal(); }
$('#cable-cancel').onclick = closeCable;
$('#cable-install').onclick = ()=>{ try{ api().open_cable_download(); }catch(_){} closeCable(); };
/* ---------- report a problem modal ---------- */
function reportGather(){
  return {
    category: $('#report-category').value,
    severity: $('#report-severity').value,
    message: $('#report-message').value,
    email: $('#report-email').value,
    include_transcript: $('#report-transcript').checked,
  };
}
function reportResetForm(){
  $('#report-form').style.display=''; $('#report-done').style.display='none';
  $('#report-foot').style.display=''; $('#report-foot-done').style.display='none';
  $('#report-err').style.display='none';
  $('#report-ticket-row').style.display=''; $('#report-done-keep').style.display='';
  const s=$('#report-send'); s.disabled=false; s.textContent=T('report_send');
  const pv=$('#report-preview-pre'); if(pv) pv.textContent='';
  const d=$('#report-modal').querySelector('details'); if(d) d.open=false;
}
function openReport(){
  reportResetForm();
  $('#report-message').value=''; $('#report-email').value='';
  $('#report-transcript').checked=false; $('#report-severity').value='normal'; $('#report-category').value='audio';
  $('#scrim').classList.add('open'); $('#report-modal').classList.add('open');
  openModal($('#report-modal'), closeReport, $('#reportbtn'));
  // Flush any offline-queued reports. Opening the form is an explicit user
  // context — never a silent background send.
  try{ api().flush_reports(); }catch(_){}
}
function closeReport(){ $('#report-modal').classList.remove('open'); if(!$('#drawer').classList.contains('open')) $('#scrim').classList.remove('open'); closeModal(); }
(function(){
  const rb=$('#reportbtn'); if(rb) rb.onclick=openReport;
  const rbt=$('#reportbtn-top'); if(rbt) rbt.onclick=openReport;
  $('#report-cancel').onclick=closeReport;
  $('#report-close').onclick=closeReport;
  $('#report-copy').onclick=()=>{ try{ navigator.clipboard.writeText($('#report-ticket').textContent||''); }catch(_){} };
  const det=$('#report-modal').querySelector('details');
  if(det) det.addEventListener('toggle', async ()=>{
    if(!det.open) return;
    try{ const p=await api().preview_report(reportGather()); $('#report-preview-pre').textContent=JSON.stringify(p,null,2); }
    catch(_){ $('#report-preview-pre').textContent=''; }
  });
  $('#report-send').onclick=async ()=>{
    const errEl=$('#report-err');
    errEl.style.display='none';
    const s=$('#report-send'); s.disabled=true; s.textContent=T('report_sending');
    let res; try{ res=await api().send_report(reportGather()); }catch(_){ res={ok:false}; }
    s.textContent=T('report_send');
    if(res && res.ok){
      $('#report-done-intro').textContent=T('report_done_intro');
      $('#report-ticket').textContent=res.ticket||'—';
      $('#report-form').style.display='none'; $('#report-foot').style.display='none';
      $('#report-done').style.display=''; $('#report-foot-done').style.display='';
    } else if(res && res.queued){
      $('#report-done-intro').textContent=T('report_queued');
      $('#report-ticket-row').style.display='none'; $('#report-done-keep').style.display='none';
      $('#report-form').style.display='none'; $('#report-foot').style.display='none';
      $('#report-done').style.display=''; $('#report-foot-done').style.display='';
    } else {
      errEl.textContent=T('report_err_failed'); errEl.style.display=''; s.disabled=false;
    }
  };
})();
/* ---------- transcript history modal ---------- */
let HIST_SESSIONS = [], HIST_CUR = null, HIST_CUR_FILE = null;
function openHistory(){
  $('#scrim').classList.add('open'); $('#history-modal').classList.add('open');
  openModal($('#history-modal'), closeHistory, $('#historybtn'));
  loadHistoryList();
}
function closeHistory(){
  $('#history-modal').classList.remove('open');
  if(!$('#drawer').classList.contains('open')) $('#scrim').classList.remove('open');
  closeModal();
}
$('#historybtn').onclick = openHistory;
$('#history-close').onclick = closeHistory;
function fmtSessionWhen(iso, started){
  try{ const d = iso ? new Date(iso) : new Date((started||0)*1000); return d.toLocaleString(LANG); }
  catch(_){ return iso || ''; }
}
async function loadHistoryList(){
  try{ HIST_SESSIONS = await api().list_sessions() || []; }catch(_){ HIST_SESSIONS = []; }
  renderHistoryList();
}
function renderHistoryList(){
  const q = ($('#history-search').value||'').trim().toLowerCase();
  const list = $('#history-list'); list.innerHTML='';
  const rows = HIST_SESSIONS.filter(s=>{
    if(!q) return true;
    const hay = ((s.preview||'')+' '+(s.target_in||'')+' '+(s.target_out||'')+' '+(s.started_iso||'')).toLowerCase();
    return hay.includes(q);
  });
  if(!rows.length){ const d=document.createElement('div'); d.className='histempty'; d.textContent=T('history_none'); list.appendChild(d); return; }
  rows.forEach(s=>{
    const b=document.createElement('button'); b.type='button'; b.className='histrow'; b.setAttribute('role','option');
    b.dataset.file=s.file;
    const langs = (s.target_in||'?')+' / '+(s.target_out||'?');
    b.innerHTML = '<div class="hr-when"></div><div class="hr-meta"></div><div class="hr-prev"></div>';
    b.querySelector('.hr-when').textContent = fmtSessionWhen(s.started_iso, s.started);
    b.querySelector('.hr-meta').textContent = T('history_turns_n').replace('{n}', s.turns) + ' · ' + langs;
    b.querySelector('.hr-prev').textContent = s.preview||'';
    b.onclick = ()=>openSession(s.file, b);
    list.appendChild(b);
  });
}
$('#history-search').oninput = ()=>{ renderHistoryList(); if(HIST_CUR) renderHistoryTurns(); };
async function openSession(file, rowEl){
  document.querySelectorAll('#history-list .histrow').forEach(r=>r.classList.toggle('sel', r===rowEl));
  try{ HIST_CUR = await api().load_session(file); }catch(_){ HIST_CUR=null; }
  HIST_CUR_FILE = HIST_CUR ? file : null;
  const has = !!(HIST_CUR && HIST_CUR.turns && HIST_CUR.turns.length);
  ['#hist-export-txt','#hist-export-srt','#hist-export-vtt','#hist-delete'].forEach(s=>$(s).disabled=!HIST_CUR_FILE);
  $('#history-empty').hidden = has;
  $('#history-turns').hidden = !has;
  renderHistoryTurns();
}
function fmtOffset(s){ s=Math.max(0,Math.floor(s||0)); return String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0'); }
function escHtml(s){ return (s||'').replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function highlight(s, q){
  if(!q) return escHtml(s);
  s=s||''; const lo=s.toLowerCase();
  // Fast path: most scripts case-fold without changing code-unit count, so
  // lowercase offsets map 1:1 onto the original string.
  if(lo.length===s.length){ let out='', i=0;
    while(true){ const j=lo.indexOf(q,i); if(j<0){ out+=escHtml(s.slice(i)); break; }
      out+=escHtml(s.slice(i,j))+'<mark>'+escHtml(s.slice(j,j+q.length))+'</mark>'; i=j+q.length; }
    return out;
  }
  // Slow path: a length-changing fold (Turkish 'İ'→'i̇', German 'ß'→'ss')
  // shifts lowercase offsets, so fold per-character and map each folded code
  // unit back to its original index to keep <mark> on the right characters.
  const map=[]; let folded='';
  for(let k=0;k<s.length;k++){ const f=s[k].toLowerCase(); for(let m=0;m<f.length;m++){ folded+=f[m]; map.push(k); } }
  let out='', i=0;                       // i indexes the ORIGINAL string
  while(true){
    let fi=0; while(fi<map.length && map[fi]<i) fi++;   // folded offset for original i
    const j=folded.indexOf(q,fi);
    if(j<0){ out+=escHtml(s.slice(i)); break; }
    const startOrig=map[j];
    const endOrig=map[j+q.length-1]+1;   // exclusive original end of the match
    out+=escHtml(s.slice(i,startOrig))+'<mark>'+escHtml(s.slice(startOrig,endOrig))+'</mark>';
    i=endOrig;
  }
  return out;
}
function renderHistoryTurns(){
  const box=$('#history-turns'); if(!HIST_CUR){ box.innerHTML=''; return; }
  const q=($('#history-search').value||'').trim().toLowerCase();
  box.innerHTML='';
  // Speaker tags render only for a genuinely multi-speaker session, and only
  // where the speaker CHANGES (same run-grouping rule as captions + exports).
  // Prefixes are computed over the FULL turn list before the search filter so
  // a filtered view still shows truthful labels.
  const turns=HIST_CUR.turns||[];
  const spks=new Set(turns.map(t=>t.spk).filter(s=>s!=null));
  const multi=spks.size>=2;
  let prevSpk=null;
  turns.forEach(turn=>{
    const pre=(multi && turn.spk!=null && turn.spk!==prevSpk) ? 'S'+turn.spk+': ' : '';
    if(turn.spk!=null) prevSpk=turn.spk;
    if(q && !((turn.text||'').toLowerCase().includes(q) || (turn.src||'').toLowerCase().includes(q))) return;
    const d=document.createElement('div'); d.className='ht';
    const ts=document.createElement('div'); ts.className='ht-t'; ts.textContent=fmtOffset(turn.t); d.appendChild(ts);
    if(turn.src){ const sc=document.createElement('div'); sc.className='ht-src'; sc.innerHTML=(pre?escHtml(pre):'')+highlight(turn.src,q); d.appendChild(sc); }
    const tx=document.createElement('div'); tx.className='ht-text'; tx.innerHTML=(pre?escHtml(pre):'')+highlight(turn.text,q); d.appendChild(tx);
    box.appendChild(d);
  });
}
async function exportSession(fmt){
  if(!HIST_CUR_FILE) return;
  const bi = !!($('#hist-bilingual')||{}).checked;
  let r=null; try{ r=await api().export_session(HIST_CUR_FILE, fmt, bi); }catch(_){}
  // Keep History open and reveal the exported file so the user sees where it
  // landed (the folder is also one click away via #hist-open-folder).
  if(r && r.ok && r.file){ try{ api().reveal_transcript(r.file); }catch(_){} }
}
$('#hist-export-txt').onclick = ()=>exportSession('txt');
$('#hist-export-srt').onclick = ()=>exportSession('srt');
$('#hist-export-vtt').onclick = ()=>exportSession('vtt');
$('#hist-delete').onclick = async()=>{
  if(!HIST_CUR_FILE) return;
  try{ await api().delete_session(HIST_CUR_FILE); }catch(_){}
  HIST_CUR=null; HIST_CUR_FILE=null;
  $('#history-empty').hidden=false; $('#history-turns').hidden=true; $('#history-turns').innerHTML='';
  ['#hist-export-txt','#hist-export-srt','#hist-export-vtt','#hist-delete'].forEach(s=>$(s).disabled=true);
  loadHistoryList();
};
/* ---------- privacy / data-flow explainer modal (informational) ---------- */
// Honest, build-aware copy: OSS emphasizes BYOK + zero telemetry; official SaaS
// names the AI translation provider generically (audio may route to either engine);
// the named sub-processors live in the linked website privacy policy.
function renderPrivacy(){
  const off = !!(STATE && STATE.official_release);
  $('#privacy-lead').textContent   = T('privacy_lead');
  $('#privacy-detail').textContent = T(off ? 'privacy_saas_detail' : 'privacy_byok_detail');
}
function openPrivacy(){ renderPrivacy(); $('#scrim').classList.add('open'); $('#privacy-modal').classList.add('open'); openModal($('#privacy-modal'), closePrivacy, $('#trustbadge')); }
function closePrivacy(){ $('#privacy-modal').classList.remove('open'); if(!$('#drawer').classList.contains('open')) $('#scrim').classList.remove('open'); closeModal(); }
$('#trustbadge').onclick = openPrivacy;
$('#privacy-close').onclick = closePrivacy;
$('#privacy-policy-link').onclick = e=>{ e.preventDefault(); try{ api().open_url('https://voxislive.com/privacy'); }catch(_){} };
// "Show tour again": clear the persisted flag, close the drawer, replay the tour.
$('#showtourbtn').onclick = async()=>{
  try{ await api().reset_onboarding(); }catch(_){}
  STATE.onboarding_done=false;
  closeDrawer();
  openOnboard();
};
$('#storebtn').onclick = async()=>{ try{ await api().open_store_page(); }catch(_){} };
$('#updatebadge').onclick = async()=>{ try{ await api().open_store_page(); }catch(_){} };
$('#showgem').onclick = e=>{
  e.preventDefault();
  const g=$('#gemkey'); const show=g.type==='password';
  g.type=show?'text':'password'; e.target.textContent=show?T('hide'):T('show');
};
// BYOK clear/save handlers are bound only on developer builds; the official
// build hides the section entirely, so they are never wired (mirrors the Python
// double-gate on save_keys/clear_byok).
let _byokBound=false;
function bindByokHandlers(){
  if(_byokBound) return; _byokBound=true;
  $('#clearbtn').onclick = async e=>{
    e.preventDefault();
    if(!confirm(T('confirm_clear_byok'))) return;
    await api().clear_byok('gemini');
    $('#byok-badge').style.display='none';
    $('#gemkey').value='';
  };
}
$('#savesettings').onclick = async()=>{
  if(!STATE.official_release){
    const gem = $('#gemkey').value.trim();
    if(gem){
      const ok = await api().save_keys(gem);
      if(ok){
        $('#byok-badge').style.display='inline'; $('#gemkey').value='';
      } else { alert(T('alert_key_failed')); return; }
    }
  }
  await api().set_cfg('ui_language', $('#uilang').value);
  $('#closedrawer').click();
};
$('#manageplanbtn').onclick = () => { try{api().open_url('https://voxislive.com/account');}catch(_){} };
$('#invitebtn').onclick = () => { try{api().open_url('https://voxislive.com/account?panel=refer');}catch(_){} };
$('#logoutbtn').onclick = async()=>{
  try{ await api().voxis_logout(); }catch(e){}
  QUOTA=null;
  renderQuotaBar(null);
  $('#quota-gate').style.display='none';
  resetTranscript();
  $('#closedrawer').click();
  showLoginOverlay('login');
};
document.querySelectorAll('.k').forEach(k=>k.onclick=async()=>{
  k.textContent=T('press_key'); k.classList.add('recording');
  const combo = await api().capture_hotkey(k.dataset.hk);
  k.textContent = combo || STATE.cfg.hotkeys[k.dataset.hk] || '—';
  k.classList.remove('recording');
  if(combo){ STATE.cfg.hotkeys[k.dataset.hk]=combo; updateTileTitles(); }
});
// Hotkeys are otherwise only discoverable inside Settings — surface each
// scenario's assigned combo in its tile tooltip.
function updateTileTitles(){
  const hk=(STATE.cfg && STATE.cfg.hotkeys) || {};
  const set=(id, label, key)=>{ const el=$(id); if(el) el.title = label + (hk[key] ? ' — '+hk[key] : ''); };
  set('#m-video', T('video_t1'), 'video');
  set('#m-meeting', T('meeting_t1'), 'meeting');
}
/* ---------- transkript ---------- */
function emptyHtml(){ return `<div class="empty" id="empty"><div class="orb"><svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M4 9.5v5M8 6v12M12 9v6M16 4v16M20 8.5v7"/></svg></div><div class="big" data-i18n="empty_big">${T('empty_big')}</div><div class="small" data-i18n-html="empty_small">${T('empty_small')}</div><button class="btn btn-primary emptystart" type="button"><svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.5v15l13-7.5z"/></svg><span data-i18n="start_cue">${T('start_cue')}</span><span class="dim">—</span><span data-i18n="video_t1">${T('video_t1')}</span></button></div>`; }
// Delegated: the empty state is rebuilt on reset, the handler survives it.
$('#scroll').addEventListener('click', e=>{ if(e.target.closest('.emptystart')) $('#m-video').click(); });
let curTurn=null, curBubble=null, pendingTurn=null;
// Which meeting side the current bubble belongs to ('incoming' = the other
// party, 'outgoing' = us). A meeting runs two translators into this one
// caption stream, so a side change must always open a NEW bubble — otherwise
// the two conversations append into the same line. Null in Video/Game mode.
let curLeg=null;
function trimScroll(){ const sc=$('#scroll'); while(sc.children.length>90) sc.removeChild(sc.firstChild); }
function scrollEnd(){ const sc=$('#scroll'); sc.scrollTop=sc.scrollHeight; }
function removeEmpty(){ const e=$('#empty'); if(e) e.remove(); }
function resetTranscript(){
  if(pendingTurn){ clearTimeout(pendingTurn.timer); pendingTurn=null; }
  $('#scroll').innerHTML=emptyHtml(); curTurn=null; curBubble=null; curLeg=null;
  latencyNoteShown=false; lastSpk=null; sawTranslation=false;
}
/* ── WAITING CUE ──────────────────────────────────────────────────────────────
   Everything between pressing Start and the first translated word used to be a
   blank stream. That window is where the product is lost: 40% of all sessions
   end inside 30 s, and the connect handshake alone runs past 10 s for 16% of
   them (p90 33 s) before the model's own interpreter lag even begins. The cue
   says what is happening, escalates if the handshake drags, sets the latency
   expectation BEFORE the wait instead of after it (latency_note only ever fires
   on the first caption, i.e. too late for anyone who gave up), and deletes
   itself the moment a translation lands. Pure UI — it is never part of the
   saved transcript, which the Python side builds from its own turn list. */
let startPendingAt = 0;      // when Start was clicked; 0 = not starting
let sawTranslation = false;  // any translation this session (even with captions off)
const WAIT_SLOW_SECONDS = 10;
const WAIT_GIVEUP_SECONDS = 45;   // start refused/failed: stop claiming we connect
function clearWaitCue(){ const el=$('#waitcue'); if(el) el.remove(); }
function renderWaitState(p){
  const live = !!(p && p.mode);
  if(sawTranslation || document.querySelector('#scroll .turn') || (!live && !startPendingAt)){
    if(!live) startPendingAt = 0;
    clearWaitCue();
    return;
  }
  let text;
  if(live){
    startPendingAt = 0;   // connected: the handshake half of the wait is over
    text = T('wait_listening');
  } else {
    const secs = (Date.now() - startPendingAt) / 1000;
    // A start that was refused (quota wall, missing cable, device error) leaves
    // no session behind; its own error line is already on screen, so stop
    // asserting that we are still connecting.
    if(secs > WAIT_GIVEUP_SECONDS){ startPendingAt = 0; clearWaitCue(); return; }
    text = T(secs >= WAIT_SLOW_SECONDS ? 'wait_connecting_slow' : 'wait_connecting');
  }
  let el = $('#waitcue');
  if(!el){
    el = document.createElement('div');
    el.id = 'waitcue'; el.className = 'line sys waitcue';
    $('#scroll').appendChild(el);
  }
  if(el.textContent !== text) el.textContent = text;
  // It describes what is happening NOW, so it stays the last line even after a
  // status line (e.g. "mode started") is appended behind it.
  const sc = $('#scroll');
  if(sc.lastElementChild !== el){ sc.appendChild(el); scrollEnd(); }
}
// Every Start path goes through here so the cue appears the instant the user
// clicks, not one poll later.
function invokeStart(mode, consented){
  startPendingAt = Date.now();
  sawTranslation = false;
  try{ return consented===undefined ? api().start(mode) : api().start(mode, consented); }
  catch(e){ startPendingAt = 0; throw e; }
}
/* Speaker tag on a turn bubble. The Python side sends a label only for a
   genuinely multi-speaker session (≥2 voices seen); here the tag renders only
   where the speaker CHANGES vs the previous turn, so one person talking
   across several turns reads as a single labeled run. lastSpk is the label of
   the last finalized turn (definitive, from the src event); hints on a live
   line are reconciled when it finalizes. */
let lastSpk=null;
function setLegTag(bubble, leg){
  // Only in a meeting: Video/Game sends no leg, and an unlabelled transcript
  // must keep reading exactly as it did before two-way captions existed.
  if(!bubble || !leg) return;
  const tag=document.createElement('span');
  tag.className='leg leg-'+leg;
  tag.textContent = T(leg==='incoming' ? 'leg_them' : 'leg_me');
  bubble.prepend(tag);
}
function setSpkTag(bubble, spk, final){
  if(!bubble) return;
  if(final && spk!=null){
    const show = spk!==lastSpk;
    lastSpk = spk;
    let tag=bubble.querySelector('.spk');
    if(!show){ if(tag) tag.remove(); return; }
    if(!tag){ tag=document.createElement('span'); tag.className='spk'; bubble.prepend(tag); }
    tag.textContent='S'+spk;
    return;
  }
  if(spk==null || spk===lastSpk) return;   // live hint: same speaker → no tag
  let tag=bubble.querySelector('.spk');
  if(!tag){ tag=document.createElement('span'); tag.className='spk'; bubble.prepend(tag); }
  tag.textContent='S'+spk;
}
function newTurn(spk, leg){
  removeEmpty();
  const turn=document.createElement('div'); turn.className='turn'; turn.setAttribute('role','group');
  const bubble=document.createElement('div'); bubble.className='tr active';
  // Per-turn copy: copies the finalized translation text of this turn (the
  // speaker tag is presentation, not content — stripped from the copy).
  const act=document.createElement('div'); act.className='turnact';
  const copy=document.createElement('button'); copy.type='button';
  copy.title=T('copy_turn'); copy.setAttribute('aria-label',T('copy_turn'));
  copy.innerHTML='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';
  copy.onclick=()=>{ try{
    const c=bubble.cloneNode(true); c.querySelectorAll('.spk').forEach(x=>x.remove());
    navigator.clipboard.writeText(c.textContent.trim());
  }catch(_){} };
  act.appendChild(copy);
  turn.appendChild(act);
  turn.appendChild(bubble);
  $('#scroll').appendChild(turn);
  curTurn=turn; curBubble=bubble; curLeg=leg||null; trimScroll();
  setLegTag(bubble, leg);
  setSpkTag(bubble, spk);
}
function appendWords(el, text){
  // Words get an animated inline-block span; whitespace stays a plain text node
  // (a whitespace-only inline-block collapses to zero width and eats the space).
  text.split(/(\s+)/).forEach(p=>{
    if(!p) return;
    if(/^\s+$/.test(p)){ el.appendChild(document.createTextNode(p)); return; }
    const s=document.createElement('span'); s.className='w'; s.textContent=p; el.appendChild(s);
  });
}
let latencyNoteShown=false;
// A new caption bubble whose creation is being held back (see onTrans) while
// its translated audio is still queued behind a playback backlog. Holding
// only the BUBBLE — never the words inside it — is what tonight's reverted
// wordQueue got wrong: that throttled every word and dropped some at turn
// boundaries. Here, once the delay elapses, all queued text is dumped
// instantly via the normal (unthrottled) appendWords.
function flushPendingTurn(){
  if(!pendingTurn) return;
  clearTimeout(pendingTurn.timer);
  if(curBubble) curBubble.classList.remove('active');
  newTurn(pendingTurn.spk, pendingTurn.leg);
  pendingTurn.queued.forEach(t=>appendWords(curBubble, t));
  pendingTurn=null;
}
function onTrans(text, newline, spk, backlogS, leg){
  // A side change always starts a new bubble, whatever the engine's own
  // pause timing said.
  if(leg && curLeg && leg!==curLeg) newline = true;
  // Counted before the subtitle gate: the inverse demo replays the last line
  // Voxis SPOKE, which happens whether or not captions are switched on.
  if(newline) contrastLines++;
  // Marked before the subtitle gate: with captions switched off no bubble is
  // ever created, and the waiting cue must still know that translation started.
  sawTranslation = true;
  if(!$('#subs').checked) return;
  // Honest-latency: the caption renders the instant a token arrives, ahead of the
  // TTS audio. The first turn of a session also drops a one-time in-context note
  // explaining the model's inherent ~3s interpreter delay.
  if(!latencyNoteShown && !(STATE.cfg && STATE.cfg.latency_note_seen)){
    latencyNoteShown=true;
    if(STATE.cfg) STATE.cfg.latency_note_seen = true;
    try{ api().mark_seen('latency_note_seen'); }catch(_){}
    addSys(T('latency_note'));
  }
  // spk is the LIVE hint for the streaming line (the definitive label lands
  // with the src event when the turn finalizes).
  if(newline || !curBubble){
    flushPendingTurn();  // an earlier delayed turn must land before this one starts
    // Under a heavy playback backlog the translated audio for this NEW line
    // hasn't started yet — showing its bubble immediately would put the
    // caption visibly ahead of what's actually audible. Hold its appearance
    // back by (at most) the current backlog, capped so it never feels laggy.
    const delayMs = Math.min(Math.max(backlogS||0, 0), 1.5) * 1000;
    if(curBubble) curBubble.classList.remove('active');
    if(delayMs < 50){
      newTurn(spk, leg);
      appendWords(curBubble, text);
    } else {
      pendingTurn = {spk, leg, queued:[text],
        timer: setTimeout(()=>{ flushPendingTurn(); scrollEnd(); }, delayMs)};
    }
  } else if(pendingTurn){
    pendingTurn.queued.push(text);
  } else {
    appendWords(curBubble, text);
  }
  scrollEnd();
}
/* Live "heard now" ghost line: streams the source utterance as it is spoken.
   Kept as the LAST element of the scroll; cleared when the paired source lands
   on its turn (onSrc) or the session ends. NOT attached to the current turn —
   source leads translation by the ear-voice lag, so the live text belongs to
   the NEXT turn, not the one currently rendering. */
function onHearLive(text){
  const h=$('#hearline');
  if(!$('#subs').checked || !text){ if(h) h.remove(); return; }
  removeEmpty();
  let line=h;
  if(!line){
    line=document.createElement('div'); line.id='hearline'; line.className='hearline';
    const who=document.createElement('span'); who.className='who'; who.textContent=T('source');
    const ht=document.createElement('span'); ht.className='ht';
    line.appendChild(who); line.appendChild(ht);
  }
  $('#scroll').appendChild(line);           // re-append: always last
  line.querySelector('.ht').textContent=text+'…';
  scrollEnd();
}
function onSrc(text, spk, leg){
  // The utterance is being consumed by its turn — retire the ghost line.
  { const h=$('#hearline'); if(h) h.remove(); }
  // Best-effort source caption beneath the turn that just finalized; also the
  // turn's definitive speaker label (replaces the live hint if it differed).
  const turn=curTurn; if(!turn) return;
  if(spk!=null) setSpkTag(turn.querySelector('.tr'), spk, true);
  if(!text) return;
  let cap=turn.querySelector('.src');
  if(!cap){ cap=document.createElement('div'); cap.className='src'; turn.appendChild(cap); }
  cap.textContent='';
  const who=document.createElement('span'); who.className='who'; who.textContent=T('source');
  cap.appendChild(who); cap.appendChild(document.createTextNode(text));
  scrollEnd();
}
function addSys(text, level){
  if(pendingTurn){ clearTimeout(pendingTurn.timer); pendingTurn=null; }
  removeEmpty();
  const sc=$('#scroll'); const d=document.createElement('div');
  d.className='line sys' + (level==='error' ? ' err' : level==='warn' ? ' warn' : '');
  d.textContent=text;
  sc.appendChild(d); scrollEnd(); trimScroll();
  if(curBubble) curBubble.classList.remove('active');
  curTurn=null; curBubble=null; curLeg=null;
}
// After a transcript is saved, offer inline Open-file / Open-folder actions so the
// real file (now in a user-facing Documents folder) is one click away.
function addTranscriptActions(file){
  const sc=$('#scroll'); if(!sc) return;
  const d=document.createElement('div'); d.className='line sys';
  d.style.display='flex'; d.style.gap='8px'; d.style.flexWrap='wrap';
  const mk=(label,icon,fn)=>{
    const b=document.createElement('button');
    b.className='btn btn-ghost';
    b.style.cssText='width:auto;padding:7px 12px;font-size:12px';
    b.innerHTML=icon+'<span></span>';
    b.lastChild.textContent=label;   // safe text insert (icon stays as markup)
    b.onclick=()=>{ try{fn();}catch(_){}};
    return b;
  };
  const icFile='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>';
  const icFolder='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/></svg>';
  const icExport='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>';
  d.appendChild(mk(T('open_file'), icFile, ()=>api().open_transcript(file)));
  d.appendChild(mk(T('open_folder'), icFolder, ()=>api().reveal_transcript(file)));
  // Quick TXT/SRT/VTT export beside the always-saved JSON, without a trip
  // through History (owner feedback: "Kaydet" only wrote JSON, and users
  // may not think to click through to History for the other formats).
  // Status feedback ("saved to …") comes from the existing 'status' event
  // Python already emits inside export_session — nothing extra needed here.
  ['txt','srt','vtt'].forEach(fmt=>{
    d.appendChild(mk(T('history_fmt_'+fmt), icExport, ()=>api().export_session(file, fmt, true)));
  });
  sc.appendChild(d); scrollEnd(); trimScroll();
}
/* ---------- canlı ses ölçeri ---------- */
const rodEls=[...document.querySelectorAll('#rods i')];
const presEls=[...document.querySelectorAll('#presence i')];
let dispLevel=0, targetLevel=0, meterRAF=0;
const RM = matchMedia('(prefers-reduced-motion: reduce)').matches;
function startMeter(){
  if(meterRAF || RM) return;
  const loop=()=>{
    const now=performance.now();
    dispLevel += (targetLevel - dispLevel) * 0.25;
    rodEls.forEach((b,i)=>{ const k=Math.max(0.08, dispLevel*(0.45+Math.abs(Math.sin(now*0.006+i))*0.9)); b.style.height=(4+k*16)+'px'; });
    presEls.forEach((b,i)=>{ const k=Math.max(0.1, dispLevel*(0.4+Math.abs(Math.sin(now*0.007+i*0.7))*0.95)); b.style.height=(3+k*13)+'px'; });
    const db = dispLevel>0.02 ? Math.round(-46+dispLevel*44) : null;
    $('#meterdb').textContent = (db===null?'−∞':db)+' dB';
    meterRAF=requestAnimationFrame(loop);
  };
  meterRAF=requestAnimationFrame(loop);
}
function stopMeter(){
  if(meterRAF){ cancelAnimationFrame(meterRAF); meterRAF=0; }
  dispLevel=0; targetLevel=0;
  rodEls.forEach(b=>b.style.height='4px'); presEls.forEach(b=>b.style.height='3px');
  $('#meterdb').textContent='−∞ dB';
}
function dbText(level){ const db = level>0.02 ? Math.round(-46+level*44) : null; return (db===null?'−∞':db)+' dB'; }
/* ---------- pill durumu + footer ---------- */
function setPillState(p){
  let st='idle';
  if(p.dotcls==='err') st='error';
  else if(p.dotcls==='warn') st='connecting';
  else if(p.mode){ st = p.playing ? 'translating' : 'listening'; }
  $('#pill').dataset.state = st;
}
/* ---------- poll ---------- */
// Adaptive cadence: the caption is the product's fastest signal, so during a
// live session the poll runs at 70 ms (worst-case token→screen ≈ 70 ms vs the
// old 150); idle it relaxes to 250 ms so a parked app costs less CPU. `var`
// (not let) on purpose — the first poll() can run before a `let` here would
// be initialized (TDZ) and the delay expression sits OUTSIDE poll's try.
var pollFast=false;
// Every event reaches us TWICE: instantly via window.onVoxisEvent (Python's
// dispatcher thread) and again in the next poll() batch (the backstop). We drop
// the second copy by its `seq` — a per-event identity minted in Python.
//
// This used to dedupe on the event's CONTENT (type + JSON of the payload), which
// could not tell a duplicate DELIVERY from a genuinely repeated EVENT. Two
// identical caption deltas in a row (a space, a comma, a repeated word) lost the
// second one — the same silent word-drop the wordQueue experiment was reverted
// for. Worse, the fixed-payload events (quota_refresh, quota_wall, review,
// daily_wall all carry a constant null) could only ever fire ONCE per window.
const seenSeq = new Set();
function seqAlreadyHandled(seq) {
  if(typeof seq !== 'number') return false;   // no seq → never suppress
  if(seenSeq.has(seq)) return true;
  seenSeq.add(seq);
  // A set, not a high-water mark: a push dropped under queue overflow can make
  // the poll copy arrive out of order, and a watermark would eat it.
  if(seenSeq.size > 600) {
    const iter = seenSeq.values();
    for(let i = 0; i < 200; i++) {
      const v = iter.next().value;
      if(v === undefined) break;
      seenSeq.delete(v);
    }
  }
  return false;
}
function dispatchUIMessage(msg) {
  if(!msg) return;
  // {seq, ev:[...]} is the only shape Python emits now; a bare array would mean
  // a stale payload, so pass it through undeduped rather than dropping it.
  const ev = Array.isArray(msg) ? msg : msg.ev;
  if(!Array.isArray(msg) && seqAlreadyHandled(msg.seq)) return;
  dispatchUIEvent(ev);
}
function dispatchUIEvent(ev) {
  if(!ev || !Array.isArray(ev)) return;
  if(ev[0]==='status'){ addSys(ev[1], ev[2] && ev[2].level); }
  else if(ev[0]==='trans'){ onTrans(ev[1], ev[2], ev[3], ev[4], ev[5]); }
  else if(ev[0]==='src'){ onSrc(ev[1], ev[2], ev[3]); }
  else if(ev[0]==='hear_live'){ onHearLive(ev[1]); }
  else if(ev[0]==='saved'){ addTranscriptActions(ev[1]); }
  else if(ev[0]==='quota_refresh'){ refreshQuotaAfterSession(); }
  else if(ev[0]==='quota_wall'){ showPaywallCard(); }
  else if(ev[0]==='review'){ showReviewCard(); }
  else if(ev[0]==='preview'){ onPreviewEvent(ev[1]); }
  else if(ev[0]==='taste_wall'){ openTasteWall(ev[1] && ev[1].mode); }
  else if(ev[0]==='daily_wall'){ openDailyWall(); }
  else if(ev[0]==='device_blocked'){ openDeviceBlockWall(ev[1]); }
  else if(ev[0]==='update_available'){ showUpdateBadge(ev[1] && ev[1].version); }
}
// Shown once per launch when the background app.json check (webui._check_app_manifest)
// finds a newer published version than APP_VERSION. Purely informational — Voxis has
// no self-updater; clicking opens the same Store listing the Store itself updates from.
function showUpdateBadge(version){
  if(!version) return;
  const b = $('#updatebadge');
  if(!b) return;
  b.textContent = T('new_version_available').replace('{v}', version);
  b.style.display = '';
}
window.onVoxisEvent = function(msg) { dispatchUIMessage(msg); };
async function poll(){
  try{
    const p = await api().poll();
    // Reconcile the maximize button glyph/label with the REAL window state
    // (OS double-click / Win+Up / restore-on-launch don't go through the button).
    if(typeof p.maximized==='boolean' && winMaxed!==p.maximized){
      winMaxed=p.maximized; applyWinMaxUI(); document.body.classList.toggle('win-maximized', winMaxed);
    }
    p.events.forEach(dispatchUIMessage);
    if(scOpen) driveSoundcheck(p.sc, p.sc_mic);
    $('#badge').textContent = p.badge.text;
    setPillState(p);
    const liveSession = !!p.mode;
    if(liveSession && !SESSION_LIVE){ limitShown=false; warn80Shown=false; sessionT0=Date.now(); contrastLines=0; }  // new session → re-arm paywall + toast
    if(!liveSession && SESSION_LIVE){
      // Session just ended: close the loop with how long it ran.
      { const h=$('#hearline'); if(h) h.remove(); }
      if(sessionT0) addSys(T('session_summary').replace('{m}', String(Math.max(1, Math.round((Date.now()-sessionT0)/60000)))));
      // THE moment the user is reliably in front of Voxis: they just came back to
      // press Stop. Someone who set up a session and went to watch a film full
      // screen never saw anything we drew mid-session.
      offerContrast();
    }
    if(liveSession) maybeOfferContrast();
    // The Kaydet chip is THE save affordance (the rail card is gone): visible
    // whenever there are turns to save — during and after a session.
    $('#savechip').classList.toggle('on', !!document.querySelector('#scroll .turn'));
    SESSION_LIVE = liveSession;
    renderWaitState(p);
    pollFast = liveSession;
    targetLevel = Number(p.level) || 0;
    $('#vad').classList.toggle('live', liveSession);
    const hasInputSignal = liveSession && targetLevel > 0.02;
    $('#vad').classList.toggle('signal', hasInputSignal);
    const vadLabel = p.vad ? T('vad_speaking')
      : !p.mode ? T('waiting_signal')
      : p.mode==='video'
        ? T(hasInputSignal ? 'system_audio_detected' : 'waiting_system_audio')
        : T(hasInputSignal ? 'input_audio_detected' : 'waiting_for_speech');
    $('#vadtxt').textContent = vadLabel;
    $('#vad').setAttribute('aria-label', vadLabel);
    $('#presence').classList.toggle('on', liveSession);
    if(liveSession) startMeter(); else if(meterRAF) stopMeter();
    // Reduced-motion users get no rAF loop; still surface the input-level readout
    // each poll (the per-frame oscillation is what we skip, not the dB value).
    if(RM){ $('#meterdb').textContent = liveSession ? dbText(targetLevel) : '−∞ dB'; }
    // Just "● live". The latency number used to render here permanently —
    // an on-screen proof of lag that reframed simultaneous interpretation as
    // lateness. The one-time first-session note still sets the expectation.
    $('#streamhint').innerHTML = liveSession ? ('<span class="lv">●</span> '+T('live')) : '';
    document.querySelectorAll('.scenario').forEach(b=>{
      b.classList.toggle('active', b.dataset.mode===p.mode);
      // Only hard-disable while a session is active. Quota-blocked tiles stay
      // clickable so the click can surface real feedback (see rejectQuota);
      // their blocked state is conveyed via aria-disabled + .quota-blocked.
      b.disabled = !!p.mode;
    });
    $('#stopbtn').disabled = !p.mode;
    // Outgoing language only feeds Meeting mode; lock it during a video
    // session so the UI can't imply two-way translation there.
    $('#send').disabled = (p.mode==='video');
    applySendDim(p.mode==='video' || previewSendDim);
    // Video/Game translates the system mix; its microphone selector is not an
    // input to this mode. Make that explicit while the session is running.
    $('#mic').disabled = (p.mode==='video');
    $('#mic-label').textContent = p.mode==='video' ? T('mic_meeting_only') : T('mic');
    { const mo=$('#monitor-outgoing'), wrap=$('#monitor-outgoing-wrap');
      if(mo) mo.disabled=(p.mode==='video');
      if(wrap) wrap.style.opacity=(p.mode==='video') ? '.45' : ''; }
    // Virtual-mic caveat is contextual: Meeting hover/focus (CSS) or live.
    $('#meeting-caveat').classList.toggle('show', p.mode==='meeting');
  }catch(e){}
  setTimeout(poll, pollFast ? 70 : 250);
}
/* ── BOOT ────────────────────────────────────────────────────────────────── */
// Localize the static chrome before anything renders so the first paint is in
// the detected language, not hardcoded Turkish.
applyI18n(LANG);
applyWinMaxUI();
async function bootAuth(){
  showAuthBoot();
  try{
    const auth = await api().check_auth();
    if(auth.authenticated){ QUOTA=auth.quota; hideLoginOverlay(); await init(); renderQuotaBadge(QUOTA); applyQuotaGate(QUOTA); }
    else if(auth.offline){ showAuthOffline(); }
    else { showLoginOverlay('login'); }
  } catch(e){ showLoginOverlay('login'); }
}
window.addEventListener('pywebviewready', bootAuth);
if(window.pywebview && window.pywebview.api) bootAuth();


