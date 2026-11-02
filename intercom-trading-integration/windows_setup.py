"""Windows launcher; secrets encrypted with current-user Windows DPAPI outside Git.
No DEX transport. Never prints keys or tokens. Python 3.10+.
"""
import argparse,base64,ctypes,getpass,json,os,pathlib,secrets,subprocess,sys,time,uuid
from urllib.request import Request,urlopen,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError,URLError
ROOT=pathlib.Path(__file__).resolve().parent
class SetupError(Exception):pass
def data_dir():
    if os.name!='nt':raise SetupError('Acest launcher necesita Windows; testele Python portabile sunt disponibile separat.')
    return pathlib.Path(os.environ['LOCALAPPDATA'])/'IntercomTradingSandbox'
def protect(data,decrypt=False):
    if os.name!='nt':raise SetupError('Windows DPAPI is required; refusing plaintext fallback')
    from ctypes import wintypes
    class BLOB(ctypes.Structure):_fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]
    buf=ctypes.create_string_buffer(data);src=BLOB(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)));dst=BLOB()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    if decrypt:
        fn=crypt.CryptUnprotectData;fn.argtypes=[ctypes.POINTER(BLOB),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(BLOB)]
        ok=fn(ctypes.byref(src),None,None,None,None,1,ctypes.byref(dst))
    else:
        fn=crypt.CryptProtectData;fn.argtypes=[ctypes.POINTER(BLOB),wintypes.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(BLOB)]
        ok=fn(ctypes.byref(src),'Intercom SANDBOX',None,None,None,1,ctypes.byref(dst))
    if not ok:raise SetupError('Windows DPAPI failed; configuration was not decrypted/persisted')
    try:return ctypes.string_at(dst.pbData,dst.cbData)
    finally:kernel.LocalFree(ctypes.cast(dst.pbData,ctypes.c_void_p))
def load():
    f=data_dir()/'config.dpapi'
    if not f.is_file():raise SetupError('Config lipsa. Ruleaza mai intai: .\\Start-Windows.ps1 setup')
    return json.loads(protect(f.read_bytes(),True))
def save(c):
    d=data_dir();d.mkdir(parents=True,exist_ok=True)
    raw=protect(json.dumps(c).encode());f=d/'config.dpapi';tmp=d/('config-'+uuid.uuid4().hex+'.tmp')
    try:tmp.write_bytes(raw);os.replace(tmp,f)
    finally:tmp.unlink(missing_ok=True)
def validate(c):
    if not isinstance(c,dict):raise SetupError('Invalid configuration')
    for k in ('TRADING_GUARD_API_KEY','TRADING_APPROVAL_RECEIPT_KEY'):
        if not isinstance(c.get(k),str) or len(c[k])<32:raise SetupError('Invalid generated service credentials')
    if c['TRADING_GUARD_API_KEY']==c['TRADING_APPROVAL_RECEIPT_KEY']:raise SetupError('Keys must be independent')
    if not c.get('TRADING_APPROVER_EMAIL') or '@' not in c['TRADING_APPROVER_EMAIL']:raise SetupError('Email missing')
    if not c.get('TRADING_GOOGLE_CLIENT_ID') or not c.get('TRADING_GOOGLE_CLIENT_SECRET'):raise SetupError('Google OAuth client missing')
    if not pathlib.Path(c.get('TRADING_GUARD_DB','')).is_absolute():raise SetupError('Database requires an absolute shared path')
    return c
def setup():
    if (data_dir()/'config.dpapi').exists():raise SetupError('Config exista deja; nu suprascriu cheile. Foloseste pin sau porneste serviciile existente.')
    if sys.version_info<(3,10):raise SetupError('Instaleaza Python 3.10+ de pe python.org, cu Python Launcher.')
    email=input('Adresa Google autorizata (aceeasi pentru Gmail): ').strip().casefold()
    client=input('Google OAuth Web Client ID: ').strip();secret=getpass.getpass('Google OAuth Client Secret (ascuns): ').strip()
    c={'TRADING_APPROVER_EMAIL':email,'TRADING_GOOGLE_CLIENT_ID':client,'TRADING_GOOGLE_CLIENT_SECRET':secret,'TRADING_GOOGLE_SUB':'','TRADING_GUARD_API_KEY':secrets.token_urlsafe(48),'TRADING_APPROVAL_RECEIPT_KEY':secrets.token_urlsafe(48),'TRADING_GUARD_DB':str(data_dir()/'guard.sqlite3')}
    validate(c)
    import venv
    env=data_dir()/'venv';venv.EnvBuilder(with_pip=True).create(env)
    python=env/'Scripts'/'python.exe'
    subprocess.run([str(python),'-m','pip','install','-r',str(ROOT/'requirements.txt')],check=True)
    save(c);print('Configuratie salvata criptat pentru contul Windows curent. LIVE ramane blocat. Ruleaza: .\\Start-Windows.ps1 start')
