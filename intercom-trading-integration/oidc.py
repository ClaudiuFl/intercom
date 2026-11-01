"""Google OIDC approver. Loopback HTTP only; no DEX transport. Requires PyJWT[crypto]."""
import hashlib,hmac,secrets,time,json,html,re,os
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,urlopen
import jwt
from guard import Guard,Denied,canonical

AUTH_URL='https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL='https://oauth2.googleapis.com/token'
JWKS_URL='https://www.googleapis.com/oauth2/v3/certs'
ISSUERS=('https://accounts.google.com','accounts.google.com')
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def pkce(verifier):
    import base64
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
class GoogleVerifier:
    def __init__(self,client_id,client_secret,redirect_uri):
        self.client_id=client_id;self.client_secret=client_secret;self.redirect_uri=redirect_uri
        self.jwks=jwt.PyJWKClient(JWKS_URL,cache_jwk_set=True,lifespan=300,timeout=10)
    def verify_token(self,token,nonce):
        key=self.jwks.get_signing_key_from_jwt(token).key
        c=jwt.decode(token,key,algorithms=['RS256'],audience=self.client_id,issuer=ISSUERS,leeway=5,
            options={'require':['exp','iat','iss','aud','sub','nonce','email','email_verified']})
        if c.get('azp',self.client_id)!=self.client_id or isinstance(c['aud'],list) and len(c['aud'])>1 and c.get('azp')!=self.client_id:raise Denied('wrong_authorized_party')
        if not isinstance(c['nonce'],str) or not hmac.compare_digest(c['nonce'],nonce):raise Denied('oidc_nonce')
        if c['email_verified'] is not True or not isinstance(c['sub'],str) or not c['sub']:raise Denied('unverified_identity')
        if time.time()-c['iat']>180:raise Denied('old_id_token')
        return c
    def exchange(self,code,verifier,nonce):
        data=urlencode({'code':code,'client_id':self.client_id,'client_secret':self.client_secret,'redirect_uri':self.redirect_uri,'grant_type':'authorization_code','code_verifier':verifier}).encode()
        with urlopen(Request(TOKEN_URL,data=data,headers={'Content-Type':'application/x-www-form-urlencoded'}),timeout=10) as r:
            raw=r.read(65537)
        if len(raw)>65536:raise Denied('token_response_size')
        token=json.loads(raw).get('id_token')
        if not isinstance(token,str):raise Denied('missing_id_token')
        return self.verify_token(token,nonce) # Never retain/return/log access or ID tokens.
