"""Trading gate. No live transport or signing is implemented; only synthetic markets."""
import hashlib,hmac,json,math,secrets,sqlite3,time,os
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation

LIVE_ENABLED=False  # Deliberate hard lock. Environment variables cannot enable this build.
PAIRS={'TNK/USDC','RESET/USDC'}
class Denied(Exception): pass
def canonical(x): return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def dec(x):
    if isinstance(x,bool) or not isinstance(x,(str,int,float,Decimal)): raise Denied('invalid_number')
    try: d=Decimal(str(x))
    except InvalidOperation: raise Denied('invalid_number')
    if not d.is_finite() or d<=0: raise Denied('nonpositive_or_nonfinite')
    return d
class SyntheticMarket:
    name='SYNTHETIC_ONLY'
    def __init__(self,clock=time.time):self.clock=clock;self.shift=Decimal('0');self.active=True
    def view(self,pair):
        if pair not in PAIRS:raise Denied('pair')
        return {'pair':pair,'bid':str(Decimal('0.99')+self.shift),'ask':str(Decimal('1')+self.shift),'availableBase':'100','timestamp':self.clock(),'active':self.active,'feeUSDC':'0.01','baseBalance':'100','quoteBalance':'100'}
class Guard:
    def __init__(self,db,market,receipt_key,approver,clock=time.time):
        self.db=db;self.market=market;self.key=receipt_key;self.approver=approver;self.clock=clock
        with self.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, body TEXT NOT NULL, digest TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, state TEXT NOT NULL, result TEXT);