def serve(role):
    c=validate(load());env={**os.environ,**c};env.pop('TRADING_APPROVER_ID',None)
    python=data_dir()/'venv'/'Scripts'/'python.exe'
    if not python.is_file():raise SetupError('Mediul Python lipseste; reinstaleaza dependentele in venv-ul local configurat.')
    print('Serviciu '+role+' pe loopback; Ctrl+C opreste acest proces. LIVE OFF.')
    try:return subprocess.call([str(python),str(ROOT/('server.py' if role=='guard' else 'oidc_server.py'))],cwd=ROOT,env=env)
    except KeyboardInterrupt:return 0
def start():
    validate(load())
    for role in ('guard','oidc'):
        # No credentials in command arguments or PowerShell command text.
        script=ROOT/'Start-Windows.ps1'
        subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-NoExit','-File',str(script),'serve','-Role',role],cwd=ROOT)
    print('Doua ferestre pornite. Nu le inchide in timpul testului. Continua cu check si configurarea Google SUB.')
def pin():
    c=validate(load());sub=input('Google sub afisat dupa login la http://localhost:8766/oidc/setup: ').strip()
    if not sub.isascii() or not sub.isdigit() or not 1<=len(sub)<=255:raise SetupError('Google sub invalid; foloseste identificatorul afisat dupa login verificat, nu emailul.')
    c['TRADING_GOOGLE_SUB']=sub;save(c)
    print('SUB fixat. Opreste AMBELE ferestre de servicii cu Ctrl+C si ruleaza start din nou; apoi check.')
def copy_key():
    c=validate(load());subprocess.run(['powershell.exe','-NoProfile','-Command','$v=[Console]::In.ReadToEnd(); Set-Clipboard -Value $v'],input=c['TRADING_GUARD_API_KEY'],text=True,check=True)
    print('Cheia Guard este in clipboard, nu in consola. Lipeste-o in credentialul Header Auth din n8n. Apoi goleste clipboardul.')
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args):return None
def request(base,path,key=None,body=None,allow_http_error=False):
    headers={}
    if key:headers['X-Guard-Key']=key
    if body is not None:headers['Content-Type']='application/json'
    req=Request(base+path,headers=headers,data=None if body is None else json.dumps(body).encode())
    with build_opener(NoRedirect()).open(req,timeout=5) as r:return json.load(r)
def checks(c,call=request):
    """Tests health plus all three workflow Guard contracts; no approval is fabricated."""
    validate(c);key=c['TRADING_GUARD_API_KEY'];guard='http://127.0.0.1:8765';oidc='http://localhost:8766'
    h=call(guard,'/v1/health',key);a=call(oidc,'/internal/readiness',key)
    for x in (h,a):
        if x.get('mode')!='SANDBOX' or x.get('live_enabled') is not False:raise SetupError('Refuz: serviciul nu confirma SANDBOX/LIVE OFF.')
    from runtime_config import readiness
    if h.get('configuration_fingerprint')!=readiness(c)['configuration_fingerprint'] or h.get('configuration_fingerprint')!=a.get('configuration_fingerprint'):raise SetupError('Guard/OIDC au configuratii diferite. Repornieste AMBELE din acelasi setup Windows.')
    for k in ('google_client_configured','google_subject_pinned','approver_email_configured'):
        if not h.get(k):raise SetupError('Configurare incompleta: '+k+'. Completeaza login setup/pin, apoi reporneste ambele servicii.')
    if h.get('approver_email')!=c['TRADING_APPROVER_EMAIL']:raise SetupError('Email Guard diferit de configuratia salvata')
    markets=call(guard,'/v1/markets',key)
    if markets.get('mode')!='SANDBOX' or markets.get('synthetic') is not True or markets.get('live_enabled') is not False:raise SetupError('Unexpected market source')
    if markets.get('approver_email')!=c['TRADING_APPROVER_EMAIL']:raise SetupError('Destinatar Gmail diferit')
    p=call(guard,'/v1/proposals',key,{'request_id':'windows-smoke:'+uuid.uuid4().hex,'candidate':{'pair':'TNK/USDC','side':'buy','price':1,'amount':5,'reason':'Local connectivity smoke test; reject immediately; no approval','ready_to_trade':True}})
    if p.get('live_enabled') is not False or p.get('state')!='PENDING' or not p.get('approval_url','').startswith('http://localhost:8766/approve?proposal_id='):raise SetupError('Unexpected proposal contract')
    pid=p['proposal_id'];r=call(guard,'/v1/proposals/'+pid,key)
    if r.get('state')!='PENDING':raise SetupError('Proposal read mismatch')
    # Only a rejection: the check never generates approval evidence or a market order.
    rejected=call(guard,'/v1/approve-and-simulate',key,{'proposal_id':pid,'gmail_approved':False})
    if rejected.get('order_sent') is not False:raise SetupError('Unexpected rejection response')
    r=call(guard,'/v1/proposals/'+pid,key)
    if r.get('state')!='REJECTED' or r.get('order_sent') is not False:raise SetupError('Persistent decision check failed')
    return {'guard':'OK','oidc_service':'OK','same_configuration':True,'three_guard_node_contracts':'OK','live_enabled':False,'order_sent':False,'google_real_login':'NOT_TESTED_BY_CHECK','gmail_delivery':'NOT_TESTED_BY_CHECK'}
