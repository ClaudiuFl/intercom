import unittest,tempfile,pathlib,secrets,time,copy,json
from urllib.parse import urlsplit,parse_qs
from concurrent.futures import ThreadPoolExecutor
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from guard import Guard,SyntheticMarket,Denied
from oidc import OIDCApproval,GoogleVerifier,confirmation_page
class FakeGoogle:
    client_id='test-client';redirect_uri='http://localhost:8766/oidc/callback'
    def __init__(self):self.claims={'sub':'test-subject','email':'owner@example.invalid','email_verified':True}
    def exchange(self,code,verifier,nonce):return self.claims
class OIDCTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1000.;self.g=Guard(str(pathlib.Path(self.tmp.name)/'db'),SyntheticMarket(lambda:self.now),b'r'*32,'test-subject',lambda:self.now)
        self.client=FakeGoogle();self.a=OIDCApproval(self.g,self.client,'owner@example.invalid','test-subject')
        self.p=self.g.create('r',{'pair':'RESET/USDC','side':'buy','price':1,'amount':2,'ready_to_trade':True,'reason':'synthetic'})
    def tearDown(self):self.tmp.cleanup()
    def start(self,pid=True):
        s=self.a.start(self.p['proposal_id'] if pid else None);state=parse_qs(urlsplit(s['url']).query)['state'][0];return s,state
    def login(self):
        s,state=self.start();return self.a.callback(state,s['browser'],'test-code')
    def test_get_and_login_do_not_approve(self):
        r=self.login();self.assertEqual(self.a.pending(self.p['proposal_id'])['state'],'PENDING');self.assertIn('method="post"',confirmation_page(r))
    def test_explicit_post_simulates(self):
        r=self.login();out=self.a.decide(r['sid'],r['csrf'],'approve',self.a.origin);self.assertFalse(out['order_sent']);self.assertEqual(out['status'],'SIMULATED_LIMIT_ORDER_ONLY')
    def test_refuse_wrong_account(self):
        self.client.claims={**self.client.claims,'email':'other@example.invalid'}
        with self.assertRaisesRegex(Denied,'wrong_google_account'):self.login()
    def test_refuse_unverified_email(self):
        self.client.claims={**self.client.claims,'email_verified':False}
        with self.assertRaises(Denied):self.login()
    def test_refuse_wrong_subject(self):
        self.client.claims={**self.client.claims,'sub':'other'}
        with self.assertRaisesRegex(Denied,'not_pinned'):self.login()
    def test_setup_no_auto_enrol(self):
        self.a.subject='';s,state=self.start(False);r=self.a.callback(state,s['browser'],'test-code');self.assertEqual(r,{'setup_subject':'test-subject'});self.assertEqual(self.a.pending(self.p['proposal_id'])['state'],'PENDING')
    def test_state_replay(self):
        s,state=self.start();self.a.callback(state,s['browser'],'test-code')
        with self.assertRaises(Denied):self.a.callback(state,s['browser'],'test-code')
    def test_state_requires_same_browser(self):
        s,state=self.start()
        with self.assertRaises(Denied):self.a.callback(state,'attacker','test-code')
    def test_csrf(self):
        r=self.login()
        with self.assertRaisesRegex(Denied,'csrf'):self.a.decide(r['sid'],'bad','approve',self.a.origin)
    def test_origin(self):
        r=self.login()
        with self.assertRaisesRegex(Denied,'origin'):self.a.decide(r['sid'],r['csrf'],'approve','https://evil.invalid')
    def test_session_replay(self):
        r=self.login();self.a.decide(r['sid'],r['csrf'],'approve',self.a.origin)
        with self.assertRaises(Denied):self.a.decide(r['sid'],r['csrf'],'approve',self.a.origin)
    def test_expiry_after_login(self):
        r=self.login();self.now+=121
        with self.assertRaises(Denied):self.a.decide(r['sid'],r['csrf'],'approve',self.a.origin)
    def test_market_changed_after_login(self):
        r=self.login();self.g.market.shift=__import__('decimal').Decimal('.01')
        with self.assertRaisesRegex(Denied,'limit'):self.a.decide(r['sid'],r['csrf'],'approve',self.a.origin)
    def test_reject(self):
        r=self.login();self.assertEqual(self.a.decide(r['sid'],r['csrf'],'reject',self.a.origin)['status'],'REJECTED')
    def test_simultaneous_post(self):
        r=self.login()
        def run(_):
            try:return self.a.decide(r['sid'],r['csrf'],'approve',self.a.origin)['status']
            except Denied:return 'DENIED'
        with ThreadPoolExecutor(2) as pool:out=list(pool.map(run,range(2)))
        self.assertEqual(out.count('SIMULATED_LIMIT_ORDER_ONLY'),1)
    def test_new_workflow_no_gmail_resume(self):
        w=json.loads((pathlib.Path(__file__).parent/'intercom_dex_GMAIL_OIDC_SANDBOX.json').read_text());self.assertFalse(w['active']);names={n['name'] for n in w['nodes']}
        for n in w['nodes']:
            self.assertNotEqual(n['parameters'].get('operation'),'sendAndWait')
            if n['type'].endswith('httpRequest'):self.assertNotIn('/prepare',n['parameters']['url']);self.assertNotIn('/take',n['parameters']['url'])
        for src,ports in w['connections'].items():
            self.assertIn(src,names)
            for branches in ports.values():
                for branch in branches:
                    for target in branch:self.assertIn(target['node'],names)
class JWTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    def setUp(self):
        self.v=GoogleVerifier('test-client','not-a-real-secret','http://localhost:8766/oidc/callback')
        key=self.key.public_key()
        class FakeJWKS:
            def get_signing_key_from_jwt(self,token):return type('K',(),{'key':key})()
        self.v.jwks=FakeJWKS();now=int(time.time());self.claims={'iss':'https://accounts.google.com','aud':'test-client','sub':'test-subject','email':'owner@example.invalid','email_verified':True,'nonce':'nonce','iat':now,'exp':now+60}
    def token(self,**kw):return jwt.encode({**self.claims,**kw},self.key,algorithm='RS256',headers={'kid':'local-test'})
    def test_valid_signature_and_claims(self):self.assertEqual(self.v.verify_token(self.token(),'nonce')['sub'],'test-subject')
    def test_wrong_issuer(self):
        with self.assertRaises(Exception):self.v.verify_token(self.token(iss='https://evil.invalid'),'nonce')
    def test_wrong_audience(self):
        with self.assertRaises(Exception):self.v.verify_token(self.token(aud='other-client'),'nonce')
    def test_wrong_nonce(self):
        with self.assertRaises(Denied):self.v.verify_token(self.token(),'wrong')
    def test_wrong_signature(self):
        other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        token=jwt.encode(self.claims,other,algorithm='RS256')
        with self.assertRaises(jwt.InvalidSignatureError):self.v.verify_token(token,'nonce')
    def test_expired_token(self):
        with self.assertRaises(jwt.ExpiredSignatureError):self.v.verify_token(self.token(exp=int(time.time())-60),'nonce')
    def test_wrong_algorithm(self):
        with self.assertRaises(jwt.InvalidAlgorithmError):self.v.verify_token(jwt.encode(self.claims,'x'*32,algorithm='HS256'),'nonce')
if __name__=='__main__':unittest.main(verbosity=2)