CREATE TABLE IF NOT EXISTS receipts(nonce TEXT PRIMARY KEY, proposal_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, proposal_id TEXT, event TEXT NOT NULL);''')
    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.db,timeout=10,isolation_level=None);c.row_factory=sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA synchronous=FULL')
        try:
            with c:yield c
        finally:c.close()
    def check(self,p,m):
        if p.get('pair') not in PAIRS or m.get('pair')!=p['pair']:raise Denied('pair')
        if p.get('side') not in ('buy','sell'):raise Denied('side')
        now=self.clock();ts=m.get('timestamp')
        if not isinstance(ts,(float,int)) or not math.isfinite(ts) or not -1<=now-ts<=15:raise Denied('stale_market')
        if m.get('active') is not True:raise Denied('inactive_market')
        bid,ask=dec(m['bid']),dec(m['ask']);price,amount=dec(p['price']),dec(p['amount'])
        if bid>ask or (ask-bid)/ask>Decimal('0.02'):raise Denied('spread')
        if amount>dec(m['availableBase']):raise Denied('liquidity')
        fee=dec(m['feeUSDC']);notional=price*amount
        if 'maxFeeUSDC' in p and fee>dec(p['maxFeeUSDC']):raise Denied('approved_fee_cap')
        if notional+fee>Decimal('10'):raise Denied('max_10_including_fee')
        quote=ask if p['side']=='buy' else bid
        # No adverse drift: approved limit remains binding; reject rather than silently reprice.
        if (p['side']=='buy' and quote>price) or (p['side']=='sell' and quote<price):raise Denied('approved_limit_breached')
        if p['side']=='buy' and dec(m['quoteBalance'])<notional+fee:raise Denied('quote_balance')
        if p['side']=='sell' and dec(m['baseBalance'])<amount:raise Denied('base_balance')
    def create(self,request_id,candidate):
        if not isinstance(request_id,str) or not 1<=len(request_id)<=200:raise Denied('request_id')
        if candidate.get('ready_to_trade') is not True:raise Denied('WAIT')
        p={k:candidate.get(k) for k in ('pair','side','price','amount','reason')}
        if not isinstance(p['reason'],str) or not 1<=len(p['reason'])<=1000:raise Denied('reason')
        p['price']=str(dec(p['price']));p['amount']=str(dec(p['amount']))
        p.update(mode='SANDBOX',adapter=self.market.name,executionPolicy='LIMIT_ONLY_NO_REPRICE',maxTotalUSDC='10',expiresAfterSeconds=120)
        market=self.market.view(p['pair']);p['maxFeeUSDC']=str(dec(market['feeUSDC']))
        self.check(p,market);body=canonical(p);digest=hashlib.sha256(body.encode()).hexdigest();now=self.clock()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM proposals WHERE request_id=?',(request_id,)).fetchone()
            if old:
                if old['body']!=body:raise Denied('request_id_reused_with_other_content')
                c.rollback();return self.public(old)
            pid=secrets.token_hex(16);c.execute('INSERT INTO proposals VALUES(?,?,?,?,?,?,?,NULL)',(pid,request_id,body,digest,now,now+120,'PENDING'))
            c.execute('INSERT INTO events(at,proposal_id,event) VALUES(?,?,?)',(now,pid,'CREATED_SANDBOX'));c.commit()
            return self.public(c.execute('SELECT * FROM proposals WHERE id=?',(pid,)).fetchone())
    def public(self,r):return {'proposal_id':r['id'],'digest':r['digest'],'proposal':json.loads(r['body']),'expiresAt':r['expires'],'state':r['state'],'live_enabled':False}
    def verify_receipt(self,r,row):
        if len(self.key)<32 or not self.approver:raise Denied('authenticated_approver_not_configured')
        if not isinstance(r,dict):raise Denied('authenticated_receipt_required')
        sig=r.get('signature','');b={k:v for k,v in r.items() if k!='signature'}
        expected=hmac.new(self.key,canonical(b).encode(),hashlib.sha256).hexdigest()
        if not isinstance(sig,str) or not hmac.compare_digest(sig,expected):raise Denied('forged_receipt')
        if b.get('approver')!=self.approver or b.get('proposal_id')!=row['id'] or b.get('digest')!=row['digest'] or b.get('approved') is not True:raise Denied('approval_binding')
        now=self.clock();issued=b.get('issuedAt');expires=b.get('expiresAt');nonce=b.get('nonce')
        if not all(type(x) in (int,float) and math.isfinite(x) for x in (issued,expires)) or not issued<=now<expires<=min(row['expires'],issued+120):raise Denied('receipt_expired')
        if not isinstance(nonce,str) or not 16<=len(nonce)<=200:raise Denied('receipt_nonce')
        return nonce
    def approve(self,pid,gmail_approved,receipt=None):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM proposals WHERE id=?',(pid,)).fetchone()
            if not r:raise Denied('unknown_proposal')
            if r['state']!='PENDING':raise Denied('already_consumed')
            if os.path.exists(os.environ.get('TRADING_GUARD_HALT_FILE',self.db+'.halt')):raise Denied('operator_halt')
            if self.clock()>=r['expires']:raise Denied('proposal_expired')
            if gmail_approved is not True:
                c.execute("UPDATE proposals SET state='REJECTED' WHERE id=?",(pid,));c.commit();return {'status':'REJECTED','order_sent':False,'live_enabled':False}
            nonce=self.verify_receipt(receipt,r)
            try:c.execute('INSERT INTO receipts VALUES(?,?)',(nonce,pid))
            except sqlite3.IntegrityError:raise Denied('receipt_reused')
            p=json.loads(r['body']);self.check(p,self.market.view(p['pair']))
            # Conservative test budget: gross quoted exposure, not purported realized P&L.
            used=c.execute("SELECT body FROM proposals WHERE state='SIMULATED' AND created>=?",(self.clock()-86400,)).fetchall()
            total=sum((dec(json.loads(x['body'])['price'])*dec(json.loads(x['body'])['amount'])+dec(json.loads(x['body'])['maxFeeUSDC']) for x in used),Decimal('0'))
            if len(used)>=3 or total+dec(p['price'])*dec(p['amount'])+dec(p['maxFeeUSDC'])>Decimal('20'):raise Denied('daily_gross_exposure_stop')
            result={'status':'SIMULATED_LIMIT_ORDER_ONLY','order_sent':False,'live_enabled':False,'proposal_id':pid,'digest':r['digest'],'fresh_market_checked':True,'human_identity_evidence':'EXTERNAL_SIGNED_RECEIPT','no_fill_or_pnl_claim':True}
            c.execute("UPDATE proposals SET state='SIMULATED',result=? WHERE id=?",(canonical(result),pid));c.execute('INSERT INTO events(at,proposal_id,event) VALUES(?,?,?)',(self.clock(),pid,'SIMULATED_NO_ORDER'));c.commit();return result
    def execute_live(self,*args,**kwargs):raise Denied('LIVE_HARD_DISABLED_NO_VERIFIED_DEX_ADAPTER')