def docker_probe(c):
    import shutil
    if not shutil.which('docker'):return 'not_detected'
    try:
        result=subprocess.run(['docker','ps','--format','{{.ID}} {{.Image}}'],capture_output=True,text=True,timeout=8)
        if result.returncode:return 'not_detected'
        ids=[line.split()[0] for line in result.stdout.splitlines() if len(line.split())==2 and 'n8n' in line.split()[1].lower()]
        if not ids:return 'not_detected'
        if len(ids)!=1:return 'ambiguous'
        js="let s='';process.stdin.on('data',b=>s+=b);process.stdin.on('end',()=>{const c=JSON.parse(s);const r=require('http').get({hostname:'host.docker.internal',port:8765,path:'/v1/health',headers:{'X-Guard-Key':c.key},timeout:4000},r=>{let b='';r.on('data',x=>{b+=x;if(b.length>16384)r.destroy();});r.on('end',()=>{try{const x=JSON.parse(b);process.exit(r.statusCode===200&&x.live_enabled===false&&x.configuration_fingerprint===c.fingerprint?0:1)}catch{process.exit(1)}})});r.on('error',()=>process.exit(1));r.on('timeout',()=>{r.destroy();process.exit(1)});});"
        from runtime_config import readiness
        p=subprocess.run(['docker','exec','-i',ids[0],'node','-e',js],input=json.dumps({'key':c['TRADING_GUARD_API_KEY'],'fingerprint':readiness(c)['configuration_fingerprint']}),capture_output=True,text=True,timeout=8)
        return 'reachable' if p.returncode==0 else 'unreachable'
    except (OSError,subprocess.TimeoutExpired):return 'unreachable'
def check():
    c=validate(load());result=checks(c)
    try:
        with urlopen('http://127.0.0.1:5678/healthz',timeout=3) as r:result['n8n_host_http']='reachable' if r.status==200 else 'unexpected_status'
    except OSError:result['n8n_host_http']='not_confirmed'
    base='http://127.0.0.1:8765'
    result['n8n_docker']=docker_probe(c)
    if result['n8n_docker']=='reachable':base='http://host.docker.internal:8765'
    if result['n8n_docker'] in ('unreachable','ambiguous'):
        print(json.dumps(result,indent=2));raise SetupError('n8n Docker nu poate fi configurat automat; vezi sectiunea Docker din WINDOWS.md. Nu schimb bindingul loopback si nu deschid firewallul.')
    workflow=json.loads((ROOT/'intercom_dex_WINDOWS_SANDBOX.json').read_text())
    for n in workflow['nodes']:
        if n['name']=='Local sandbox configuration':
            n['parameters']['jsCode']=n['parameters']['jsCode'].replace('http://127.0.0.1:8765',base)
    destination=data_dir()/'intercom_dex_WINDOWS_SANDBOX.json'
    destination.write_text(json.dumps(workflow,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));print('Importa workflow-ul configurat automat din: '+str(destination))
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['setup','start','serve','pin','copy-key','check']);p.add_argument('--role',choices=['guard','oidc']);a=p.parse_args()
    try:
        if a.action=='serve':
            if not a.role:raise SetupError('Specify --role guard or oidc')
            return serve(a.role)
        {'setup':setup,'start':start,'pin':pin,'copy-key':copy_key,'check':check}[a.action]()
        return 0
    except SetupError as e:
        print('STOP: '+str(e),file=sys.stderr);return 1
    except HTTPError as e:
        print('STOP HTTP '+str(e.code)+': 401 inseamna credential Guard diferit; 403 inseamna Host/OIDC refuzat; 409 inseamna refuz de validare. Nu s-a trimis niciun ordin.',file=sys.stderr);return 1
    except URLError:
        print('STOP: Guard/OIDC nu pot fi contactate pe porturile 8765/8766. Porneste ambele ferestre cu start; nu schimba nodurile individual.',file=sys.stderr);return 1
    except (OSError,subprocess.CalledProcessError,ValueError):
        # Do not serialize exception bodies which could contain credentials/provider output.
        print('Operatie oprita. Verifica pasul din WINDOWS.md: configuratie DPAPI, servicii pornite, porturi 8765/8766 sau identitate Google fixata. Nu s-a trimis niciun ordin.',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
