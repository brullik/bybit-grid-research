import hmac, hashlib
from bybit_grid.bybit.signing import canonical_query, build_v5_sign_payload, sign_v5

def test_signing_payload_and_hmac():
    qs=canonical_query({'b':2,'a':'x'})
    assert qs == 'a=x&b=2'
    payload=build_v5_sign_payload(123,'key',5000,qs)
    assert payload == '123key5000a=x&b=2'
    assert sign_v5('secret', payload) == hmac.new(b'secret', payload.encode(), hashlib.sha256).hexdigest()
