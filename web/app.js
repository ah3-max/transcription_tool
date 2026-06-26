/* 原生前端行為 + API 串接（S-11，從 v6 雛形拆出）。
   同源相對路徑 /api（D-11，免烤 base URL）；回應外型 {data, error?, message?}。
   live/rec 舞台維持視覺 stub（S-06/S-07）；設定/批次/文件生成/匯出接真實 API。 */
(function(){
  var T = window.I18N;                 // 字典與翻譯
  function t(k){ return T.t(k); }
  var $ = function(id){ return document.getElementById(id); };

  // ── 小工具 ──
  function esc(s){ return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  // ── 統一錯誤／提示 toast（S-10）：取代散落 alert，自動消失、可手動關 ──
  function showToast(msg, kind){
    var wrap=$('toastWrap'); if(!wrap){ return; }
    var el=document.createElement('div'); el.className='toast'+(kind?(' '+kind):'');
    el.innerHTML='<span class="tx">'+esc(msg||t('err.generic'))+'</span><button class="tc" aria-label="close">×</button>';
    var kill=function(){ if(el.parentNode){ el.parentNode.removeChild(el); } };
    el.querySelector('.tc').addEventListener('click', kill);
    wrap.appendChild(el);
    setTimeout(kill, kind==='err'?6000:4000);
  }

  // ── API 層 ──
  var api = {
    async json(method, path, body){
      var opt = { method: method, headers: {} };
      if (body !== undefined){ opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
      var r = await fetch('/api' + path, opt);
      var data = null;
      try { data = await r.json(); } catch(e){ data = {}; }
      if (!r.ok) throw new Error((data && data.message) || t('err.generic'));
      return data;
    },
    async form(method, path, formData){
      var r = await fetch('/api' + path, { method: method, body: formData });
      var data = null;
      try { data = await r.json(); } catch(e){ data = {}; }
      if (!r.ok) throw new Error((data && data.message) || t('err.generic'));
      return data;
    }
  };

  // 下載：fetch→檢查 res.ok→blob→觸發下載（問題 F）。失敗用 msgEl 顯示友善訊息、不整頁跳走。
  async function download(path, filename, msgEl){
    if(msgEl) msgEl.textContent='';
    try {
      var r = await fetch('/api' + path);
      if(!r.ok){
        var m = t('dl.fail');
        try { var j = await r.json(); if(j && j.message) m = j.message; } catch(e){}
        if(msgEl) msgEl.textContent = m; else showToast(m,'err');
        return;
      }
      var blob = await r.blob();
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url; a.download = filename || 'download';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function(){ URL.revokeObjectURL(url); }, 1000);
    } catch(e){
      if(msgEl) msgEl.textContent = t('dl.fail'); else showToast(t('dl.fail'),'err');
    }
  }

  var FN_LABEL = { asr:'fn.asr', batch_tr:'fn.btr', live_tr:'fn.rtr', post:'fn.post' };

  // ══════════════════════════ 導覽與面板 ══════════════════════════
  function crumb(){ var a=document.querySelector('#nav button.on'); if(a) $('crumb').textContent = t('nav.'+a.dataset.p); }
  function show(p){
    document.querySelectorAll('.panel').forEach(function(el){el.classList.toggle('on', el.id==='p-'+p);});
    document.querySelectorAll('#nav button').forEach(function(b){b.classList.toggle('on', b.dataset.p===p);});
    document.querySelectorAll('#mnav button').forEach(function(b){b.classList.toggle('on', b.dataset.p===p);});
    crumb(); document.querySelector('.main').scrollTop=0;
    if(p==='live'){ checkLiveReadiness(); }
    if(p==='set'){ loadEndpoints(); }
    if(p==='batch'){ loadJobs(); }
    if(p==='gen'){ loadTranscriptSources(); loadRecords(); }
  }
  document.querySelectorAll('#nav button, #mnav button').forEach(function(b){ b.addEventListener('click', function(){ show(b.dataset.p); }); });

  // ══════════════════════════ i18n ══════════════════════════
  function applyLang(L){
    T.setLang(L);
    document.querySelectorAll('[data-i18n]').forEach(function(el){ el.textContent=t(el.getAttribute('data-i18n')); });
    document.querySelectorAll('[data-i18ngrp]').forEach(function(el){ el.label=t(el.getAttribute('data-i18ngrp')); });
    crumb();
    if(srcToggle) srcToggle.textContent = (stageEl && stageEl.classList.contains('with-src')) ? t('live.srcWord')+' ◂' : t('live.srcWord')+' ▸';
    if(progBtn) progBtn.textContent = (progDetail && progDetail.style.display==='none') ? t('batch.expand') : t('batch.collapse');
    var u1=$('uiLang'),u2=$('uiLang2'); if(u1)u1.value=L; if(u2)u2.value=L;
    document.documentElement.lang = L==='zh'?'zh-Hant':(L==='th'?'th':'en');
  }
  ['uiLang','uiLang2'].forEach(function(id){ var el=$(id); if(el) el.addEventListener('change', function(){ applyLang(el.value); }); });

  // ── segmented / format chips / 複選 chip（視覺） ──
  document.querySelectorAll('.seg, .pv-fmt').forEach(function(seg){
    seg.querySelectorAll('button').forEach(function(b){ b.addEventListener('click', function(){ seg.querySelectorAll('button').forEach(function(x){x.classList.toggle('on', x===b);}); }); });
  });
  document.querySelectorAll('.chk').forEach(function(c){ c.addEventListener('click', function(){ c.classList.toggle('on'); }); });

  // ── 資源用量：預設隱藏（FR-24/plan 驗收），眼睛切換；輪詢 /api/resources ──
  var EYE='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>';
  var EYEOFF='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3l18 18"/><path d="M10.6 5.1A10.9 10.9 0 0 1 12 5c6.5 0 10 7 10 7a18 18 0 0 1-3.2 4.1M6.3 6.3A18 18 0 0 0 2 12s3.5 7 10 7a10.9 10.9 0 0 0 4-.8"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';
  var res=$('res'), resBtn=$('resToggle');
  if(res) res.classList.add('hide');                       // 預設隱藏
  if(resBtn){ resBtn.innerHTML=EYEOFF; resBtn.addEventListener('click', function(){ var h=res.classList.toggle('hide'); resBtn.innerHTML=h?EYEOFF:EYE; if(!h) pollResources(); }); }

  function setMeter(idx, pct){
    var meters = res ? res.querySelectorAll('.meter') : [];
    var m = meters[idx]; if(!m) return;
    var bar = m.querySelector('.track i'), lbl = m.querySelector('.mpct');
    if(pct == null){ if(lbl) lbl.textContent='N/A'; if(bar) bar.style.width='0%'; return; }
    pct = Math.round(pct);
    if(bar){ bar.style.width = pct + '%'; bar.classList.toggle('hot', pct >= 80); }
    if(lbl) lbl.textContent = pct + '%';
  }
  async function pollResources(){
    if(!res || res.classList.contains('hide')) return;     // 隱藏時不打 API
    try {
      var d = (await api.json('GET','/resources')).data || {};
      setMeter(0, d.gpu && d.gpu.used_pct != null ? d.gpu.used_pct : (d.gpu && d.gpu.length ? d.gpu[0].used_pct : null));
      setMeter(1, d.ram ? d.ram.used_pct : null);
    } catch(e){ /* 取不到資源不擋服務（FR-24） */ }
  }
  setInterval(pollResources, 5000);

  // ══════════════════════════ 即時就緒檢查／降級（S-10） ══════════════════════════
  // 連線前查 /resources/live-readiness：不足→顯示橫幅、停即時、引導手動錄音。
  // 連線中資源掉線的 degraded 下行訊號由 S-06 WS 處理（約定已凍結，見 plan-log）。
  var liveReady=true;
  function setLiveDegraded(reasons){
    var banner=$('liveBanner'); if(!banner) return;
    liveReady = !reasons || !reasons.length;
    var startBtn=$('startStream');
    if(liveReady){
      banner.style.display='none';
      if(startBtn) startBtn.disabled=false;
    } else {
      var rEl=$('liveBannerReason');
      if(rEl) rEl.textContent = reasons.map(function(c){ return t('degrade.'+c); }).join('、');
      banner.style.display='flex';
      if(startBtn) startBtn.disabled=true;
    }
  }
  async function checkLiveReadiness(){
    try {
      var d=(await api.json('GET','/resources/live-readiness')).data || {};
      setLiveDegraded(d.ready ? [] : (d.reasons||[]));
    } catch(e){ /* 查不到就緒狀態時不擋既有畫面（FR-24 精神） */ }
  }
  var liveToBatch=$('liveToBatch');
  if(liveToBatch) liveToBatch.addEventListener('click', function(){ show('batch'); });

  // ══════════════════════════ 即時舞台（stub，S-06） ══════════════════════════
  var setup=$('live-setup'), stageWrap=$('live-stage-wrap');
  var timerEl=$('recTimer'), tHandle=null, tSecs=0;
  function pad(n){return (n<10?'0':'')+n;} function fmtT(s){return pad(Math.floor(s/3600))+':'+pad(Math.floor(s%3600/60))+':'+pad(s%60);}
  var startBtn=$('startStream');
  if(startBtn) startBtn.addEventListener('click', function(){ if(!liveReady){ showToast(t('degrade.title'),'err'); return; } setup.style.display='none'; stageWrap.style.display='block'; tSecs=0; timerEl.textContent=fmtT(0); tHandle=setInterval(function(){tSecs++;timerEl.textContent=fmtT(tSecs);},1000); });
  var stopBtn=$('stopStream');
  if(stopBtn) stopBtn.addEventListener('click', function(){ if(tHandle){clearInterval(tHandle);tHandle=null;} stageWrap.style.display='none'; setup.style.display='block'; });
  var srcToggle=$('srcToggle'), stageEl=$('stage');
  if(srcToggle) srcToggle.addEventListener('click', function(){ var on=stageEl.classList.toggle('with-src'); srcToggle.textContent=(on?t('live.srcWord')+' ◂':t('live.srcWord')+' ▸'); });
  var stageMain=$('stageMain'), cap=26;
  document.querySelectorAll('.stage-font').forEach(function(b){ b.addEventListener('click', function(){ cap=b.getAttribute('data-d')==='up'?Math.min(cap+2,40):Math.max(cap-2,16); stageMain.style.setProperty('--cap',cap+'px'); }); });
  var outLang=$('outLang');
  if(outLang) outLang.addEventListener('change', function(){ var k=outLang.value; document.querySelectorAll('#stageMain .s-primary').forEach(function(p){ var v=p.getAttribute('data-'+k); if(v) p.textContent=v; }); });

  // ── 錄音記錄頁 tabs + 摘要載入（stub，S-07） ──
  var recTabs=$('recTabs'), recT=$('recTranscript'), recS=$('recSummary');
  var recLoad=$('recLoading'), recSC=$('recSummaryContent'), sumTimer=null;
  if(recTabs) recTabs.querySelectorAll('button').forEach(function(b){ b.addEventListener('click', function(){
    if(b.dataset.rt==='s'){ recT.style.display='none'; recS.style.display='block'; recLoad.style.display='flex'; recSC.style.display='none'; if(sumTimer)clearTimeout(sumTimer); sumTimer=setTimeout(function(){recLoad.style.display='none';recSC.style.display='block';},2000); }
    else { recS.style.display='none'; recT.style.display='block'; }
  }); });

  // ══════════════════════════ 批次逐字稿 ══════════════════════════
  var batchMode=$('batchMode');
  if(batchMode) batchMode.querySelectorAll('button').forEach(function(b){ b.addEventListener('click', function(){ var nw=b.dataset.bm==='new'; $('batch-new').style.display=nw?'block':'none'; $('batch-hist').style.display=nw?'none':'block'; if(!nw) loadHistory(); }); });
  var progBtn=$('progBtn'), progDetail=$('progDetail');
  if(progBtn) progBtn.addEventListener('click', function(){ var h=progDetail.style.display==='none'; progDetail.style.display=h?'block':'none'; progBtn.textContent=h?t('batch.collapse'):t('batch.expand'); });
  var batchLang=$('batchLang');
  if(batchLang) batchLang.querySelectorAll('button').forEach(function(b){ b.addEventListener('click', function(){ var zh=b.dataset.bl==='zh'; $('batchZh').style.display=zh?'block':'none'; $('batchTh').style.display=zh?'none':'block'; }); });
  function setFmt(ids, f){ ids.forEach(function(id){ var el=$(id); if(el){ el.classList.remove('fmt-doc','fmt-md','fmt-txt','fmt-pdf'); el.classList.add('fmt-'+f); } }); }
  var batchFmt=$('batchFmt');
  if(batchFmt) batchFmt.querySelectorAll('button').forEach(function(b){ b.addEventListener('click', function(){ setFmt(['batchZh','batchTh'], b.dataset.fmt); }); });

  // ── 上傳：拖放 + 點擊（隱藏 input） ──
  function attachPicker(dropId, opts){
    var drop=$(dropId); if(!drop) return null;
    var input=document.createElement('input'); input.type='file';
    if(opts.accept) input.accept=opts.accept;
    if(opts.multiple) input.multiple=true;
    input.style.display='none'; drop.parentNode.appendChild(input);
    drop.style.cursor='pointer';
    drop.addEventListener('click', function(){ input.click(); });
    input.addEventListener('change', function(){ opts.onpick(input.files); });
    drop.addEventListener('dragover', function(e){ e.preventDefault(); drop.style.borderColor='var(--teal)'; });
    drop.addEventListener('dragleave', function(){ drop.style.borderColor=''; });
    drop.addEventListener('drop', function(e){ e.preventDefault(); drop.style.borderColor=''; if(e.dataTransfer.files.length) opts.onpick(e.dataTransfer.files); });
    return { input:input };
  }

  var batchFiles=[];
  attachPicker('batchDrop', { accept:'.mp3,.mp4,.m4a,.wav', multiple:true, onpick:function(files){
    batchFiles=Array.prototype.slice.call(files);
    $('batchFiles').textContent = batchFiles.map(function(f){return f.name;}).join('、');
  }});

  var batchSubmit=$('batchSubmit');
  if(batchSubmit) batchSubmit.addEventListener('click', async function(){
    var msg=$('batchMsg');
    if(!batchFiles.length){ msg.textContent=t('batch.needFile'); return; }
    var srcBtn=document.querySelector('#batchSrcSeg button.on'); var src=srcBtn?srcBtn.dataset.src:'zh';
    var outs=[]; document.querySelectorAll('#batchOutChk .chk.on').forEach(function(c){ outs.push(c.dataset.lang); });
    if(!outs.length){ msg.textContent=t('batch.needOut'); return; }
    var fd=new FormData();
    batchFiles.forEach(function(f){ fd.append('files', f); });
    fd.append('src_lang', src); fd.append('out_langs', outs.join(','));
    msg.textContent=t('batch.uploading'); batchSubmit.disabled=true;
    try {
      await api.form('POST','/jobs', fd);
      msg.textContent=t('batch.queued');
      batchFiles=[]; $('batchFiles').textContent='';
      loadJobs();
    } catch(e){ msg.textContent = e.message || t('err.generic'); }
    finally { batchSubmit.disabled=false; }
  });

  function stClass(s){ return s==='done'?'done':(s==='running'?'run':(s==='error'?'wait':'wait')); }
  function stLabel(s){ return s==='done'?t('st.done'):(s==='running'?t('st.running'):(s==='error'?t('st.error'):t('st.queued'))); }

  async function loadJobs(){
    var box=$('progDetail'); if(!box) return;
    try {
      var rows=(await api.json('GET','/jobs?limit=50')).data || [];
      if(!rows.length){ box.innerHTML='<p class="muted">'+esc(t('batch.empty'))+'</p>'; return; }
      box.innerHTML = rows.map(function(j){
        return '<div class="qrow"><div class="qname">'+esc(j.original_name)+'<small>'+esc(j.job_id)+'</small></div>'+
               '<div class="barwrap"><div class="bar"><i style="width:'+(j.status==='done'?100:(j.status==='running'?50:0))+'%"></i></div></div>'+
               '<span class="st '+stClass(j.status)+'">'+esc(stLabel(j.status))+'</span></div>';
      }).join('');
    } catch(e){ box.innerHTML='<p class="muted">'+esc(e.message)+'</p>'; }
  }

  async function loadHistory(){
    var box=$('histList'); if(!box) return;
    try {
      var rows=(await api.json('GET','/jobs?limit=50')).data || [];
      var cnt=$('histCount'); if(cnt) cnt.textContent=rows.length;
      if(!rows.length){ box.innerHTML='<p class="muted">'+esc(t('batch.empty'))+'</p>'; return; }
      // 用彙整端點一次撈 transcript＋translation 產出，依 job 分組（避免逐筆 N+1，問題 A/E）
      var byJob={};
      var kinds=['transcript','translation'];
      for(var ki=0; ki<kinds.length; ki++){
        var outs=(await api.json('GET','/jobs/outputs?kind='+kinds[ki]+'&limit=500')).data || [];
        outs.forEach(function(o){ (byJob[o.job_id]||(byJob[o.job_id]=[])).push(o); });
      }
      box.innerHTML = '<p class="muted" id="histMsg" style="margin:0 0 8px"></p>' + rows.map(function(j){
        // 依「實際 outputs」生鈕：來源語言給 transcript、其餘給 translation，URL 用實際 kind（問題 A）
        var outs=byJob[j.job_id]||[];
        var acts = outs.length
          ? outs.map(function(o){
              return '<button class="ic" data-job="'+esc(j.job_id)+'" data-kind="'+esc(o.kind)+'"'+
                     ' data-lang="'+esc(o.lang||'')+'" data-fmt="'+esc(o.fmt||'docx')+'">'+
                     esc(t('kind.'+o.kind))+' '+esc(o.lang||'')+'</button>';
            }).join('')
          : '<span class="muted">'+esc(t('hist.noOutput'))+'</span>';
        return '<div class="ses"><div class="nm">'+esc(j.original_name)+'<small>'+esc(j.job_id)+' · '+esc(stLabel(j.status))+'</small></div>'+
               '<span class="meta">'+esc(stLabel(j.status))+'</span><div class="act">'+acts+'</div></div>';
      }).join('');
      box.querySelectorAll('button[data-job]').forEach(function(b){
        b.addEventListener('click', function(){
          var fmt=b.dataset.fmt||'docx';
          var path='/jobs/'+encodeURIComponent(b.dataset.job)+'/export?fmt='+encodeURIComponent(fmt)+
                   '&kind='+encodeURIComponent(b.dataset.kind)+'&lang='+encodeURIComponent(b.dataset.lang);
          download(path, b.dataset.job+'_'+b.dataset.kind+'_'+b.dataset.lang+'.'+fmt, $('histMsg'));
        });
      });
    } catch(e){ box.innerHTML='<p class="muted">'+esc(e.message)+'</p>'; }
  }

  // ══════════════════════════ 文件生成（S-08） ══════════════════════════
  var genSrc=$('genSrc');
  if(genSrc) genSrc.querySelectorAll('button').forEach(function(b){ b.addEventListener('click', function(){ var pick=b.dataset.gs==='pick'; $('gen-pick').style.display=pick?'block':'none'; $('gen-up').style.display=pick?'none':'block'; }); });

  var TPL_MAP={ meet:'meeting', care:'handover', up:'custom' };
  var curTplKey='meet';
  var genTpl=$('genTpl'), genTag=$('genTag');
  if(genTpl) genTpl.querySelectorAll('button').forEach(function(b){ b.addEventListener('click', function(){
    var tpl=b.dataset.tpl; curTplKey=tpl;
    $('gen-tpl-up').style.display = tpl==='up'?'block':'none';
    var meet=$('genDocMeet'), care=$('genDocCare'), result=$('genResult');
    result.style.display='none';                            // 換範本→回到結構示意
    if(tpl==='care'){ meet.style.display='none'; care.style.display='block'; genTag.textContent=t('tpl.care'); }
    else if(tpl==='up'){ meet.style.display='block'; care.style.display='none'; genTag.textContent=t('tpl.custom'); }
    else { meet.style.display='block'; care.style.display='none'; genTag.textContent=t('tpl.meet'); }
  }); });

  var genFmt=$('genFmt');
  if(genFmt) genFmt.querySelectorAll('button').forEach(function(b){ b.addEventListener('click', function(){ setFmt(['genDocMeet','genDocCare','genResult'], b.dataset.fmt); }); });

  var genTranscriptFile=null, genTemplateFile=null;
  attachPicker('genUpDrop', { accept:'.txt,.md,.docx', onpick:function(files){ genTranscriptFile=files[0]; $('genUpName').textContent=files[0].name; }});
  attachPicker('genTplDrop', { accept:'.md,.docx', onpick:function(files){ genTemplateFile=files[0]; $('genTplName').textContent=files[0].name; }});

  async function loadTranscriptSources(){
    // 來源下拉：列出既有 transcript 產出（S-04/05 落檔後才有；目前可能為空）
    var sel=$('genSrcSelect'); if(!sel) return;
    var batchGrp=sel.querySelector('optgroup[data-i18ngrp="nav.batch"]');
    if(!batchGrp) return;
    try {
      // 單次彙整端點取所有 transcript 產出（含 job 原檔名），不再逐 job N+1（問題 E）
      var outs=(await api.json('GET','/jobs/outputs?kind=transcript&limit=500')).data || [];
      batchGrp.innerHTML = outs.map(function(o){
        return '<option value="'+esc(o.id)+'">'+esc(o.original_name)+' — '+esc(o.lang||'')+'</option>';
      }).join('');
    } catch(e){ /* 靜默：來源為空不擋頁 */ }
  }

  var genBtn=$('genBtn');
  if(genBtn) genBtn.addEventListener('click', async function(){
    var msg=$('genMsg'), tplKey=TPL_MAP[curTplKey]||'meeting';
    var usingManual = $('gen-up').style.display!=='none';
    var fd=new FormData(); fd.append('template', tplKey);
    if(usingManual){
      if(!genTranscriptFile){ msg.textContent=t('gen.needSrc'); return; }
      fd.append('transcript_file', genTranscriptFile);
    } else {
      var sel=$('genSrcSelect'); var oid=sel && sel.value;
      if(!oid){ msg.textContent=t('gen.needSrc'); return; }
      fd.append('ref_output_id', oid);
    }
    if(tplKey==='custom'){
      if(!genTemplateFile){ msg.textContent=t('gen.needTpl'); return; }
      fd.append('custom_template_file', genTemplateFile);
    }
    msg.textContent=t('gen.generating'); genBtn.disabled=true;
    try {
      var d=(await api.form('POST','/records', fd)).data;
      lastRecordId=d.output_id;
      var result=$('genResult');
      $('genDocMeet').style.display='none'; $('genDocCare').style.display='none';
      result.textContent=d.content; result.style.display='block';
      genTag.textContent=t('gen.done');
      msg.textContent='';
      loadRecords();                                      // 重新整理已生成記錄清單（問題 B）
    } catch(e){
      // 409 多為未設定 post 端點
      msg.textContent = /endpoint|post/i.test(e.message) ? t('gen.noEndpoint') : (e.message || t('err.generic'));
    } finally { genBtn.disabled=false; }
  });

  var lastRecordId=null;
  var genExportBtn=$('genExportBtn');
  if(genExportBtn) genExportBtn.addEventListener('click', function(){
    if(!lastRecordId){ $('genMsg').textContent=t('gen.needGen'); return; }
    var fmt=$('genExportFmt').value || 'docx';
    download('/records/'+encodeURIComponent(lastRecordId)+'/export?fmt='+encodeURIComponent(fmt),
             lastRecordId+'.'+fmt, $('genMsg'));
  });

  // ── 已生成記錄清單（問題 B）：重整後仍可重新匯出 ──
  async function loadRecords(){
    var box=$('recordsList'); if(!box) return;
    try {
      var rows=(await api.json('GET','/records?limit=50')).data || [];
      if(!rows.length){ box.innerHTML='<p class="muted">'+esc(t('gen.histEmpty'))+'</p>'; return; }
      box.innerHTML = '<p class="muted" id="recMsg" style="margin:0 0 8px"></p>' + rows.map(function(r){
        var when=r.created_at ? new Date(r.created_at*1000).toLocaleString() : '';
        return '<div class="ses"><div class="nm">'+esc(t('kind.record'))+
               '<small>'+esc(r.id)+' · '+esc(when)+'</small></div>'+
               '<span class="meta">'+esc(r.ref_type||'')+'</span>'+
               '<div class="act"><button class="ic" data-rid="'+esc(r.id)+'" data-fmt="docx">docx</button>'+
               '<button class="ic" data-rid="'+esc(r.id)+'" data-fmt="md">md</button>'+
               '<button class="ic" data-rid="'+esc(r.id)+'" data-fmt="txt">txt</button></div></div>';
      }).join('');
      box.querySelectorAll('button[data-rid]').forEach(function(b){
        b.addEventListener('click', function(){
          download('/records/'+encodeURIComponent(b.dataset.rid)+'/export?fmt='+encodeURIComponent(b.dataset.fmt),
                   b.dataset.rid+'.'+b.dataset.fmt, $('recMsg'));
        });
      });
    } catch(e){ box.innerHTML='<p class="muted">'+esc(e.message)+'</p>'; }
  }

  // ══════════════════════════ 一般設定：端點 CRUD ══════════════════════════
  var addBtn=$('addEpBtn'), addForm=$('addEpForm'), cancelEp=$('cancelEp');
  if(addBtn) addBtn.addEventListener('click', function(){ addForm.style.display='block'; });
  if(cancelEp) cancelEp.addEventListener('click', function(){ addForm.style.display='none'; });

  async function loadEndpoints(){
    var tb=$('epTable'), empty=$('epEmpty'); if(!tb) return;
    try {
      var rows=(await api.json('GET','/endpoints')).data || [];
      if(empty) empty.style.display = rows.length ? 'none' : 'block';
      tb.innerHTML = rows.map(function(e){
        return '<tr><td class="fn">'+esc(t(FN_LABEL[e.function]||e.function))+'</td>'+
               '<td><span class="sel">'+esc(e.model)+'</span></td>'+
               '<td class="mono">'+esc(e.url)+'</td>'+
               '<td><button class="ic" data-act="toggle" data-id="'+esc(e.id)+'" data-active="'+(e.active?'1':'0')+'">'+
                 esc(e.active?t('set.epOn'):t('set.epOff'))+'</button> '+
               '<button class="ic" data-act="del" data-id="'+esc(e.id)+'">'+esc(t('act.delete'))+'</button></td></tr>';
      }).join('');
      tb.querySelectorAll('button[data-act]').forEach(function(b){
        b.addEventListener('click', async function(){
          try {
            if(b.dataset.act==='del'){ await api.json('DELETE','/endpoints/'+encodeURIComponent(b.dataset.id)); }
            else { await api.json('PATCH','/endpoints/'+encodeURIComponent(b.dataset.id)+'?active='+(b.dataset.active==='1'?'false':'true')); }
            loadEndpoints();
          } catch(e){ showToast(e.message||t('err.generic'),'err'); }
        });
      });
    } catch(e){ if(empty){ empty.style.display='block'; empty.textContent=e.message; } }
  }

  var epSave=$('epSave');
  if(epSave) epSave.addEventListener('click', async function(){
    var body={ name:$('epName').value.trim(), url:$('epUrl').value.trim(),
               model:$('epModel').value.trim(), function:$('epFn').value, active:true };
    var msg=$('epMsg');
    if(!body.name||!body.url||!body.model){ msg.textContent=t('err.generic'); return; }
    epSave.disabled=true;
    try {
      await api.json('POST','/endpoints', body);
      $('epName').value=''; $('epUrl').value=''; $('epModel').value='';
      addForm.style.display='none'; msg.textContent='';
      loadEndpoints();
    } catch(e){ msg.textContent=e.message||t('err.generic'); }
    finally { epSave.disabled=false; }
  });

  // ── 波形（裝飾） ──
  var wave=document.querySelector('.wave'); if(wave){ for(var i=0;i<40;i++){var bar=document.createElement('i');bar.style.animationDelay=(i*0.05)+'s';wave.appendChild(bar);} }

  // ── 主題切換 ──
  var MOON='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  var SUN='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  var themeBtn=$('themeToggle');
  if(themeBtn){ themeBtn.innerHTML=MOON; themeBtn.addEventListener('click', function(){ var d=document.body.classList.toggle('dark'); themeBtn.innerHTML=d?SUN:MOON; }); }

  // ── init ──
  applyLang('zh');
  checkLiveReadiness();                                   // 預設即時頁，開頁即查就緒（S-10）
})();
