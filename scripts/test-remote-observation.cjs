const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ts = require('typescript');
function compile(path, context, requireOverride) {
  const result = {};
  const code = ts.transpileModule(fs.readFileSync(path, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  vm.runInNewContext(code, { exports: result, process: {env:{}}, AbortController, DOMException, ...context, require: name => name === "@/features/creative/copy" ? compile("src/features/creative/copy.ts", {}, () => result) : (requireOverride || require)(name) });
  return result;
}
function clock() {
  let now = 100000, seq = 0;
  const timers = new Map();
  class Time extends Date { static now() { return now; } }
  const environment = { Date: Time, setTimeout(fn, ms) { const id = ++seq; timers.set(id, {at: now + ms, fn}); return id; }, clearTimeout(id) { timers.delete(id); } };
  const flush = async () => { for (let i=0; i<20; i++) await Promise.resolve(); };
  return { environment, async tick(ms) {
    const until = now + ms; await flush();
    for (;;) {
      const next = [...timers].filter(([,t]) => t.at <= until).sort((a,b) => a[1].at-b[1].at)[0];
      if (!next) break;
      now = next[1].at; timers.delete(next[0]); next[1].fn(); await flush();
    }
    now = until; await flush();
  } };
}
const response = (data, status=200, retryAfter=null) => ({ ok:status<400, status, headers:{get:()=>retryAfter}, json:async()=>data });
(async () => {
  let checks = 0;
  const apiClock = clock();
  let requests = 0;
  const client = compile('src/lib/api.ts', { ...apiClock.environment, fetch:async()=> { requests++; return response({error:{code:'RATE_LIMITED',message:'请求过于频繁',details:{retry_after:2}}},429,'2'); } });
  let caught;
  try { await client.api('/projects/p/tasks'); } catch(error) { caught=error; }
  assert.equal(caught.status,429); assert.equal(caught.retryAfterMs,2000); checks+=2;
  await assert.rejects(client.api('/creative/projects/p'), error=>error.status===429);
  assert.equal(requests,1,'same-project readers must obey a shared cooldown without another network request'); checks+=2;

  const taskClock = clock(); let taskReads=0;
  const taskClient = compile('src/lib/api.ts', { ...taskClock.environment, fetch:async()=> { taskReads++; return taskReads===1 ? response({error:{code:'RATE_LIMITED',message:'wait'}},429,'2') : response({id:'t',status:taskReads===2?'running':'done',progress:taskReads===2?50:100}); } });
  const waited = taskClient.waitTask('t');
  await taskClock.tick(1999); assert.equal(taskReads,1);
  await taskClock.tick(1); assert.equal(taskReads,2);
  await taskClock.tick(2000); assert.equal((await waited).status,'done'); checks+=3;
  const abortClock = clock();
  const abortClient = compile('src/lib/api.ts',{...abortClock.environment,fetch:async()=>response({error:{message:'wait'}},429,'60')});
  const controller = new AbortController();
  const aborted = abortClient.waitTask('t',undefined,controller.signal);
  await abortClock.tick(0); controller.abort();
  await assert.rejects(aborted, error=>error.name==='AbortError'); checks++;

  const readClock = clock();
  const observerModule = compile('src/lib/read-observer.ts',readClock.environment,()=>client);
  let reads=0, release;
  const observer = observerModule.createReadObserver(async()=> { reads++; if(reads===1) await new Promise(resolve=>release=resolve); },()=>{});
  await readClock.tick(0);
  for(let i=0;i<200;i++) observer.request();
  await readClock.tick(4900); assert.equal(reads,1,'events must not overlap an in-flight read');
  release(); await readClock.tick(100); assert.equal(reads,2,'a burst coalesces into one trailing read');
  for(let i=0;i<200;i++) observer.request();
  await readClock.tick(4999); assert.equal(reads,2);
  await readClock.tick(1); assert.equal(reads,3); observer.stop(); checks+=4;
  let limitedReads=0;
  const limited = observerModule.createReadObserver(async()=> { limitedReads++; if(limitedReads===1) throw new client.ApiError('wait',429,'RATE_LIMITED',60000); },()=>{});
  await readClock.tick(0);
  for(let i=0;i<200;i++) limited.request();
  await readClock.tick(59999); assert.equal(limitedReads,1,'progress events cannot bypass Retry-After');
  await readClock.tick(1); assert.equal(limitedReads,2); limited.stop(); checks+=2;

  const remoteClock = clock(), calls=[];
  let task = {id:'v',projectId:'p',sceneId:'s',kind:'video',type:'视频',status:'running',progress:5,createdAt:'2026-09-30T00:00:00Z'};
  const project = {id:'p',scenes:[{id:'s'}],characters:[],updatedAt:'2026-09-30T00:00:00Z'};
  let state = {projects:[project],activeId:'p',sceneId:'s',tasks:[task],paused:false};
  const store = {getState:()=>state,setState:update=> { state={...state,...(typeof update==='function'?update(state):update)}; }};
  class Events {
    static instances=[];
    constructor(){this.handlers=new Map();Events.instances.push(this);}
    addEventListener(name,callback){this.handlers.set(name,callback);}
    emit(name,data){this.handlers.get(name)?.({data:JSON.stringify(data)});}
    close(){this.closed=true;}
  }
  const remoteApi = {...client,api:async path=> {calls.push(path); if(path==='/projects')return[project]; if(path.endsWith('/tasks'))return[task]; if(path.endsWith('/queue'))return{paused:false}; return project;}};
  const remoteObserver = compile('src/lib/read-observer.ts',remoteClock.environment,()=>remoteApi);
  const remote = compile('src/lib/remote-store.ts',{...remoteClock.environment,EventSource:Events},name=>name==='./api'?remoteApi:name==='./store'?{useStore:store}:remoteObserver);
  await Promise.all([remote.refreshRemote(),remote.refreshRemote(),remote.refreshRemote()]);
  assert.equal(calls.length,3,'concurrent full refresh callers share one request chain'); checks++;
  const disconnect = remote.connectRemote('p');
  Events.instances[0].onopen(); await remoteClock.tick(0);
  const before = calls.length;
  for(let i=0;i<200;i++)Events.instances[0].emit('task',{...task,progress:i%99});
  await remoteClock.tick(5000);
  assert.equal(calls.length,before,'200 task progress events cause no project/tasks reload');
  assert.equal(state.tasks[0].progress,199%99,'SSE still updates visible task progress'); checks+=2;
  task={...task,status:'done',progress:100};
  Events.instances[0].emit('task',task);
  for(let i=0;i<20;i++)Events.instances[0].emit('scene',{id:'s'});
  await remoteClock.tick(0);
  assert.equal(calls.length,before+2,'terminal and scene burst performs one metadata read, no task fetch'); checks++;
  Events.instances[0].emit('task',{...task,status:'running',progress:90});
  assert.equal(state.tasks[0].status,'done','a late progress snapshot cannot regress a terminal task'); checks++;
  await remoteClock.tick(10000);
  assert.equal(calls.filter(path=>path==='/projects/p/tasks').length,3,'only the shared 15-second fallback polls tasks'); checks++;
  disconnect(); const afterStop=calls.length; await remoteClock.tick(60000);
  assert.equal(calls.length,afterStop,'unmount stops both fallback timers'); checks++;
  for(const file of ['src/features/Creative.tsx','src/features/creative/VideoGeneration.tsx']) {
    assert.ok(!fs.readFileSync(file,'utf8').includes('/tasks`'),'creative/video panels cannot add their own task polling'); checks++;
  }
  console.log(`Remote observation: ${checks} checks passed; 200 progress events = 0 full reloads; one task fallback every 15s; 429 honored for 60s.`);
})().catch(error=> {console.error(error);process.exitCode=1;});
