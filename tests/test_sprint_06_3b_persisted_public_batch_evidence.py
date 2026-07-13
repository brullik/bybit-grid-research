import hashlib
import json
import zipfile
import pytest

from bybit_grid.data.public_batch.evidence import CANONICAL_MEMBERS, GUARDRAILS, build_manifest, canonical_json_bytes, validate_review_pack
from bybit_grid.data.public_batch.models import InclusiveMinuteWindow, PublicBatchError
from bybit_grid.data.public_batch.pagination import plan_1m_windows, fetch_funding_history_chunked
from bybit_grid.data.public_batch.recording import RecordedPublicResponse, strict_json_loads


def test_import_and_strict_json_boundaries():
    assert strict_json_loads('{"a":1}') == {"a": 1}
    for bad in ('{"a":1,"a":2}', '{"a":1.2}', '{"a":NaN}'):
        with pytest.raises(PublicBatchError):
            strict_json_loads(bad)
    body = '{"retCode":0,"result":{}}'
    rec = RecordedPublicResponse(1, '/v5/market/time', {}, 200, 'application/json', body, hashlib.sha256(body.encode()).hexdigest(), json.loads(body))
    assert rec.parsed_payload['retCode'] == 0


def test_limit_validation_and_1001_plans():
    w = InclusiveMinuteWindow(0, 1000 * 60000)
    assert [x.row_count for x in plan_1m_windows(w.start_open_time_ms, w.end_open_time_ms, 1000)] == [1000, 1]
    assert [x.row_count for x in plan_1m_windows(w.start_open_time_ms, w.end_open_time_ms, 251)] == [251, 251, 251, 248]
    for bad in (True, 1.0, '1000', 0, 1001):
        with pytest.raises(PublicBatchError):
            plan_1m_windows(0, 60000, bad)


def test_funding_chunk_truncation_risk():
    class C:
        def public_get(self, endpoint, params):
            rows = [{'symbol': 'BTCUSDT', 'fundingRateTimestamp': str(i * 60000), 'fundingRate': '0.01'} for i in range(params['limit'])]
            return {'retCode': 0, 'result': {'list': rows}}
    with pytest.raises(PublicBatchError):
        fetch_funding_history_chunked(C(), 'BTCUSDT', 0, 10 * 60000, 1, target_records_per_window=5, page_limit=5)


def test_review_pack_contract(tmp_path):
    member_bytes = {}
    for n in CANONICAL_MEMBERS:
        if n.endswith('.md'):
            member_bytes[n] = b'# report\n'
        elif n.endswith('.jsonl'):
            member_bytes[n] = canonical_json_bytes({'plan_id': 'trade_primary_1000'}) + b'\n'
        elif n == 'capture_summary.json':
            member_bytes[n] = canonical_json_bytes({'run_id': 'r', 'symbol': 'BTCUSDT', **GUARDRAILS})
        elif n != 'review_pack_manifest.json':
            member_bytes[n] = canonical_json_bytes({'run_id': 'r'})
    manifest = canonical_json_bytes(build_manifest({k: v for k, v in member_bytes.items() if k != 'review_pack_manifest.json'}, run_id='r'))
    z = tmp_path / 'pack.zip'
    with zipfile.ZipFile(z, 'w') as zf:
        for n in CANONICAL_MEMBERS:
            zf.writestr(n, manifest if n == 'review_pack_manifest.json' else member_bytes[n])
    with pytest.raises(PublicBatchError):
        validate_review_pack(z, 'r')
    with zipfile.ZipFile(z, 'a') as zf:
        zf.writestr('extra.json', '{}')
    with pytest.raises(PublicBatchError):
        validate_review_pack(z, 'r')
