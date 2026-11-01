import unittest,subprocess,tempfile,os,secrets,pathlib,time,urllib.request,urllib.error,json
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None
class OIDCHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.db=str(pathlib.Path(cls.tmp.name)/'db');cls.key=secrets.token_hex(32)
        env={**os.environ,'TRADING_GUARD_DB':cls.db,'TRADING_APPROVAL_RECEIPT_KEY':cls.key,'TRADING_GOOGLE_CLIENT_ID':'test-client','TRADING_GOOGLE_CLIENT_SECRET':'test-secret-not-real','TRADING_APPROVER_EMAIL':'owner@example.invalid','TRADING_GOOGLE_SUB':'test-subject'}
        cls.p=subprocess.Popen(['python','oidc_server.py'],cwd=pathlib.Path(__file__).parent,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        cls.opener=urllib.request.build_opener(NoRedirect())
        for _ in range(50):
            if cls.p.poll() is not None:raise RuntimeError('OIDC test server failed to bind')
            try:cls.request('/missing')
            except urllib.error.HTTPError:return
            except OSError:time.sleep(.05)
        raise RuntimeError('OIDC test server startup timeout')
    @classmethod
    def tearDownClass(cls):cls.p.terminate();cls.p.communicate(timeout=5);cls.tmp.cleanup()
    @classmethod
    def request(cls,path,host='localhost:8766',body=None,origin=None):
        headers={'Host':host}
        if body is not None:headers['Content-Type']='application/x-www-form-urlencoded'
        if origin:headers['Origin']=origin
        return cls.opener.open(urllib.request.Request('http://127.0.0.1:8766'+path,data=body,headers=headers),timeout=3)
    def test_start_redirects_without_following_google(self):
        with self.assertRaises(urllib.error.HTTPError) as err:self.request('/oidc/setup')
        self.assertEqual(err.exception.code,303);self.assertTrue(err.exception.headers['Location'].startswith('https://accounts.google.com/'));self.assertIn('HttpOnly',err.exception.headers['Set-Cookie']);self.assertEqual(err.exception.headers['Cache-Control'],'no-store')
    def test_host_rebinding_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as err:self.request('/oidc/setup',host='evil.invalid:8766')
        self.assertEqual(err.exception.code,403)
    def test_invalid_callback_does_not_exchange_code(self):
        with self.assertRaises(urllib.error.HTTPError) as err:self.request('/oidc/callback?state=bogus&code=bogus')
        self.assertEqual(err.exception.code,403)
    def test_unauthenticated_confirmation_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as err:self.request('/decision',body=b'csrf=bad&decision=approve',origin='http://localhost:8766')
        self.assertEqual(err.exception.code,403)
if __name__=='__main__':unittest.main(verbosity=2)
