import json,pathlib,copy,uuid
p=pathlib.Path(__file__).parent
w=json.loads((p/'intercom_dex_GMAIL_OIDC_SANDBOX.json').read_text())
w['name']='Intercom DEX - Windows Gmail OIDC - E2E SANDBOX LIVE OFF'
by={n['name']:n for n in w['nodes']}
config={'name':'Local sandbox configuration','id':str(uuid.uuid4()),'type':'n8n-nodes-base.code','typeVersion':2,'position':[100,0],'parameters':{'mode':'runOnceForAllItems','jsCode':"return [{json:{guardBaseUrl:'http://127.0.0.1:8765',proposalSource:'test',live_enabled:false}}];"}}
w['nodes'].append(config)
for n in w['nodes']:
 if n['type'].endswith('.httpRequest'):
  n['parameters']['url']=n['parameters']['url'].replace('$vars.INTERCOM_GUARD_BASE_URL',"$('Local sandbox configuration').first().json.guardBaseUrl")
 if n['name']=='Gmail - secure approval link':
  n['parameters']['sendTo']="={{ $('Guard - synthetic market ONLY').first().json.approver_email }}"
  n['parameters']['subject']='Intercom DEX - Windows E2E SANDBOX - aprobare necesara'
  n['parameters']['options']={'appendAttribution':False}
 if n['name']=='Normalize Market Feed':
  n['parameters']['jsCode']="const x=$input.first().json;if(x.mode!=='SANDBOX'||x.synthetic!==true||x.live_enabled!==false||!Array.isArray(x.pairs)||x.pairs.length!==2)throw new Error('Sandbox market contract required');if(typeof x.approver_email!=='string'||!x.approver_email.includes('@'))throw new Error('Approver email missing in Guard setup');return [{json:{pairs:x.pairs,mode:'SANDBOX'}}];"
# This Windows E2E workflow needs only Gmail and Guard credentials, not an AI credential.
removed={'AI Agent','OpenAI Chat Model','Structured Output Parser'}
w['nodes']=[n for n in w['nodes'] if n['name'] not in removed]
w['nodes'].append({'name':'Deterministic test proposal','id':str(uuid.uuid4()),'type':'n8n-nodes-base.code','typeVersion':2,'position':[720,-120],'parameters':{'mode':'runOnceForAllItems','jsCode':"return [{json:{output:{pair:'TNK/USDC',side:'buy',price:1,amount:5,reason:'Deterministic end-to-end Gmail/OIDC test; synthetic data only; no order',ready_to_trade:true}}}];"}})
c={k:v for k,v in w['connections'].items() if k not in removed}
w['connections']=c
def edge(a,*targets):c[a]={'main':[[{'node':t,'type':'main','index':0}] for t in targets]}
edge('Start manual','Local sandbox configuration');edge('Local sandbox configuration','Guard - synthetic market ONLY');edge('Normalize Market Feed','Deterministic test proposal');edge('Deterministic test proposal','Validate candidate - fail closed')
w['active']=False;w['pinData']={}
text=json.dumps(w,ensure_ascii=False,indent=2)+'\n'
assert '$vars' not in text
(p/'intercom_dex_WINDOWS_SANDBOX.json').write_text(text)
