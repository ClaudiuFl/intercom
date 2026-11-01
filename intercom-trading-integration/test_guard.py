import unittest,tempfile,pathlib,hashlib,hmac,threading,json
from concurrent.futures import ThreadPoolExecutor
from guard import *
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1000.;self.key=b'x'*32;self.market=SyntheticMarket(lambda:self.now)
        self.g=Guard(str(pathlib.Path(self.tmp.name)/'state.db'),self.market,self.key,'approved-user',lambda:self.now)
    def tearDown(self):self.tmp.cleanup()
    def create(self,req='r1',**kwargs):
        c=dict(pair='TNK/USDC',side='buy',price=1,amount=5,reason='synthetic',ready_to_trade=True);c.update(kwargs);return self.g.create(req,c)
    def receipt(self,p,**kw):
        r=dict(proposal_id=p['proposal_id'],digest=p['digest'],approver='approved-user',approved=True,issuedAt=self.now,expiresAt=min(self.now+60,p['expiresAt']),nonce=secrets.token_hex(16));r.update(kw)
        r['signature']=hmac.new(self.key,canonical(r).encode(),hashlib.sha256).hexdigest();return r
    def test_approved_simulates_only(self):
        p=self.create();r=self.g.approve(p['proposal_id'],True,self.receipt(p));self.assertFalse(r['order_sent']);self.assertEqual(r['status'],'SIMULATED_LIMIT_ORDER_ONLY')
    def test_reject_persistent(self):
        p=self.create();self.assertEqual(self.g.approve(p['proposal_id'],False)['status'],'REJECTED')
        with self.assertRaisesRegex(Denied,'already_consumed'):self.g.approve(p['proposal_id'],True,self.receipt(p))
    def test_gmail_boolean_not_identity(self):
        p=self.create()
        with self.assertRaisesRegex(Denied,'receipt_required'):self.g.approve(p['proposal_id'],True)
    def test_forged(self):
        p=self.create();r=self.receipt(p);r['approver']='attacker'
        with self.assertRaisesRegex(Denied,'forged'):self.g.approve(p['proposal_id'],True,r)
    def test_wrong_digest(self):
        p=self.create()
        with self.assertRaisesRegex(Denied,'binding'):self.g.approve(p['proposal_id'],True,self.receipt(p,digest='other'))
    def test_wrong_person(self):
        p=self.create()
        with self.assertRaisesRegex(Denied,'binding'):self.g.approve(p['proposal_id'],True,self.receipt(p,approver='attacker'))
    def test_expired_proposal(self):
        p=self.create();r=self.receipt(p);self.now+=121
        with self.assertRaisesRegex(Denied,'proposal_expired'):self.g.approve(p['proposal_id'],True,r)
    def test_expired_receipt(self):
        p=self.create();r=self.receipt(p);self.now+=61
        with self.assertRaisesRegex(Denied,'receipt_expired'):self.g.approve(p['proposal_id'],True,r)
    def test_market_moves_after_approval(self):
        p=self.create();r=self.receipt(p);self.market.shift=Decimal('.01')
        with self.assertRaisesRegex(Denied,'limit_breached'):self.g.approve(p['proposal_id'],True,r)
    def test_market_pauses(self):
        p=self.create();r=self.receipt(p);self.market.active=False
        with self.assertRaisesRegex(Denied,'inactive'):self.g.approve(p['proposal_id'],True,r)
    def test_fee_cap(self):
        p=self.create();r=self.receipt(p);view=self.market.view;self.market.view=lambda pair:{**view(pair),'feeUSDC':'.02'}
        with self.assertRaisesRegex(Denied,'fee_cap'):self.g.approve(p['proposal_id'],True,r)
    def test_gross_daily_cap(self):
        for i in range(2):
            p=self.create(str(i),amount=8);self.g.approve(p['proposal_id'],True,self.receipt(p))
        p=self.create('third',amount=8)
        with self.assertRaisesRegex(Denied,'daily_gross'):self.g.approve(p['proposal_id'],True,self.receipt(p))
    def test_max_with_fees(self):
        with self.assertRaisesRegex(Denied,'max_10'):self.create(amount=10)
    def test_nonfinite(self):
        with self.assertRaises(Denied):self.create(price=float('nan'))
    def test_wait(self):
        with self.assertRaisesRegex(Denied,'WAIT'):self.create(ready_to_trade=False)
    def test_idempotent_creation(self):
        p=self.create();self.assertEqual(p,self.create())
        with self.assertRaisesRegex(Denied,'request_id'):self.create(amount=4)
    def test_concurrent_duplicate_approval(self):
        p=self.create();r=self.receipt(p)
        def attempt(_):
            try:return self.g.approve(p['proposal_id'],True,r)['status']
            except Denied as e:return str(e)
        with ThreadPoolExecutor(2) as pool:out=list(pool.map(attempt,range(2)))
        self.assertEqual(out.count('SIMULATED_LIMIT_ORDER_ONLY'),1);self.assertEqual(out.count('already_consumed'),1)
    def test_restart_duplicate(self):
        p=self.create();r=self.receipt(p);self.g.approve(p['proposal_id'],True,r)
        again=Guard(self.g.db,self.market,self.key,'approved-user',lambda:self.now)
        with self.assertRaisesRegex(Denied,'already_consumed'):again.approve(p['proposal_id'],True,r)
    def test_halt(self):
        p=self.create();pathlib.Path(self.g.db+'.halt').touch()
        with self.assertRaisesRegex(Denied,'operator_halt'):self.g.approve(p['proposal_id'],True,self.receipt(p))
    def test_sell(self):
        p=self.create(side='sell',price=.99);self.assertFalse(self.g.approve(p['proposal_id'],True,self.receipt(p))['order_sent'])
    def test_live_permanently_locked(self):
        self.assertFalse(LIVE_ENABLED)
        with self.assertRaisesRegex(Denied,'LIVE_HARD_DISABLED'):self.g.execute_live()
    def test_workflow_structure(self):
        w=json.loads((pathlib.Path(__file__).parent/'intercom_dex_gmail_guard_SANDBOX.json').read_text());self.assertFalse(w['active']);names={n['name'] for n in w['nodes']}
        for source,ports in w['connections'].items():
            self.assertIn(source,names)
            for branches in ports.values():
                for branch in branches:
                    for e in branch:self.assertIn(e['node'],names)
        for n in w['nodes']:
            self.assertNotIn('credentials',n)
            if n['type'].endswith('httpRequest'):
                self.assertNotIn('/prepare',n['parameters']['url']);self.assertNotIn('/execute',n['parameters']['url']);self.assertFalse(n['retryOnFail'])
        self.assertEqual(w['connections']['If Gmail Approved']['main'][0][0]['node'],'Guard - revalidate and SIMULATE only')
if __name__=='__main__':unittest.main(verbosity=2)