class OIDCApproval:
    def __init__(self,guard,client,email,subject='',origin='http://localhost:8766'):
        self.g=guard;self.client=client;self.email=email.casefold();self.subject=subject;self.origin=origin
        if origin!='http://localhost:8766':raise Denied('this_build_requires_exact_localhost_origin')
        if client.redirect_uri!=origin+'/oidc/callback':raise Denied('redirect_uri')
        with guard.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS oidc_logins(state_hash TEXT PRIMARY KEY, browser_hash TEXT NOT NULL, nonce TEXT NOT NULL, verifier TEXT NOT NULL, proposal_id TEXT, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS oidc_sessions(sid_hash TEXT PRIMARY KEY, subject TEXT NOT NULL, proposal_id TEXT NOT NULL, proposal_digest TEXT NOT NULL, csrf_hash TEXT NOT NULL, expires REAL NOT NULL);''')
    def pending(self,pid):
        with self.g.connect() as c:r=c.execute('SELECT * FROM proposals WHERE id=?',(pid,)).fetchone()
        if not r or r['state']!='PENDING' or self.g.clock()>=r['expires']:raise Denied('proposal_not_pending_or_expired')
        if digest(r['body'])!=r['digest']:raise Denied('stored_content_mismatch')
        return r
    def start(self,pid=None):
        if pid is not None:
            if not isinstance(pid,str) or not re.fullmatch('[0-9a-f]{32}',pid):raise Denied('proposal_id')
            self.pending(pid)
        state,browser,nonce,verifier=(secrets.token_urlsafe(32) for _ in range(4));now=self.g.clock()
        with self.g.connect() as c:
            c.execute('DELETE FROM oidc_logins WHERE expires<=?',(now,));c.execute('DELETE FROM oidc_sessions WHERE expires<=?',(now,))
            if c.execute('SELECT count(*) FROM oidc_logins').fetchone()[0]>=1000:raise Denied('login_capacity')
            c.execute('INSERT INTO oidc_logins VALUES(?,?,?,?,?,?)',(digest(state),digest(browser),nonce,verifier,pid,now+120))
        url=AUTH_URL+'?'+urlencode({'client_id':self.client.client_id,'redirect_uri':self.client.redirect_uri,'response_type':'code','scope':'openid email','state':state,'nonce':nonce,'code_challenge':pkce(verifier),'code_challenge_method':'S256','prompt':'select_account','login_hint':self.email})
        return {'url':url,'browser':browser}
    def callback(self,state,browser,code):
        if not all(isinstance(s,str) and 0<len(s)<=4096 for s in (state,browser,code)):raise Denied('oidc_callback_parameters')
        with self.g.connect() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM oidc_logins WHERE state_hash=?',(digest(state),)).fetchone()
            if not r or self.g.clock()>=r['expires'] or not hmac.compare_digest(r['browser_hash'],digest(browser)):raise Denied('oidc_state_or_browser')
            c.execute('DELETE FROM oidc_logins WHERE state_hash=?',(digest(state),));c.commit()
        claims=self.client.exchange(code,r['verifier'],r['nonce'])
        if not isinstance(claims.get('email'),str) or claims['email'].casefold()!=self.email or claims.get('email_verified') is not True:raise Denied('wrong_google_account')
        if not r['proposal_id']:
            # Bootstrap displays the already verified subject; never auto-enrols it or approves a proposal.
            return {'setup_subject':claims['sub']}
        if not self.subject or claims['sub']!=self.subject or self.g.approver!=self.subject:raise Denied('google_subject_not_pinned')
        row=self.pending(r['proposal_id']);sid,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        with self.g.connect() as c:c.execute('INSERT INTO oidc_sessions VALUES(?,?,?,?,?,?)',(digest(sid),claims['sub'],row['id'],row['digest'],digest(csrf),min(row['expires'],self.g.clock()+120)))
        return {'sid':sid,'csrf':csrf,'proposal':self.g.public(row)}
    def decide(self,sid,csrf,decision,origin):
        if origin!=self.origin:raise Denied('csrf_origin')
        if decision not in ('approve','reject') or not isinstance(sid,str) or not isinstance(csrf,str):raise Denied('decision')
        with self.g.connect() as c:
            c.execute('BEGIN IMMEDIATE');s=c.execute('SELECT * FROM oidc_sessions WHERE sid_hash=?',(digest(sid),)).fetchone()
            if not s or self.g.clock()>=s['expires'] or not hmac.compare_digest(s['csrf_hash'],digest(csrf)):raise Denied('csrf_or_session')
            if s['subject']!=self.subject or not self.subject:raise Denied('subject_changed')
            c.execute('DELETE FROM oidc_sessions WHERE sid_hash=?',(digest(sid),));c.commit()
        row=self.pending(s['proposal_id'])
        if row['digest']!=s['proposal_digest']:raise Denied('proposal_changed')
        if decision=='reject':return self.g.approve(row['id'],False)
        now=self.g.clock();receipt={'proposal_id':row['id'],'digest':row['digest'],'approver':s['subject'],'approved':True,'issuedAt':now,'expiresAt':min(row['expires'],now+30),'nonce':secrets.token_hex(16)}
        receipt['signature']=hmac.new(self.g.key,canonical(receipt).encode(),hashlib.sha256).hexdigest()
        return self.g.approve(row['id'],True,receipt) # Revalidates market under the persistent gate; simulation ONLY.

def confirmation_page(result):
    p=result['proposal'];esc=lambda x:html.escape(str(x),quote=True)
    return ('<!doctype html><meta charset="utf-8"><title>Aprobare Intercom SANDBOX</title><h1>LIVE dezactivat — date sintetice</h1>'
        '<p>Autentificarea nu aprobă nimic. Confirmă explicit propunerea de mai jos.</p><pre>'+esc(json.dumps(p,indent=2,ensure_ascii=True))+'</pre>'
        '<form method="post" action="/decision"><input type="hidden" name="csrf" value="'+esc(result['csrf'])+'">'
        '<button name="decision" value="approve">Aprob numai simularea acestei propuneri</button> '
        '<button name="decision" value="reject">Resping</button></form>')
