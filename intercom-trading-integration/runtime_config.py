"""Non-secret readiness fingerprint: detects services started with different configuration."""
import os,json,hmac,hashlib
from pathlib import Path
def readiness(config=None):
    e=os.environ if config is None else config
    key=e.get('TRADING_GUARD_API_KEY','')
    fields={k:e.get(k,'') for k in ('TRADING_APPROVER_EMAIL','TRADING_GOOGLE_SUB','TRADING_GOOGLE_CLIENT_ID')}
    fields['db']=os.path.normcase(str(Path(e.get('TRADING_GUARD_DB','guard.sqlite3')).resolve()))
    fields['receiptHash']=hashlib.sha256(e.get('TRADING_APPROVAL_RECEIPT_KEY','').encode()).hexdigest()
    fields['clientSecretHash']=hashlib.sha256(e.get('TRADING_GOOGLE_CLIENT_SECRET','').encode()).hexdigest()
    return {'mode':'SANDBOX','live_enabled':False,'configuration_fingerprint':hmac.new(key.encode(),json.dumps(fields,sort_keys=True).encode(),hashlib.sha256).hexdigest(),'google_client_configured':bool(fields['TRADING_GOOGLE_CLIENT_ID'] and e.get('TRADING_GOOGLE_CLIENT_SECRET')),'google_subject_pinned':bool(fields['TRADING_GOOGLE_SUB']),'approver_email_configured':bool(fields['TRADING_APPROVER_EMAIL'])}
