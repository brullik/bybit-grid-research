from __future__ import annotations
import argparse
import json
from bybit_grid.data.market_store.audit import audit_market_store
from bybit_grid.data.market_store.canonical import plain


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--store-root', required=True)
    ns = p.parse_args(argv)
    a = audit_market_store(ns.store_root)
    print(json.dumps(plain(a), sort_keys=True, separators=(',', ':')))
    return 0 if a.ok else 2

if __name__ == '__main__':
    raise SystemExit(main())
