import unittest,tempfile,pathlib,os,json,sys,subprocess,secrets,time
from unittest.mock import patch
import windows_setup as win
from runtime_config import readiness
class WindowsContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.config={'TRADING_GUARD_DB':str(pathlib.Path(self.tmp.name)/'state.db'),'TRADING_GUARD_API_KEY':'a'*48,'TRADING_APPROVAL_RECEIPT_KEY':'b'*48,'TRADING_APPROVER_EMAIL':'owner@example.invalid','TRADING_GOOGLE_CLIENT_ID':'test-client','TRADING_GOOGLE_CLIENT_SECRET':'test-only-not-real','TRADING_GOOGLE_SUB':'123456789012345678901'}
    def tearDown(self):self.tmp.cleanup()
    def test_independent_keys_required(self):
        with self.assertRaises(win.SetupError):win.validate({**self.config,'TRADING_APPROVAL_RECEIPT_KEY':self.config['TRADING_GUARD_API_KEY']})
    def test_absolute_db_required(self):
        with self.assertRaises(win.SetupError):win.validate({**self.config,'TRADING_GUARD_DB':'relative.db'})
    def test_fingerprint_changes_on_mismatched_subject(self):self.assertNotEqual(readiness(self.config)['configuration_fingerprint'],readiness({**self.config,'TRADING_GOOGLE_SUB':'other'})['configuration_fingerprint'])
    def test_fingerprint_does_not_contain_secrets(self):
        s=json.dumps(readiness(self.config));self.assertNotIn(self.config['TRADING_GUARD_API_KEY'],s);self.assertNotIn(self.config['TRADING_GOOGLE_CLIENT_SECRET'],s)
    def test_no_plaintext_fallback_on_linux(self):
        if os.name=='nt':self.skipTest('Non-Windows refusal test')
        with self.assertRaises(win.SetupError):win.protect(b'test-only')
    def test_workflow_three_guard_nodes_no_vars(self):
        w=json.loads((pathlib.Path(__file__).parent/'intercom_dex_WINDOWS_SANDBOX.json').read_text());self.assertFalse(w['active']);self.assertEqual(w['pinData'],{});self.assertNotIn('$vars',json.dumps(w));nodes={n['name']:n for n in w['nodes']}
        http=[n for n in w['nodes'] if n['type'].endswith('.httpRequest')];self.assertEqual(len(http),3)
        for n in http:
            self.assertIn("$('Local sandbox configuration').first().json.guardBaseUrl",n['parameters']['url']);self.assertEqual(n['parameters']['genericAuthType'],'httpHeaderAuth');self.assertNotIn('credentials',n)
        self.assertIn('approver_email',nodes['Gmail - secure approval link']['parameters']['sendTo']);self.assertEqual(nodes['Gmail - secure approval link']['parameters']['operation'],'send')
        for s,p in w['connections'].items():
            self.assertIn(s,nodes)
            for branches in p.values():
                for branch in branches:
                    for e in branch:self.assertIn(e['node'],nodes)
        self.assertIn("proposalSource:'test'",nodes['Local sandbox configuration']['parameters']['jsCode'])
    def test_configuration_saved_encrypted_via_dpapi_boundary(self):
        # Mock boundary for portability. Real Windows CryptProtectData not exercised on Linux.
        with patch.object(win,'data_dir',return_value=pathlib.Path(self.tmp.name)),patch.object(win,'protect',side_effect=lambda b,decrypt=False:bytes(x^128 for x in b)):
            win.save(self.config);raw=(pathlib.Path(self.tmp.name)/'config.dpapi').read_bytes();self.assertNotIn(self.config['TRADING_GUARD_API_KEY'].encode(),raw);self.assertEqual(win.load(),self.config)
    @unittest.skipUnless(os.name=='nt','Requires real Windows DPAPI')
    def test_real_windows_dpapi_roundtrip(self):
        value=b'synthetic-only-dpapi-regression'
        encrypted=win.protect(value);self.assertNotIn(value,encrypted);self.assertEqual(win.protect(encrypted,True),value)
    def test_checks_reject_mismatched_runtime(self):
        def call(base,path,*a):return {**readiness(self.config),'configuration_fingerprint':base}
        with self.assertRaisesRegex(win.SetupError,'configuratii diferite'):win.checks(self.config,call)
class WindowsServicesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.c={'TRADING_GUARD_DB':str(pathlib.Path(cls.tmp.name)/'db'),'TRADING_GUARD_API_KEY':secrets.token_hex(32),'TRADING_APPROVAL_RECEIPT_KEY':secrets.token_hex(32),'TRADING_APPROVER_EMAIL':'owner@example.invalid','TRADING_GOOGLE_CLIENT_ID':'test-client','TRADING_GOOGLE_CLIENT_SECRET':'test-only-not-real','TRADING_GOOGLE_SUB':'123456789012345678901'}
        cls.processes=[]
        for script in ('server.py','oidc_server.py'):
            p=subprocess.Popen([sys.executable,script],cwd=pathlib.Path(__file__).parent,env={**os.environ,**cls.c},stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);cls.processes.append(p)
        for _ in range(60):
            if any(p.poll() is not None for p in cls.processes):raise RuntimeError('Dedicated test ports unavailable')
            try:
                win.request('http://127.0.0.1:8765','/v1/health',cls.c['TRADING_GUARD_API_KEY']);win.request('http://localhost:8766','/internal/readiness',cls.c['TRADING_GUARD_API_KEY']);return
            except OSError:time.sleep(.05)
        raise RuntimeError('Services startup timeout')
    @classmethod
    def tearDownClass(cls):
        for p in cls.processes:p.terminate();p.communicate(timeout=5)
        cls.tmp.cleanup()
    def test_end_to_end_guard_check_uses_three_node_contracts(self):
        r=win.checks(self.c);self.assertEqual(r['three_guard_node_contracts'],'OK');self.assertFalse(r['order_sent']);self.assertEqual(r['google_real_login'],'NOT_TESTED_BY_CHECK')
    def test_oidc_readiness_requires_key(self):
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError) as e:win.request('http://localhost:8766','/internal/readiness','incorrect-test-key')
        self.assertEqual(e.exception.code,401)
    def test_guard_markets_supplies_recipient(self):self.assertEqual(win.request('http://127.0.0.1:8765','/v1/markets',self.c['TRADING_GUARD_API_KEY'])['approver_email'],self.c['TRADING_APPROVER_EMAIL'])
    def test_check_detects_stale_saved_configuration(self):
        with self.assertRaises(win.SetupError):win.checks({**self.c,'TRADING_GOOGLE_SUB':'different'})
if __name__=='__main__':unittest.main(verbosity=2)
