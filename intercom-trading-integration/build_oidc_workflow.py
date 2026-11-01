import json,copy,pathlib,uuid
p=pathlib.Path(__file__).parent
w=json.loads((p/'intercom_dex_gmail_guard_SANDBOX.json').read_text())
w['name']='Intercom DEX - Gmail + Google OIDC - SANDBOX LIVE OFF'
remove={'If Gmail Approved','Guard - revalidate and SIMULATE only','Guard - persist rejection','Result - LIVE HARD DISABLED'}
w['nodes']=[n for n in w['nodes'] if n['name'] not in remove]
for n in w['nodes']:
 if n['name']=='Gmail - explicit approval':
  n['name']='Gmail - secure approval link'
  n['parameters']={'resource':'message','operation':'send','sendTo':'={{ $vars.INTERCOM_APPROVER_EMAIL }}','subject':'Intercom DEX — SANDBOX — aprobarea ta necesară','emailType':'text','message':"=LIVE DEZACTIVAT. Datele sunt sintetice. Propunere exactă: {{ JSON.stringify($('Guard - persist immutable proposal').first().json.proposal) }}. ID: {{ $('Guard - persist immutable proposal').first().json.proposal_id }}. Digest: {{ $('Guard - persist immutable proposal').first().json.digest }}. Expiră (Unix secunde): {{ $('Guard - persist immutable proposal').first().json.expiresAt }}. Deschide pe laptopul pe care rulează serviciul: {{ $('Guard - persist immutable proposal').first().json.approval_url }} . Autentifică-te cu contul Google autorizat, verifică detaliile și apasă explicit Aprob sau Resping. Simpla deschidere a linkului NU aprobă. Nicio tranzacție reală nu poate fi trimisă de acest build.",'options':{}}
  n['position']=[1560,-80]
# Authenticated polling reads persisted result. No callback token or Gmail resume URL in the email.
w['nodes'].append({'name':'Guard - read decision','id':str(uuid.uuid4()),'type':'n8n-nodes-base.httpRequest','typeVersion':4.5,'position':[1780,-80],'parameters':{'url':"={{ $vars.INTERCOM_GUARD_BASE_URL + '/v1/proposals/' + $('Guard - persist immutable proposal').first().json.proposal_id }}",'authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth','options':{'timeout':15000}},'retryOnFail':False,'onError':'stopWorkflow'})
f=copy.deepcopy(next(n for n in w['nodes'] if n['name']=='If Valid Proposal'));f.update(name='If pending',id=str(uuid.uuid4()),position=[2000,-80]);f['parameters']['conditions']['conditions'][0]['leftValue']='={{ $json.pending === true }}';w['nodes'].append(f)
w['nodes'].append({'name':'Wait 5 seconds','id':str(uuid.uuid4()),'type':'n8n-nodes-base.wait','typeVersion':1.1,'position':[2220,-180],'parameters':{'resume':'timeInterval','amount':5,'unit':'seconds'},'webhookId':str(uuid.uuid4())})
w['nodes'].append({'name':'Result - LIVE HARD DISABLED','id':str(uuid.uuid4()),'type':'n8n-nodes-base.code','typeVersion':2,'position':[2220,60],'parameters':{'jsCode':"const x=$input.first().json;if(x.live_enabled!==false||x.order_sent!==false||x.pending!==false)throw new Error('Invalid terminal state');return [{json:{proposal_id:x.proposal_id,state:x.state,result:x.result,order_sent:false,live_enabled:false}}];"}})
c=w['connections'];c={k:v for k,v in c.items() if k not in remove|{'Gmail - explicit approval'}}
c['Guard - persist immutable proposal']={'main':[[{'node':'Gmail - secure approval link','type':'main','index':0}]]}
def edge(a,*b):c[a]={'main':[[{'node':x,'type':'main','index':0}] for x in b]}
edge('Gmail - secure approval link','Guard - read decision');edge('Guard - read decision','If pending');edge('If pending','Wait 5 seconds','Result - LIVE HARD DISABLED');edge('Wait 5 seconds','Guard - read decision')
w['connections']=c
(p/'intercom_dex_GMAIL_OIDC_SANDBOX.json').write_text(json.dumps(w,indent=2,ensure_ascii=False)+'\n')
