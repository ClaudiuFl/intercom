import unittest,subprocess,os,secrets,tempfile,time,json,urllib.request,urllib.error,pathlib,hmac,hashlib
class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.api=secrets.token_hex(32);cls.receipt_key=secrets.token_hex(32)
        env={**os.environ,'TRADING_GUARD_API_KEY':cls.api,'TRADING_APPROVAL_RECEIPT_KEY':cls.receipt_key,'TRADING_APPROVER_ID':'test-user','TRADING_GUARD_DB':str(pathlib.Path(cls.tmp.name)/'state.db')}
        cls.p=subprocess.Popen(['python','server.py'],cwd=pathlib.Path(__file__).parent,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        for _ in range(50):
            if cls.p.poll() is not None:raise RuntimeError('Guard failed to bind dedicated test port')
            try:
                cls.request('/v1/health');return
            except OSError:time.sleep(.05)
        raise RuntimeError('Guard startup timeout')
    @classmethod
    def tearDownClass(cls):cls.p.terminate();cls.p.communicate(timeout=5);cls.tmp.cleanup()
    @classmethod
    def request(cls,path,body=None,key=None):
        r=urllib.request.Request('http://127.0.0.1:8765'+path,data=None if body is None else json.dumps(body).encode(),headers={'X-Guard-Key':cls.api if key is None else key,'Content-Type':'application/json'})
        with urllib.request.urlopen(r,timeout=3) as resp:return json.load(resp)
    def test_full_signed_sandbox_flow(self):
        feed=self.request('/v1/markets');self.assertTrue(feed['synthetic'])
        p=self.request('/v1/proposals',{'request_id':'http-flow','candidate':{'pair':'TNK/USDC','side':'buy','price':1,'amount':5,'ready_to_trade':True,'reason':'synthetic'}})
        with self.assertRaises(urllib.error.HTTPError) as err:self.request('/v1/approve-and-simulate',{'proposal_id':p['proposal_id'],'gmail_approved':True})
        self.assertEqual(err.exception.code,409)
        now=time.time();r={'proposal_id':p['proposal_id'],'digest':p['digest'],'approver':'test-user','approved':True,'issuedAt':now,'expiresAt':now+30,'nonce':secrets.token_hex(16)}
        raw=json.dumps(r,sort_keys=True,separators=(',',':'),allow_nan=False)
        r['signature']=hmac.new(self.receipt_key.encode(),raw.encode(),hashlib.sha256).hexdigest()
        self.request('/v1/approval-evidence',{'proposal_id':p['proposal_id'],'receipt':r})
        result=self.request('/v1/approve-and-simulate',{'proposal_id':p['proposal_id'],'gmail_approved':True});self.assertFalse(result['order_sent']);self.assertTrue(result['fresh_market_checked'])
        with self.assertRaises(urllib.error.HTTPError):self.request('/v1/approve-and-simulate',{'proposal_id':p['proposal_id'],'gmail_approved':True})
    def test_unauthenticated_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as err:self.request('/v1/markets',key='invalid')
        self.assertEqual(err.exception.code,401)
    def test_no_execution_route(self):
        for path in ('/prepare','/execute','/v1/live'):
            with self.assertRaises(urllib.error.HTTPError) as err:self.request(path,{'approved':True})
            self.assertEqual(err.exception.code,404)
if __name__=='__main__':unittest.main(verbosity=2)
