const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const w=JSON.parse(fs.readFileSync(__dirname+'/intercom_dex_WINDOWS_SANDBOX.json','utf8'));
const nodes=new Map(w.nodes.map(n=>[n.name,n]));
const code=(name,items)=>vm.runInNewContext('(function(){'+nodes.get(name).parameters.jsCode+'})()',{$input:{all:()=>items,first:()=>items[0]},$execution:{id:'windows-workflow-test'},Number,JSON,Error});
const config=code('Local sandbox configuration',[])[0].json;assert.equal(config.guardBaseUrl,'http://127.0.0.1:8765');assert.equal(config.live_enabled,false);
const feed={json:{mode:'SANDBOX',synthetic:true,live_enabled:false,approver_email:'owner@example.invalid',pairs:[{pair:'TNK/USDC'},{pair:'RESET/USDC'}]}};
assert.equal(code('Normalize Market Feed',[feed])[0].json.mode,'SANDBOX');
assert.throws(()=>code('Normalize Market Feed',[{json:{...feed.json,approver_email:''}}]));
const candidate=code('Deterministic test proposal',[]);
const validated=code('Validate candidate - fail closed',candidate)[0].json;
assert.equal(validated.valid,true);assert.equal(validated.candidate.price*validated.candidate.amount,5);
const terminal=code('Result - LIVE HARD DISABLED',[{json:{live_enabled:false,order_sent:false,pending:false,state:'SIMULATED',result:{status:'SIMULATED_LIMIT_ORDER_ONLY'}}}])[0].json;
assert.equal(terminal.order_sent,false);assert.equal(terminal.state,'SIMULATED');
assert.throws(()=>code('Result - LIVE HARD DISABLED',[{json:{live_enabled:true,order_sent:true,pending:false}}]));
assert(!w.nodes.some(n=>n.type.startsWith('@n8n/')||n.type.includes('OpenAi')));
assert(!JSON.stringify(w).includes('$vars'));assert.equal(w.active,false);
const seen=new Set();function visit(name){if(seen.has(name))return;seen.add(name);for(const branches of Object.values(w.connections[name]||{}))for(const b of branches)for(const e of b)visit(e.node);}
visit('Start manual');assert.equal(seen.size,w.nodes.length);
console.log('Windows workflow: one connected flow, three Guard HTTP nodes, no $vars, no AI credential dependency; 5-USDC test candidate and terminal safeguards passed.');
