"""Private guard HTTP API, not an Intercom DEX API. Never exposes a live route."""
import hmac,json,os,sqlite3
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from guard import Guard,SyntheticMarket,Denied,canonical
os.umask(0o077)
API_KEY=os.environ.get('TRADING_GUARD_API_KEY','')
RECEIPT_KEY=os.environ.get('TRADING_APPROVAL_RECEIPT_KEY','')
APPROVER=os.environ.get('TRADING_GOOGLE_SUB',os.environ.get('TRADING_APPROVER_ID',''))
if len(API_KEY)<32:raise SystemExit('Set a random TRADING_GUARD_API_KEY of at least 32 characters; do not print it.')
g=Guard(os.environ.get('TRADING_GUARD_DB','guard.sqlite3'),SyntheticMarket(),RECEIPT_KEY.encode(),APPROVER)
with g.connect() as c:c.execute('CREATE TABLE IF NOT EXISTS evidence(proposal_id TEXT PRIMARY KEY, receipt TEXT NOT NULL)')
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass # No tokens, approval bodies, or personal data in HTTP logs.
    def reply(self,status,obj):
        b=canonical(obj).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def authorized(self):return hmac.compare_digest(self.headers.get('X-Guard-Key',''),API_KEY)
    def do_GET(self):
        if not self.authorized():return self.reply(401,{'error':'unauthorized'})
        if self.path=='/v1/markets':return self.reply(200,{'pairs':[g.market.view(p) for p in sorted(__import__('guard').PAIRS)],'mode':'SANDBOX','synthetic':True,'live_enabled':False})
        if self.path.startswith('/v1/proposals/'):
            import re,time
            pid=self.path.removeprefix('/v1/proposals/')
            if not re.fullmatch('[0-9a-f]{32}',pid):return self.reply(404,{'error':'proposal_id'})
            with g.connect() as c:
                c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM proposals WHERE id=?',(pid,)).fetchone()
                if not row:return self.reply(404,{'error':'unknown_proposal'})
                if row['state']=='PENDING' and g.clock()>=row['expires']:
                    c.execute("UPDATE proposals SET state='EXPIRED' WHERE id=?",(pid,))
                row=c.execute('SELECT * FROM proposals WHERE id=?',(pid,)).fetchone();c.commit()
            return self.reply(200,{**g.public(row),'result':json.loads(row['result']) if row['result'] else None,'order_sent':False,'pending':row['state']=='PENDING'})
        if self.path=='/v1/health':return self.reply(200,{'mode':'SANDBOX','live_enabled':False,'dex_adapter':'NOT_IMPLEMENTED','authenticated_approver_configured':bool(RECEIPT_KEY and APPROVER)})
        self.reply(404,{'error':'route_not_available'})
    def do_POST(self):
        if not self.authorized():return self.reply(401,{'error':'unauthorized'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=32768:raise Denied('body_size')
            x=json.loads(self.rfile.read(size),parse_constant=lambda _: (_ for _ in ()).throw(Denied('nonfinite_json')))
            if not isinstance(x,dict):raise Denied('body_object_required')
            if self.path=='/v1/proposals':
                result=g.create(x.get('request_id'),x.get('candidate',{}))
                result['approval_url']='http://localhost:8766/approve?proposal_id='+result['proposal_id']
            elif self.path=='/v1/approval-evidence':
                # The identity gateway must authenticate the human before signing this receipt.
                # This route cannot turn Gmail's approved=true into identity evidence.
                pid=x.get('proposal_id');receipt=x.get('receipt')
                with g.connect() as c:
                    row=c.execute('SELECT * FROM proposals WHERE id=?',(pid,)).fetchone()
                    if not row:raise Denied('unknown_proposal')
                    if row['state']!='PENDING':raise Denied('already_consumed')
                    g.verify_receipt(receipt,row)
                    c.execute('INSERT INTO evidence VALUES(?,?)',(pid,canonical(receipt)))
                result={'status':'SIGNED_EVIDENCE_STORED','order_sent':False}
            elif self.path=='/v1/approve-and-simulate':
                pid=x.get('proposal_id')
                with g.connect() as c:r=c.execute('SELECT receipt FROM evidence WHERE proposal_id=?',(pid,)).fetchone()
                result=g.approve(pid,x.get('gmail_approved'),json.loads(r['receipt']) if r else None)
            else:return self.reply(404,{'error':'route_not_available','live_enabled':False})
            self.reply(200,result)
        except (Denied,KeyError,TypeError,ValueError,sqlite3.IntegrityError) as e:self.reply(409,{'error':str(e) if isinstance(e,Denied) else 'invalid_request_or_duplicate','order_sent':False,'live_enabled':False})
        except Exception:self.reply(500,{'error':'internal_error_fail_closed','order_sent':False,'live_enabled':False})
if __name__=='__main__':
    # Loopback only. Deploy behind an authenticated TLS reverse proxy if n8n runs elsewhere.
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
