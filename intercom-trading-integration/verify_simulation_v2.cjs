const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const current=JSON.parse(fs.readFileSync(path.join(__dirname,'intercom_dex_simulare_offline_v2.json'),'utf8'));
const originalPath=process.argv[2];
const old=originalPath?JSON.parse(fs.readFileSync(originalPath,'utf8')):null;
function code(w,name,items,now){const n=w.nodes.find(n=>n.name===name);return vm.runInNewContext('(function(){'+n.parameters.jsCode+'})()',{$input:{all:()=>items,first:()=>items[0]},$execution:{id:'regression'},Date:{now:()=>now},Number,JSON,Math,String,Set,Error});}
const base=1800000000000;
const reproduction={};
if(old){const f=code(old,'Synthetic fixtures',[],base);for(const lag of [0,31000]){const rows=code(old,'Validate simulation',f,base+lag);reproduction['delay_'+lag+'ms']={valid:rows.filter(x=>x.json.valid).length,invalid:rows.filter(x=>!x.json.valid).length};}assert.equal(reproduction.delay_0ms.valid,6);assert.equal(reproduction.delay_31000ms.valid,0);}
const names=new Set(current.nodes.map(n=>n.name));assert.equal(current.active,false);assert.deepEqual(current.pinData,{});assert.equal(names.size,current.nodes.length);
for(const n of current.nodes){assert(['n8n-nodes-base.manualTrigger','n8n-nodes-base.code','n8n-nodes-base.if'].includes(n.type));assert(!n.credentials);assert(!n.disabled);if(n.type.endsWith('.code'))assert.equal(n.parameters.mode,'runOnceForAllItems');}
for(const [s,p]of Object.entries(current.connections)){assert(names.has(s));for(const b of p.main)for(const e of b)assert(names.has(e.node));}
const reports=[];
for(const delay of [0,31000,120000,86400000]){
 const fixture=code(current,'Synthetic fixtures',[],base);
 const rows=code(current,'Validate simulation',fixture,base+delay);
 const summary=code(current,'Automatic simulation summary',rows,base+delay)[0].json;
 assert.equal(summary.valid,6);assert.equal(summary.invalid,12);
 const expanded=code(current,'Cases for IF routing',[{json:summary}],base+delay);
 const terminals=[],routed={};
 function route(name,items,trail=[]){assert(!trail.includes(name));const n=current.nodes.find(n=>n.name===name);
  if(n.type.endsWith('.if')){const c=n.parameters.conditions;assert.equal(c.conditions.length,1);assert.equal(c.options.typeValidation,'strict');const cond=c.conditions[0];assert.deepEqual(cond.operator,{type:'boolean',operation:'true',singleValue:true});const field=cond.leftValue.match(/^=\{\{\s*\$json\.(\w+)\s*\}\}$/)?.[1];assert(field);const split=[items.filter(i=>i.json[field]===true),items.filter(i=>i.json[field]!==true)];routed[name]={true:split[0].length,false:split[1].length};split.forEach((a,i)=>{if(a.length)route(current.connections[name].main[i][0].node,a,[...trail,name]);});return;}
  const out=code(current,name,items,base+delay);const edges=current.connections[name]?.main[0];if(edges)for(const e of edges)route(e.node,out,[...trail,name]);else terminals.push(...out.map(x=>x.json));
 }
 route('If valid',expanded);
 assert.equal(terminals.length,18);assert(terminals.every(x=>x.test_passed&&x.order_sent===false&&x.external_calls===0));
 const counts={};for(const t of terminals)counts[t.status]=(counts[t.status]||0)+1;
 for(const [s,n]of Object.entries(summary.expectedTerminalCounts))assert.equal(counts[s],n);
 assert.deepEqual(routed['If valid'],{true:6,false:12});assert.deepEqual(routed['If approved'],{true:2,false:4});
 reports.push({realClockDelayMs:delay,routed,terminalCounts:counts,passed:18,failed:0});
}
// The summary refuses corrupt or incomplete fixtures rather than declaring the suite successful.
const validRows=code(current,'Validate simulation',code(current,'Synthetic fixtures',[],base),base);
const altered=structuredClone(validRows);altered[0].json.valid=false;
assert.throws(()=>code(current,'Automatic simulation summary',altered,base));
assert.throws(()=>code(current,'Automatic simulation summary',validRows.slice(1),base));
const gmail=JSON.parse(fs.readFileSync(path.join(__dirname,'intercom_dex_GMAIL_OIDC_SANDBOX.json'),'utf8'));
assert.equal(gmail.nodes.length,15);assert(!JSON.stringify(gmail).includes('simulationClockMs'));assert(!gmail.nodes.some(n=>/Synthetic fixtures|Validate simulation/.test(n.name)));
const result={runtime:'Node VM harness; actual n8n import/execution not tested',originalReproduction:reproduction,correctedRuns:reports,negativeSummaryChecks:2,gmailWorkflowNodes:15,gmailWorkflowContainsOfflineFixtures:false};
fs.writeFileSync(process.env.SIMULATION_REPORT_PATH||path.join(require('os').tmpdir(),'intercom-simulation-regression.json'),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result,null,2));
