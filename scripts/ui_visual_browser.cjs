// Real App.vue, synthetic intercepted API only. Never connects to a business database.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const net = require('node:net');
const os = require('node:os');
const {createHash}=require('node:crypto');
const { spawn, execFileSync } = require('node:child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const playwrightVersion = require(path.join(process.env.PLAYWRIGHT_MODULE || require.resolve('playwright/package.json').replace(/package\.json$/, ''), 'package.json')).version;
const { baseline, check } = require('./ui_visual_integrity.cjs');
const root = path.resolve(__dirname, '..');
const head = execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim();
const fileHash=file=>createHash('sha256').update(require('node:fs').readFileSync(path.join(root,file))).digest('hex');
const output = process.env.BROWSER_ARTIFACT_DIR ? path.resolve(process.env.BROWSER_ARTIFACT_DIR)
  : path.join(root, 'frontend/coverage/ui-visual',head);
const screenshots=[];
const date = '2026-10-16', hash = 'a'.repeat(64);
const originalCSS = execFileSync('git', ['show', `${baseline}:frontend/src/style.css`], { cwd: root, encoding: 'utf8' });
const stock = { ts_code: '000001.SZ', name: '合成验收证券', trade_date: date, state: 'S4',
  opportunity_stage: 'TREND', opportunity_score: 82, right_side_score: 76, trend_score: 85,
  trend_rank_score: 90, rps60: 92, industry_name: '合成行业', sector_name: '合成行业',
  industry_heat: 72, primary_theme_name: '合成题材', primary_theme_heat: 70, market_score: 65,
  reason_codes: ['FROZEN_REASON', 'SOURCE_IDENTITY_REQUIRED'], extension_risk: 'NORMAL' };
const sector = { sector_id: 1, name: '合成行业', sector_name: '合成行业', trade_date: date,
  heat_score: 72, heat_rank: 1, rank_change: 2, lifecycle: 'RISING', heat_momentum3: 4 };
const theme = { theme_code: 'synthetic-theme', name: '合成题材', heat_score: 78, heat_rank: 1,
  lifecycle: 'RISING', heat_momentum3: 3, rank_change: 1, return1: .02, net_amount: 10000,
  limit_up_count: 2, continuous_limit_count: 1, breadth20: .6, rps60_median: 83 };
const risk = { max_positions: 10, max_single_position_weight: '0.1', min_cash_ratio: '0.02',
  max_new_positions_per_day: 2, max_sector_weight: '0.3', max_theme_weight: '0.3', max_daily_turnover: '0.5' };
const identity = { run_id: 'run-a', performance_id: 'p1', risk_id: 'r1', trade_id: 't1', period_id: 'x1' };
const runs = ['a', 'b'].map(id => ({ id: `run-${id}`, name: `合成回测 ${id}`, account_mode: 'BACKTEST',
  status: 'SUCCESS', start_date: '2026-01-01', end_date: date, initial_cash: '1000000', benchmark_code: '000300.SH' }));
const analytics = { schema_version: 'analytics_read_v1', identity, backtest: runs[0],
  performance: { cumulative_return: '.12', annualized_return: '.15', max_drawdown: '-.08', trade_days: 180 },
  risk: { benchmark_code: '000300.SH', excess_cumulative_return: '.04', sharpe_ratio: '1.2' },
  trade: { total_turnover: '1.2', total_execution_cost: '50.25', win_rate: '.6', profit_factor: '1.5', total_cost_to_initial_capital: '.00005' },
  warnings: [], source_versions: { period: 'period_v1' } };
const reference = { manifest_id: 'child', manifest_hash: hash, policy_version: 'm16.6-contract-manifest-v1',
  contract_count: 1, contract_scope: ['M14_EXACT_BUNDLE'], gap_codes: [], reproduction_level: 'FROZEN_CONTRACT_RECHECK' };
const verification = { archive_integrity: { status: 'VERIFIED' }, frozen_fact_recheck: { status: 'VERIFIED' },
  contract_integrity: { status: 'VERIFIED' }, contract_semantics: { status: 'VERIFIED', reason_codes: [] },
  comparison_permission: { allowed: false }, calculation_reproduced: false };
const reportSummary = { report_id: 'report-1', report_type: 'strategy_review', report_version: 'm16.6-report-v1',
  title: '合成冻结研究报告', as_of_date: date, source_answer_status: 'COMPLETED', source_chat_id: 'synthetic-chat',
  source_message_id: 'synthetic-message', snapshot_hash: hash, archived_at: null };
const navigation={view:'walk_forward',study_id:'synthetic-study',validation_id:'synthetic-validation',window_no:1,source_tool:'walk_forward.window_lineage'};
const citation={marker:'E1',evidence_id:'synthetic-evidence',evidence_version:'v2',tool_name:navigation.source_tool,entity_id:'synthetic-window',as_of_date:date,config_hash:hash,source_hash:hash,content_hash:hash,navigation};
const chat={chat_id:'synthetic-chat',title:'合成证据会话',status:'ACTIVE',created_at:'2026-10-16T08:00:00Z',updated_at:'2026-10-16T08:00:00Z'};
const message={message_id:'synthetic-message',source_request_id:'synthetic-request',sequence_no:2,role:'ASSISTANT',status:'COMPLETED',created_at:chat.created_at,content:'合成验收结论：仅核验冻结来源，不代表投资建议。',metadata:{answer_status:'COMPLETED',citations:[citation],verified_claims:[],tool_calls:[{tool_call_id:'synthetic-call',tool_name:navigation.source_tool,status:'SUCCESS',duration_ms:12}],warnings:['SYNTHETIC_FIXTURE']}};
const archive={archive_status:'COMPLETE',integrity:{status:'VERIFIED'},reproduction_level:'FROZEN_FACT_RECHECK',archived_evidence_count:1,required_evidence_count:1,warnings:[],evidence:[]};
const evidence={...citation,tool_version:'v1',tool_call_id:'synthetic-call',record_path:'window',created_at:chat.created_at};

function fixture(p, query, req, state) {
  const empty = state.mode === 'empty', failed = state.mode === 'error', extra=['evidence','recovery'].includes(state.mode);
  const meta = { total: 0, limit: 20, offset: Number(query.get('offset') || 0) };
  let data;
  if (p === '/auth/me') return state.signedIn ? { data: { username: 'synthetic-owner', must_change_password: state.mustChange }, meta }
    : { status: 401, data: null };
  if (p === '/auth/login') { state.signedIn = true; return { data: { username: 'synthetic-owner', must_change_password: false }, meta }; }
  if (p === '/auth/change-password') { state.mustChange = false; return { data: { username: 'synthetic-owner', must_change_password: false }, meta }; }
  if (p === '/auth/logout') { state.signedIn = false; return { data: {}, meta }; }
  if (failed && p === '/system/status') return { status: 503, data: null };
  if (p === '/system/status') data = Object.fromEntries(['trade', 'raw', 'factor', 'market', 'sector_factor', 'state', 'signal', 'signal_eval', 'opportunity'].map(k => [`latest_${k}_date`, date]));
  else if (p === '/system/runtime') data = { services: Object.fromEntries(['backend','database','worker','scheduler'].map(k => [k,{status:'UP'}])), queued_count: 0, running_count: 0, latest_raw_date: date, latest_analysis_date: date, latest_opportunity_date: date };
  else if (p === '/dashboard/summary') data = { trade_date: date, market: empty ? null : { market_score: 65, regime: 'NORMAL', up_count: 2800, down_count: 2100, flat_count: 100, up_rate: .56 }, sector_heat_top: empty ? [] : [sector], signal_counts: empty ? [] : [{ signal_type: 'RIGHT_SIDE_NEW', count: 8 }] };
  else if (p === '/system/data-coverage' || p === '/system/data-calendar') {
    data = empty ? [] : Array.from({length: 24}, (_, i) => ({ trade_date: `2026-10-${String(i+1).padStart(2,'0')}`, date: `2026-10-${String(i+1).padStart(2,'0')}`, is_open: i % 7 !== 0,
      coverage_status: ['CLOSED','MISSING','RAW_ONLY','ANALYZED','CORE_COMPLETE','OPPORTUNITY_COMPLETE','DEGRADED'][i%7],
      ...Object.fromEntries(['stock_daily','daily_basic','adj_factor','index_daily','factor','market','sector_factor','state','signal','signal_eval'].map(k=>[`${k}_rows`, i%7 ? 100 : 0])) }));
  } else if (p === '/jobs') data = empty ? [] : [{ id: 'job-1', job_type: 'BACKFILL', status: 'FAILED', started_at: '2026-10-16T01:00:00Z', finished_at: '2026-10-16T01:01:00Z', row_count: 100, step: 'source', metadata: {}, error_message: 'SYNTHETIC_SOURCE_NOT_READY · 长错误信息保留全部内容' }];
  else if (p.startsWith('/jobs/')) data = { id: 'queued-job', status: 'QUEUED', job_type: 'RECALCULATE', metadata: {} };
  else if (p.endsWith('/realtime-kline')) data = { stock, source: 'synthetic', stored: false, days: Number(query.get('days')), start: '2026-10-01', end: date, rows: empty ? [] : Array.from({length: 12},(_,i)=>({trade_date:`2026-10-${String(i+1).padStart(2,'0')}`,open:10+i/10,close:10.2+i/10,high:11+i/10,low:9+i/10})) };
  else if (p.startsWith('/stocks/') || p.startsWith('/opportunities/')) data = empty ? [] : [extra?{...stock,name:'合成长名称证券'.repeat(5),reason_codes:['LONG_REASON_'+ '冻结来源不得截断；'.repeat(24)]}:stock];
  else if (p === '/sectors/heat') data = empty ? [] : [sector];
  else if (p === '/themes') data = empty ? [] : [theme];
  else if (p.startsWith('/themes/')) data = { theme, factor: { ...theme, member_count: 20, eligible_member_count: 18, data_coverage: .9 }, member_context: { member_context_mode: 'SNAPSHOT', source_snapshot_date: date, member_context_coverage: .9 }, member_distribution: [{stage:'S4',count:2}], top_members: {trend:[stock]} };
  else if (p === '/research/signals/stats') data = { count: 25, avg_ret5: .01, avg_ret20: .03, win_rate20: .6, avg_mfe20: .08, avg_mae20: -.03, latest_evaluated_until_date: date };
  else if (p === '/research/status') data = { benchmark_code: '000300.SH', research_version: 'frozen', opportunity_eval_rows: 40, theme_eval_rows: 20, transition_eval_rows: 10, mature20_rows: 5, latest_evaluated_market_date: date };
  else if (p === '/research/evaluate') data = { id: 'research-job' };
  else if (p.startsWith('/research/')) data = empty ? [] : [{ group: '合成分组', event_count: 20, horizons: [5,10,20,60].map(horizon => ({horizon,mature_count:10,return_sample_count:10,avg_return:.03})) }];
  else if (p === '/portfolio/backtests') data = empty ? [] : runs;
  else if (p.endsWith('/analytics/summary')) data = { ...analytics, identity: {...identity,period_id:extra&&!state.periodGenerated?null:identity.period_id,run_id:p.split('/')[3]} };
  else if (p.endsWith('/analytics/series')) { data = []; Object.assign(meta, identity, {period_id:extra&&!state.periodGenerated?null:identity.period_id,run_id:p.split('/')[3], limit:500}); }
  else if (p.endsWith('/performance/period')) data = [];
  else if (p.endsWith('/performance/period/calculate')) {state.periodGenerated=true;data = { job_id: 'period-job', job_status: 'SUCCESS' };}
  else if (p.endsWith('/performance/trade/episodes')) { data = empty ? [] : [{ts_code:stock.ts_code,episode_no:1,status:'CLOSED',entry_date:'2026-10-01',exit_date:date,holding_trade_days:10,realized_pnl:'123.456789',unrealized_pnl_end:'0',episode_return:'.03',total_execution_cost:'5.20',classification:'WIN'}]; meta.total=data.length; }
  else if (p === '/portfolio/analytics/compare') data = {schema_version:'analytics_read_v1',items:[analytics, {...analytics,identity:{...identity,run_id:'run-b'}}]};
  else if (p.startsWith('/portfolio/walk-forwards/')) {data=p.endsWith('/windows')?[{window_no:1,status:'SUCCESS',train_start_date:'2026-01-01',train_end_date:'2026-06-30',test_start_date:'2026-07-01',test_end_date:date,train_date_hash:hash,test_date_hash:hash,selected_train_run_id:'run-a',oos_run_id:'run-b'}]:{status:'SUCCESS',window_count:1};meta.total=1;}
  else if (p === '/agent/status') data = { registry_version:'m16.3-v1', tool_count:9, llm_enabled:extra };
  else if (p === '/agent/chats') {data=req.method()==='POST'?chat:extra?[{...chat,status:state.chatArchived?'ARCHIVED':'ACTIVE'}]:[];meta.total=Array.isArray(data)?data.length:1;}
  else if (p.includes('/turn-archives/')) data=archive;
  else if(state.mode==='recovery'&&p.endsWith('/messages')&&req.method()==='POST')return {abort:true};
  else if(state.mode==='recovery'&&p.includes('/turns/')){
    if(state.recoveryStage!=='failed')return {status:404,code:'TURN_NOT_FOUND'};
    data={chat_id:chat.chat_id,request_id:p.split('/').pop(),status:'FAILED',error_code:'SYNTHETIC_FAILURE',content:'合成复核问题',started_at:chat.created_at};
  }
  else if (p.startsWith('/agent/chats/')) {
    if(req.method()==='DELETE')state.chatArchived=true;
    data=extra?{...chat,status:state.chatArchived?'ARCHIVED':'ACTIVE',messages:query.has('before_sequence')?[{...message,message_id:'older',sequence_no:1,role:'USER',content:'合成历史问题',metadata:{}}]:[message],active_turn:null}:{chat_id:'chat-new',title:'新会话',status:'ACTIVE',messages:[],active_turn:null};
    Object.assign(meta,{total:2,has_more:extra&&!query.has('before_sequence'),next_cursor:extra&&!query.has('before_sequence')?2:null});
  }
  else if (p === '/agent/reports') { data = empty ? [] : extra?[reportSummary,{...reportSummary,report_id:'report-2',title:'第二份合成冻结报告'}]:[reportSummary];if(query.has('type'))data=data.filter(r=>r.report_type===query.get('type'));meta.total=data.length; }
  else if (p.endsWith('/evidence')) { data=extra?[evidence]:[];Object.assign(meta,archive,{total:data.length}); }
  else if(p.includes('/evidence/'))data={...evidence,arguments_summary:{synthetic:true},frozen_facts:[{claim_id:'synthetic-claim',path:'nav',value:'1.123456789',unit:'decimal',entity:'run-a',trade_date:date,sample_role:'TRAIN'}]};
  else if(p.endsWith('/verify'))data={...archive,verification_level:'FROZEN_FACT_RECHECK',fact_recheck:{status:'VERIFIED',checked_claim_count:1,results:[]}};
  else if (p.endsWith('/contracts')) { data=[{contract_id:'contract-1',contract_kind:'M14_EXACT_BUNDLE',subject_id:'run-a',role:'TRAIN',schema_version:'frozen',contract_hash:hash,status:'VERIFIED',reason_codes:[]}]; Object.assign(meta,{total:1,check:verification}); }
  else if (p.endsWith('/verify-contracts')) data=verification;
  else if(p.includes('/contracts/'))data={contract_id:'contract-1',role:'TRAIN',contract_kind:'M14_EXACT_BUNDLE',contract_hash:hash,projection:{source_hash:hash,synthetic:true}};
  else if(p === '/agent/report-comparisons'){
    const mode=req.postDataJSON().comparison_mode||'AUTO',allowed=['STRICT_SAME_SAMPLE','WINDOW_DEGRADATION'].includes(mode);
    data={comparison_id:'synthetic-comparison',state:allowed?'COMPARABLE':'CONTEXT_REQUIRED',policy_version:'m16.6-report-comparison-v4',reason_codes:allowed?[]:['SYNTHETIC_CONTEXT_REQUIRED'],display_safety:{legacy_policy:false,delta_allowed:allowed},result:{facts:[{delta:'AUDIT_DELTA_MUST_NOT_RENDER'}]},display_result:{comparison_mode:mode,comparison_permissions:{allowed},contract_check:{left:verification,right:verification},facts:[{metric_key:'synthetic_score',left:'10',right:'12',delta:'2',pair_status:'COMPARABLE',comparison_permission:{allowed},formula:mode==='WINDOW_DEGRADATION'?'TRAIN_MINUS_OOS':'RIGHT_MINUS_LEFT'}]}};
  }
  else if (p.startsWith('/agent/reports/')) data={...reportSummary,source_contract:{snapshot_level:'FROZEN_TOOL_EVIDENCE'},snapshot:{claims:[],contract_reference:reference,sections:[{section_id:'one',title:'冻结结论',items:['仅合成验收数据'],claim_ids:[]}],charts:[],citations:[],warnings:['算法未重跑'],rejected_claims:[]}};
  else if (p === '/paper/status') data={enabled:state.mode!=='disabled',schema_ready:state.mode!=='schema',auto_approve:false,default_risk:risk,business_date:date,latest_raw_date:date};
  else if (p === '/paper/accounts') { data=empty?[]:[{id:'account',name:'合成模拟账户',state:'ACTIVE'}]; meta.total=data.length; }
  else if (p === '/paper/accounts/account') data={id:'account',name:'合成模拟账户',state:['PAUSED','CLOSED'].includes(state.mode)?state.mode:'ACTIVE',initial_cash:'1000000',benchmark_code:'000300.SH',first_trade_date:date,next_trade_date:'2026-10-19',latest_trade_date:null,config_snapshot_json:{paper:{risk}}};
  else if (p.endsWith('/performance')) data={continuous:false,series:[],latest:null,cumulative_cost:'0',cumulative_turnover:'0',realized_pnl:'0',unrealized_pnl:'0',benchmark_status:'UNAVAILABLE',financial_source_hash:hash,reason_codes:[],execution:{filled_orders:0,reached_orders:0,hypothetical_fill_rate:null,blocked_reasons:{},stages:{}}};
  else if (p === '/decisions/observations') { data=[{id:'observation',signal_date:date,data:{candidates:[{...stock,opportunity_score:'82',risk_codes:[],industry_sector_id:1,primary_theme_code:'synthetic-theme'}]}}]; meta.total=1; }
  else if (p === '/decisions/proposals') { data=[{id:'proposal',ts_code:stock.ts_code,state:'PENDING_REVIEW',stage:'RIGHT_SIDE_NEW',action:'PROPOSE_BUY',target_weight:'0.08',expires_at:'2026-10-19T01:30:00Z',data:{}}];meta.total=1; }
  else if(extra&&p.endsWith('/jobs/paper-job/cancel')){state.jobCancelled=true;data={id:'paper-job',status:'CANCELLED'};}
  else if(extra&&p.endsWith('/jobs')){data=[{id:'paper-job',job_type:'PAPER_DAILY',status:state.jobCancelled?'CANCELLED':'RUNNING',trade_date:date,started_at:chat.created_at,finished_at:state.jobCancelled?chat.created_at:null,stage:state.jobCancelled?'cancelled':'execution',step:'synthetic execution',progress_pct:40,cancel_requested:false}];Object.assign(meta,{total:1,active_count:state.jobCancelled?0:1});}
  else if(extra&&p.endsWith('/advance'))data={id:'synthetic-enqueued-job',status:'QUEUED'};
  else if (p.startsWith('/paper/accounts/account/')) data=[];
  else throw Error('Uncovered API: '+p);
  return {data,meta};
}

async function run(browser, url, width, variant, mode='rich') {
  const page=await browser.newPage({viewport:{width,height:mode==='short'?720:1000},locale:'zh-CN',timezoneId:'Asia/Shanghai'});
  page.setDefaultTimeout(15000);
  page.setDefaultNavigationTimeout(15000);
  await page.addInitScript(()=>{let serial=1;Object.defineProperty(crypto,'randomUUID',{value:()=>`00000000-0000-4000-8000-${String(serial++).padStart(12,'0')}`});});
  await page.clock.install({time:new Date('2026-10-16T08:00:00Z')});
  await page.clock.pauseAt(new Date('2026-10-16T08:00:00Z'));
  const state={mode,signedIn:mode!=='login',mustChange:mode==='password'}, calls=[], errors=[], snapshots=[];
  let failure=null;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
    if(new URL(route.request().url()).origin!==url){errors.push('EXTERNAL_NETWORK_FORBIDDEN');await route.abort();}
    else await route.continue();
  });
  if(variant==='before') await page.route('**/src/style.css',route=>route.fulfill({contentType:'application/javascript',body:`import {updateStyle} from '/@vite/client';updateStyle('/src/style.css',${JSON.stringify(originalCSS)});`}));
  await page.route('**/api/v1/**',async route=>{
    const req=route.request(), target=new URL(req.url());
    calls.push({method:req.method(),url:target.pathname+target.search,body:req.postData()});
    try {
      if(target.pathname.endsWith('/export')){await route.fulfill({contentType:'text/plain',body:'Synthetic frozen export; no production data'});return;}
      const result=fixture(target.pathname.replace('/api/v1',''),target.searchParams,req,state);
      if(result.abort){await route.abort('failed');return;}
      await route.fulfill({status:result.status||200,json:result.status?{detail:{code:result.code||'SYNTHETIC_UNAVAILABLE'}}:{code:0,message:'ok',data:result.data,meta:result.meta}});
    } catch(e){errors.push(e.message);await route.abort();}
  });
  async function settle(){await page.clock.runFor(30);await page.waitForTimeout(60);}
  async function capture(label, screenshot=false){
    if(process.env.UI_DEBUG) console.log(`${variant} ${width} ${mode}: ${label}`);
    await settle();
    // Complete the existing ECharts animations; never change production chart options.
    if(screenshot){await page.clock.runFor(1200);await page.waitForTimeout(60);}
    const value=await page.evaluate(()=>{
      const visible=e=>e.getClientRects().length>0 && getComputedStyle(e).visibility!=='hidden';
      const text=e=>(e.textContent||'').replace(/\s+/g,' ').trim();
      const visibleText=[];const walker=document.createTreeWalker(document.querySelector('#app'),NodeFilter.SHOW_TEXT);
      while(walker.nextNode()){
        const node=walker.currentNode,p=node.parentElement;
        if(!p||p.closest('script,style,svg,canvas,.chart,.analytics-chart,.kline-chart,.bar-chart,.paper-chart'))continue;
        // The reviewed V1 intentionally restores this existing mobile-bound text.
        if((visible(p)||p.closest('.sector-row small'))&&node.textContent.trim())visibleText.push(node.textContent.replace(/\s+/g,' ').trim());
      }
      return {visibleText,controls:[...document.querySelectorAll('button,input,select,textarea,summary')].filter(visible).map(e=>({tag:e.tagName,text:text(e),value:e.value??null,disabled:e.disabled??false,checked:e.checked??null,
        attrs:['type','required','pattern','min','max','aria-label','aria-expanded','aria-selected','title'].map(k=>[k,e.getAttribute(k)])})),
        tables:[...document.querySelectorAll('table')].filter(visible).map(t=>({headers:[...t.querySelectorAll('th')].map(text),cells:[...t.querySelectorAll('td')].map(text)}))};
    });
    snapshots.push({label,...value,requests:calls.splice(0).map(c=>({...c,body:c.body?.replace(/"request_id":"[^"]+"/g,'"request_id":"<opaque>"')||null})).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)))});
    if(variant==='after') {
      const overflow=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,
        nodes:[...document.querySelectorAll('#app *')].filter(e=>e.getClientRects().length && e.getBoundingClientRect().right>innerWidth+1 && !e.closest('table')).slice(0,8).map(e=>[e.tagName,e.className,e.getBoundingClientRect().right])}));
      assert(overflow.scroll<=width,`Page overflow: ${width} ${mode} ${label}: ${JSON.stringify(overflow)}`);
    }
    if(screenshot) {
      await page.evaluate(()=>scrollTo(0,0));
      const file=path.join(String(width),variant,mode,`${label}.png`);
      await page.screenshot({path:path.join(output,file),fullPage:true,timeout:15000});
      screenshots.push({file:file.split(path.sep).join('/'),checkpoint:label,width,height:mode==='short'?720:1000,variant,state:mode,source:'real App.vue with intercepted synthetic API'});
    }
  }
  async function click(name,scope=page){await scope.getByRole('button',{name,exact:true}).click();await settle();}
  async function nav(name){await page.locator('.nav-button').filter({has:page.locator('span',{hasText:new RegExp(`^${name}$`)})}).click();await settle();}
  try {
    await page.goto(url);await settle();
    await page.evaluate(()=>{
      const banner=document.createElement('div');banner.dataset.syntheticEvidence='true';
      banner.textContent='合成验收数据 · 非生产行情 · 不连接真实服务';
      banner.style.cssText='padding:6px 12px;background:#fef3c7;color:#713f12;font:12px sans-serif;text-align:center;';
      document.body.prepend(banner);
    });
    if(mode==='login'||mode==='password'){
      await page.locator('.auth-panel').waitFor();await capture(mode,true);
      if(mode==='login'){await page.locator('input[type=password]').fill('synthetic-password');await page.locator('.auth-panel button[type=submit]').click();await settle();await page.locator('.workspace-shell').waitFor();await capture('signed-in');}
      assert.deepEqual(errors,[]);return snapshots;
    }
    await page.locator('.workspace-shell').waitFor();
    await capture('overview',true);
    if(['disabled','schema','PAUSED','CLOSED'].includes(mode)){
      await nav('决策与模拟');await settle();await capture('paper-state-'+mode,true);
      if(mode==='disabled'||mode==='schema') assert(await page.getByRole('button',{name:'新建账户',exact:true}).isDisabled());
      if(mode==='PAUSED') assert(await page.getByRole('button',{name:'人工审批',exact:true}).isDisabled());
      if(mode==='CLOSED') assert.equal(await page.getByRole('button',{name:'关闭账户',exact:true}).count(),0);
      assert.deepEqual(errors,[]);return snapshots;
    }
    if(mode==='recovery'){
      await nav('智能研究');await page.locator('.agent-composer textarea').fill('合成复核问题');await click('发送');
      await page.getByRole('button',{name:'沿用原请求重试',exact:true}).waitFor();await capture('unknown-result',true);
      await click('沿用原请求重试');await capture('unknown-retry',true);
      state.recoveryStage='failed';await click('刷新状态');
      await page.getByRole('button',{name:'作为新消息重试',exact:true}).waitFor();await capture('failed-result',true);
      await click('作为新消息重试');await capture('failed-new-draft',true);
      assert.equal(await page.locator('.agent-composer textarea').inputValue(),'合成复核问题');
      assert.deepEqual(errors,[]);return snapshots;
    }
    if(mode==='evidence'){
      await nav('智能研究');await page.locator('.agent-citations button').waitFor();await capture('agent-evidence-answer',true);
      await click('加载更早消息');await capture('earlier-messages',true);
      await page.locator('.agent-citations button').click();await capture('agent-evidence-panel',true);
      await click('打开业务详情',page.locator('.agent-evidence-pane'));await page.locator('.wf-detail').waitFor();await capture('walk-forward',true);
      await click('返回智能研究');await capture('walk-forward-return');
      await click('查看证据归档');await capture('chat-archive',true);await click('关闭归档面板');
      await click('归档当前会话');await capture('chat-archived',true);
      await nav('长线');await page.locator('.view-stack:visible .table-wrap').evaluate(e=>{e.scrollLeft=e.scrollWidth;});await capture('long-text-last-column',true);
      await page.locator('.view-stack:visible .table-wrap tbody td:last-child button').first().click();await settle();await capture('stock-research-context',true);
      await nav('回测分析');await capture('missing-period',true);await click('生成周期分析');await page.clock.runFor(1100);await settle();await capture('generated-period',true);
      await nav('研究报告');
      for(const type of ['market_review','opportunity_review','strategy_review','oos_review']){await page.getByLabel('报告类型筛选').selectOption(type);await capture('report-type-'+type);}
      await page.getByLabel('报告类型筛选').selectOption('');await settle();await page.locator('.report-list > button').first().click();await settle();
      await click('从冻结证据复核');await capture('frozen-verification',true);
      await click('查看冻结事实');await capture('frozen-fact-detail',true);await click('关闭详情');
      await click('复核合同');await capture('contract-verification',true);
      await page.locator('.contract-table tbody button').click();await capture('contract-detail',true);
      for(const format of ['Markdown','HTML']){const download=page.waitForEvent('download');await click(format,page.locator('.detail-actions'));await download;await capture('report-export-'+format);}
      await page.locator('.report-compare select').nth(0).selectOption('report-1');await page.locator('.report-compare select').nth(1).selectOption('report-2');
      for(const modeValue of ['AUTO','STRICT_SAME_SAMPLE','DIFFERENT_ASSUMPTIONS','WINDOW_DEGRADATION']){
        await page.getByLabel('比较模式').selectOption(modeValue);await click('比较',page.locator('.report-compare'));await capture('report-comparison-'+modeValue,true);
        assert(!(await page.locator('.comparison-result').textContent()).includes('AUDIT_DELTA_MUST_NOT_RENDER'));
        assert.equal(await page.locator('.comparison-result th').count(),['STRICT_SAME_SAMPLE','WINDOW_DEGRADATION'].includes(modeValue)?5:4);
      }
      for(const format of ['Markdown','HTML']){const download=page.waitForEvent('download');await click('导出比较 '+format);await download;await capture('comparison-export-'+format);}
      await nav('决策与模拟');await capture('paper-running-job',true);await click('取消任务',page.locator('.paper-workbench'));await capture('paper-cancelled-job',true);
      await click('结算下一交易日',page.locator('.paper-workbench'));await capture('paper-advance-queued',true);
      assert.deepEqual(errors,[]);return snapshots;
    }
    if(mode==='rich'){
      await page.locator('.user-menu-trigger').click();await capture('user-menu',true);
      await click('修改密码');await capture('password-optional',true);await click('取消');await settle();
      await page.locator('.clickable-row').first().click();await page.locator('.theme-drawer').waitFor();await capture('theme',true);await page.locator('.theme-drawer button[aria-label="关闭"]').click();
      await page.getByRole('tab',{name:'研究',exact:true}).click();await settle();
      for(const name of ['题材','左侧','右侧','趋势','位置']){await page.getByRole('tab',{name,exact:true}).click();await settle();await capture('research-'+name,true);}
      await click('60日');await capture('research-60');await page.getByRole('tab',{name:'市场',exact:true}).click();
    }
    await nav('数据');await capture('data',true);
    if(mode==='rich'){
      for(const size of ['10','20','50','100']){
        await page.getByLabel('覆盖明细每页条数').selectOption(size);await capture('coverage-'+size);
        if(size==='10'){await click('下一页',page.locator('.pagination-controls'));await capture('coverage-next');await click('上一页',page.locator('.pagination-controls'));await capture('coverage-previous');}
      }
      for(const name of ['补算因子与股票池','拉取数据与任务','数据覆盖日历']){await click(name);await capture('collapsed-'+name,true);await click(name);}
      await click('上月');await capture('previous-month');await click('下月');
      await page.locator('.calendar-day:not(:disabled)').first().click();await capture('calendar-detail',true);
      for(const name of ['同步基础信息','拉取原始数据','开始补算']){await click(name);await capture('post-'+name);}
    }
    await nav('长线');await capture('long',true);
    if(mode==='rich'){
      await click('趋势',page.locator('.view-stack:visible'));await capture('trend',true);
      await page.locator('.view-stack:visible .stock-code-button').first().click();await page.locator('.kline-modal').waitFor();
      for(const days of [90,180,365]){await click(days+'日',page.locator('.kline-modal'));await capture('kline-'+days,days===90);}
      await page.locator('.kline-modal button[aria-label="关闭"]').click();
    }
    await nav('短线');await capture('short',true);
    await nav('回测分析');await capture('analytics',true);
    if(mode==='rich'){
      await click('年度');await capture('year');
      await page.locator('.analytics-run-picker input').nth(0).check();await capture('compare-one');
      await page.locator('.analytics-run-picker input').nth(1).check();await click('开始对比');await capture('compare-two',true);
      for(const name of ['Annualized Return','Max Drawdown','Sharpe']){
        // Frozen 390px fixed-layout headers overlap the mouse target. Exercise the
        // same native keyboard activation in both variants, never force a click.
        const button=page.getByRole('button',{name,exact:true});
        await button.focus();await page.keyboard.press('Enter');await capture('sort-'+name);
        // The new auto-layout must also make the original mouse action reachable.
        if(variant==='after') await button.click();
      }
    }
    await nav('智能研究');await capture('agent',true);
    await page.locator('.agent-context-fields input').first().fill('000001.SZ');await capture('agent-context');
    await page.locator('.agent-context-chips button').first().click();await capture('agent-clear');
    await nav('研究报告');await capture('reports',true);
    if(mode==='rich'){await page.locator('.report-list > button').first().click();await settle();await capture('report-detail',true);}
    await nav('决策与模拟');await settle();await capture('paper',true);
    if(mode==='rich'){
      for(const name of ['模拟组合','执行与账本','后验复盘','决策日志']){await click(name);await capture('paper-'+name,name!=='决策日志');}
      await click('执行与账本');
      for(const kind of ['orders','approvals','attempts','fills','ledger','positions','days','runs','events']){await page.locator('.paper-filters select').selectOption(kind);await capture('ledger-'+kind);}
      await click('决策日志');
      for(const name of ['新建账户','记录决策','人工审批','驳回','关闭账户']){
        await click(name,page.locator('.paper-workbench'));await page.getByRole('dialog').waitFor();await capture('modal-'+name,true);
        if(name==='人工审批'){await page.locator('.paper-checkbox input').check();await capture('approval-confirmed');}
        await click('取消',page.getByRole('dialog'));
      }
    }
    assert.deepEqual(errors,[]);
    return snapshots;
  } catch(error) {
    failure={message:error.message,stack:error.stack};throw error;
  } finally {
    const folder=path.join(output,String(width),variant,mode);
    await fs.mkdir(folder,{recursive:true});
    await fs.writeFile(path.join(folder,'checkpoints.json'),JSON.stringify({width,variant,mode,snapshots,errors,pending_requests:calls,failure},null,2));
    if(failure)await page.screenshot({path:path.join(folder,'failure.png'),fullPage:true,timeout:15000}).catch(e=>console.error('Failure screenshot unavailable:',e.message));
    await page.close();
  }
}

async function main(){
  check();await fs.mkdir(output,{recursive:true});
  const probe=net.createServer();await new Promise(resolve=>probe.listen(0,'127.0.0.1',resolve));
  const port=probe.address().port;await new Promise(resolve=>probe.close(resolve));
  const vite=spawn(process.execPath,[path.join(root,'frontend/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port',String(port),'--strictPort'],{cwd:path.join(root,'frontend'),stdio:'pipe',env:{...process.env,VITE_API_BASE_URL:'/api/v1'}});
  let browser, viteLog='', passed=false;
  vite.stdout.on('data',value=>{viteLog+=value;});vite.stderr.on('data',value=>{viteLog+=value;});
  assert(!process.env.GITHUB_SHA||process.env.GITHUB_SHA===head,'CI_HEAD_MISMATCH');
  const report={schema_version:'ui-visual-acceptance-v1.2',head_sha:head,baseline,viewports:[],status:'running',
    style_sha256:fileHash('frontend/src/style.css'),script_sha256:fileHash('scripts/ui_visual_browser.cjs'),
    worktree_dirty:Boolean(execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim()),
    environment:{node:process.version,playwright:playwrightVersion,platform:os.platform(),arch:os.arch()},
    ci:{run_url:process.env.GITHUB_RUN_ID?`https://github.com/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`:null,attempt:process.env.GITHUB_RUN_ATTEMPT||null},
    assertion:'same controls, values, disabled/required/aria, table headers/cells and per-step API multiset',sourceProtection:check()};
  const save=async()=>{
    await fs.writeFile(path.join(output,'result.json'),JSON.stringify(report,null,2));
    await fs.writeFile(path.join(output,'screenshots.json'),JSON.stringify(screenshots,null,2));
    await fs.writeFile(path.join(output,'index.md'),`# Synthetic UI evidence\n\nHEAD: ${head}\n\n${report.ci.run_url||'Local run; not CI evidence'}\n\n| Width | Variant | State | Checkpoint | Screenshot |\n| --- | --- | --- | --- | --- |\n`+screenshots.map(s=>`| ${s.width} | ${s.variant} | ${s.state} | ${s.checkpoint} | [image](${s.file.split('/').map(encodeURIComponent).join('/')}) |`).join('\n')+'\n');
  };
  try{
    const url=`http://127.0.0.1:${port}`;
    let ready=false;
    for(let i=0;i<100;i++){try{if((await fetch(url,{signal:AbortSignal.timeout(1000)})).ok){ready=true;break;}}catch{}if(vite.exitCode!==null)break;await new Promise(r=>setTimeout(r,100));}
    assert(ready,`Vite did not start: ${viteLog}`);
    browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
    report.environment.browser=browser.version();await save();
    for(const width of [1440,1280,1024,768,390]){
      let checkpoints=0;const states=[];
      for(const mode of ['rich','empty','error','login','password','disabled','schema','PAUSED','CLOSED']){
        const before=await run(browser,url,width,'before',mode);
        const after=await run(browser,url,width,'after',mode);
        await fs.writeFile(path.join(output,`comparison-${width}-${mode}.json`),JSON.stringify({before,after},null,2));
        assert.deepEqual(after,before,`Behavior changed at ${width}px / ${mode}`);
        checkpoints+=after.length;
        states.push({state:mode,before:before.length,after:after.length,passed:true});
      }
      report.viewports.push({width,checkpoints,states,passed:true});await save();console.log(`UI ${width}px: ${checkpoints} before/after checkpoints passed`);
    }
    const short=await run(browser,url,1280,'after','short');
    report.shortScreen={width:1280,height:720,checkpoints:short.length,passed:true};
    console.log('UI 1280x720: all eight navigation entries reachable without footer overlap');
    assert.equal(report.viewports.length,5);assert(report.viewports.every(v=>v.states.length===9));
    report.secondary=[];
    for(const width of [1440,390])for(const mode of ['evidence','recovery']){
      const before=await run(browser,url,width,'before',mode),after=await run(browser,url,width,'after',mode);
      await fs.writeFile(path.join(output,`comparison-${width}-${mode}.json`),JSON.stringify({before,after},null,2));
      assert.deepEqual(after,before,`Secondary behavior changed at ${width}px`);
      report.secondary.push({width,state:mode,checkpoints:after.length,passed:true});
    }
    passed=true;report.status='passed';
  } catch(error){report.status='failed';report.error={message:error.message,stack:error.stack};throw error;}
  finally{
    report.status=passed?'passed':'failed';report.screenshots=screenshots.length;await save();
    await fs.mkdir(path.join(output,'logs'),{recursive:true});await fs.writeFile(path.join(output,'logs/vite.log'),viteLog);
    try {
      if(browser)await browser.close();
      if(vite.exitCode===null){let timer;const stopped=new Promise(resolve=>vite.once('exit',resolve));vite.kill('SIGTERM');try{await Promise.race([stopped,new Promise((_,reject)=>{timer=setTimeout(()=>{vite.kill('SIGKILL');reject(Error('Vite cleanup timed out'));},5000);})]);}finally{clearTimeout(timer);}}
      const probeClose=net.createServer();await new Promise((resolve,reject)=>{probeClose.once('error',reject);probeClose.listen(port,'127.0.0.1',resolve);});await new Promise(resolve=>probeClose.close(resolve));
    } catch(error){passed=false;report.status='failed';report.cleanup_error=error.message;await save();throw error;}
    report.cleanup={browser_closed:true,vite_stopped:true,port_released:true};await save();
    if(passed&&process.argv.includes('--publish-summary'))await fs.writeFile(path.join(root,'docs/ui-upgrade/UI-2_browser_summary.json'),JSON.stringify(report,null,2)+'\n');
  }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
