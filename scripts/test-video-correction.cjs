const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ts = require('typescript');
const jsx = (type, props) => ({type, props});
function compile(file, modules, globals={}) {
  const result={};
  const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  vm.runInNewContext(code,{exports:result,require:name=>name==='react/jsx-runtime'?{jsx,jsxs:jsx,Fragment:'fragment'}:name==='@/features/creative/copy'?compile('src/features/creative/copy.ts',{}):modules[name]||{},...globals});
  return result;
}
function nodes(tree) { if(!tree||typeof tree!=='object')return[]; const children=tree.props?.children;return[tree,...(Array.isArray(children)?children:[children]).flatMap(nodes)]; }
function harness(fileSize=1024, selectHistorical=false) {
  const values=[];let cursor=0,reloads=0,selections=0;
  const requests=[];
  const react={useState(initial){const index=cursor++;if(!(index in values))values[index]=typeof initial==='function'?initial():initial;return[values[index],next=>values[index]=typeof next==='function'?next(values[index]):next];}};
  class Form {constructor(){this.fields=new Map();}append(name,value){this.fields.set(name,value);}}
  const comp=compile('src/features/creative/VideoCorrection.tsx',{'react':react,'@/features/creative/ErrorNotice':{ErrorNotice:'error-notice'},'@/lib/api':{apiBase:''},'./CandidateList':{CandidateList:'candidate-list'}},{FormData:Form,fetch:async(url,options)=>{requests.push({url,...options});return{ok:true,json:async()=>({candidateId:'correction-candidate'})};}}).VideoCorrection;
  const originalTask='e24bf000000000000000000000000001', historicalTask='f36011a5c3624e9d870a18c62da0402e';
  const scene={id:'scene-1',creative:{version:7,video:{take:'00000000000000000000000000000001',candidate_id:'00000000000000000000000000000001',parent_task_id:originalTask},video_takes:[{take:historicalTask,model:'MiniMax-H3',provider_task_id:'remote-original'}]}};
  const props={project:{id:'project-1'},scene,candidates:[],busy:false,reload:async()=>{reloads++;},onSelect:()=>{selections++;}};
  const render=()=>{cursor=0;return comp(props);};
  let tree=render();
  if(selectHistorical)nodes(tree).find(node=>node.type==='select').props.onChange({target:{value:historicalTask}});
  nodes(tree).find(node=>node.type==='input').props.onChange({target:{files:[{name:'fixed.mp4',type:'video/mp4',size:fileSize}]}});
  nodes(tree).find(node=>node.type==='textarea').props.onChange({target:{value:'仅修正灯罩提前发光，保留人物动作与原始H3来源'}});
  tree=render();
  return{async upload(){nodes(tree).find(node=>node.type==='button').props.onClick();for(let i=0;i<15;i++)await Promise.resolve();tree=render();},requests,get reloads(){return reloads;},get selections(){return selections;},get tree(){return tree;},originalTask,historicalTask};
}
(async()=>{
  let checks=0;
  const upload=harness();await upload.upload();
  assert.equal(upload.requests.length,1);checks++;
  const request=upload.requests[0];
  assert.equal(request.url,'/api/creative/scenes/scene-1/video-correction');checks++;
  assert.equal(request.method,'POST');checks++;
  assert.equal(request.body.fields.get('expected'),'7');checks++;
  assert.equal(request.body.fields.get('source_task_id'),upload.originalTask,'corrected take keeps the original H3 parent');checks++;
  assert.ok(request.body.fields.get('reason').includes('灯罩'));checks++;
  assert.equal(upload.reloads,1);checks++;
  assert.equal(upload.selections,0,'saving an upload must not automatically select it');checks++;
  assert.ok(nodes(upload.tree).some(node=>node.props?.role==='status'));checks++;
  assert.equal(nodes(upload.tree).find(node=>node.type==='select').props.value,upload.originalTask,'current H3 parent remains the initial selection');checks++;
  const options=nodes(upload.tree).filter(node=>node.type==='option');
  assert.equal(options.length,2,'only actual H3 source tasks are offered, not the manual candidate take');checks++;
  assert.ok(options.some(option=>option.props.value===upload.historicalTask));checks++;
  const historical=harness(1024,true);await historical.upload();
  assert.equal(historical.requests[0].body.fields.get('source_task_id'),historical.historicalTask,'historical H3 selection is sent as the real source task');checks++;
  const oversized=harness(50*1024*1024+1);await oversized.upload();
  assert.equal(oversized.requests.length,0,'oversized uploads are rejected before any request');checks++;
  assert.ok(nodes(oversized.tree).some(node=>node.type==='error-notice' && node.props.error?.message==='修正版 MP4 不能超过 50 MB'),'validation failure is passed to the shared visible ErrorNotice');checks++;
  const list=compile('src/features/creative/CandidateList.tsx',{'./shared':{operationNames:{video_correction:'本地视频修正版'}},'./CandidateRepair':{},'../CreativeStudio':{}}).CandidateList;
  const candidate={id:'candidate-1',kind:'video_correction',url:'/media/fixed.mp4',entityId:'scene-1',stale:false,data:{request:{},source_task_id:upload.originalTask,reason:'修正提前发光',post_processing:[{tool:'ffmpeg',operation:'lamp correction'}],duration_ms:6000}};
  const preview=list({items:[candidate],project:{characters:[],scenes:[]},busy:false,onSelect:()=>{}});
  assert.equal(nodes(preview).filter(node=>node.type==='video').length,1);checks++;
  assert.equal(nodes(preview).filter(node=>node.type==='audio').length,0);checks++;
  assert.equal(nodes(preview).find(node=>node.type==='video').props.src,candidate.url);checks++;
  console.log(`Local video correction: ${checks} checks passed; multipart source/version/reason retained, upload stays candidate-only, MP4 candidate previews as video.`);
})().catch(error=>{console.error(error);process.exitCode=1;});
