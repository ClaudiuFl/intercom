import os,json,html
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import urlsplit,parse_qs
from guard import Guard,SyntheticMarket,Denied
from oidc import GoogleVerifier,OIDCApproval,confirmation_page

def main():
    os.umask(0o077)
    required=('TRADING_GOOGLE_CLIENT_ID','TRADING_GOOGLE_CLIENT_SECRET','TRADING_APPROVER_EMAIL','TRADING_APPROVAL_RECEIPT_KEY')
    if any(not os.environ.get(k) for k in required):raise SystemExit('Missing OIDC configuration; see GOOGLE_OIDC.md. Never put secrets in chat.')
    key=os.environ['TRADING_APPROVAL_RECEIPT_KEY'].encode()
    if len(key)<32:raise SystemExit('Receipt key requires at least 32 bytes.')
    subject=os.environ.get('TRADING_GOOGLE_SUB','')
    g=Guard(os.environ.get('TRADING_GUARD_DB','guard.sqlite3'),SyntheticMarket(),key,subject)
    verifier=GoogleVerifier(os.environ['TRADING_GOOGLE_CLIENT_ID'],os.environ['TRADING_GOOGLE_CLIENT_SECRET'],'http://localhost:8766/oidc/callback')
    a=OIDCApproval(g,verifier,os.environ['TRADING_APPROVER_EMAIL'],subject)
    class H(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def page(self,code,body,cookie=None,location=None):
            raw=body.encode();self.send_response(code)
            headers={'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",'Content-Length':str(len(raw))}
            if cookie:headers['Set-Cookie']=cookie
            if location:headers['Location']=location
            for k,v in headers.items():self.send_header(k,v)
            self.end_headers();self.wfile.write(raw)
        def ck(self,name):
            c=SimpleCookie();c.load(self.headers.get('Cookie',''));return c[name].value if name in c else ''
        def host_ok(self):return self.headers.get('Host')=='localhost:8766'
        def do_GET(self):
            if not self.host_ok():return self.page(403,'Host refused')
            try:
                u=urlsplit(self.path);q=parse_qs(u.query,keep_blank_values=True)
                if any(len(v)!=1 for v in q.values()):raise Denied('duplicate_parameters')
                if u.path in ('/approve','/oidc/setup'):
                    if set(q)-{'proposal_id'}:raise Denied('unknown_parameter')
                    pid=q.get('proposal_id',[None])[0] if u.path=='/approve' else None
                    if u.path=='/approve' and not pid:raise Denied('proposal_id_required')
                    r=a.start(pid);return self.page(303,'Redirecting to Google','oidc_browser='+r['browser']+'; HttpOnly; SameSite=Lax; Path=/; Max-Age=120',r['url'])
                if u.path=='/oidc/callback':
                    if set(q)-{'state','code','scope','authuser','prompt','hd'}:raise Denied('oidc_error_or_unknown_parameter')
                    r=a.callback(q.get('state',[''])[0],self.ck('oidc_browser'),q.get('code',[''])[0])
                    if 'setup_subject' in r:return self.page(200,'<!doctype html><meta charset="utf-8"><h1>Identitate verificată, fără aprobare</h1><p>Configurează TRADING_GOOGLE_SUB cu:</p><pre>'+html.escape(r['setup_subject'])+'</pre><p>Repornește serviciile. Nicio propunere nu a fost aprobată.</p>','oidc_browser=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0')
                    return self.page(200,confirmation_page(r),'approval_session='+r['sid']+'; HttpOnly; SameSite=Lax; Path=/; Max-Age=120')
                return self.page(404,'Not found')
            except Exception:return self.page(403,'<!doctype html><meta charset="utf-8"><p>Autentificare refuzată, propunere expirată sau eroare de verificare. Nicio tranzacție nu a fost trimisă. Reia din email pentru o propunere încă validă.</p>')
        def do_POST(self):
            if not self.host_ok():return self.page(403,'Host refused')
            try:
                if self.path!='/decision':raise Denied('route')
                if self.headers.get('Content-Type','').split(';')[0]!='application/x-www-form-urlencoded':raise Denied('content_type')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4096:raise Denied('body_size')
                q=parse_qs(self.rfile.read(size).decode(),keep_blank_values=True)
                if set(q)!={'csrf','decision'} or any(len(v)!=1 for v in q.values()):raise Denied('form')
                r=a.decide(self.ck('approval_session'),q['csrf'][0],q['decision'][0],self.headers.get('Origin',''))
                return self.page(200,'<!doctype html><meta charset="utf-8"><h1>Rezultat SANDBOX</h1><pre>'+html.escape(json.dumps(r,indent=2))+'</pre>','approval_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0')
            except Exception:return self.page(403,'<!doctype html><meta charset="utf-8"><p>Operație refuzată sau rezultat neconfirmat. Nu s-a trimis nicio tranzacție reală; verifică starea propunerii în n8n înainte să încerci din nou.</p>')
    srv=ThreadingHTTPServer(('127.0.0.1',8766),H);srv.timeout=10;srv.serve_forever()
if __name__=='__main__':main()
