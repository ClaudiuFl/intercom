"""Source-verified contract helpers. Pure preview only; no signing/POST/transport."""
import re
from guard import Denied
SOURCE_COMMIT='90dcd473f89576cbb588f12e08802229b060a8b9'
ASSETS={'TNK/USDC':('TNK',18),'RESET/USDC':('RESET',8)}
def base_units(pair,amount):
    if pair not in ASSETS or not isinstance(amount,str) or not re.fullmatch(r'(0|[1-9][0-9]*)(\.[0-9]+)?',amount):raise Denied('amount_format')
    d=ASSETS[pair][1];whole,_,fraction=amount.partition('.')
    if len(whole)>31 or len(fraction)>d:raise Denied('amount_precision')
    n=int(whole)*10**d+int(fraction.ljust(d,'0'))
    if n<=0:raise Denied('amount_positive')
    return n
def price_units(price):
    if not isinstance(price,str) or not re.fullmatch(r'(0|[1-9][0-9]{0,30})(\.[0-9]{1,12})?',price):raise Denied('price_format')
    whole,_,frac=price.partition('.');n=int(whole)*10**12+int(frac.ljust(12,'0'))
    if n<=0:raise Denied('price_positive')
    return n
def quote_units(pair,n,price):
    if pair not in ASSETS or type(n) is not int or n<=0:raise Denied('base_units')
    q=n*price_units(price)*10**6//10**(ASSETS[pair][1]+12)
    if q<=0:raise Denied('trade_too_small')
    return q
def take_preview(*,pair,side,amount,offer,platform_bps,trade_bps):
    """Fee inputs must come from the admitted signed registry in a future executor.
    Does not establish wallet funds, registry authentication, offer freshness or finality.
    """
    if side not in ('buy','sell') or offer.get('pair')!=pair or offer.get('side')!=('sell' if side=='buy' else 'buy'):raise Denied('offer_side')
    if not re.fullmatch('[0-9a-f]{64}',offer.get('offerId','')):raise Denied('offer_id')
    n=base_units(pair,amount)
    left=offer.get('baseAmount')
    if not isinstance(left,str) or not re.fullmatch('[1-9][0-9]*',left) or n>int(left):raise Denied('insufficient_offer')
    for b,limit in ((platform_bps,500),(trade_bps,1000)):
        if type(b) is not int or not 0<=b<=limit:raise Denied('fee_bps')
    q=quote_units(pair,n,offer['price']);fee=q*platform_bps//10000+q*trade_bps//10000
    if q+fee>10_000_000:raise Denied('max_10_usdc_with_quote_fees')
    return {'verifiedSourceCommit':SOURCE_COMMIT,'mode':'PREVIEW_ONLY','live_enabled':False,'method':'POST','path':'/take','body':{'offerId':offer['offerId'],'price':offer['price'],'baseAmount':str(n)},'quoteAmount':str(q),'buyerTotalUSDCUnits':str(q+fee),'nativeChainFeesIncluded':False,'order_sent':False,'warning':'DO NOT SEND: authenticated registry, funds, final revalidation, durable dispatch/reconciliation and LIVE authorization still required.'}
