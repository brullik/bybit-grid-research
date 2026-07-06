from bybit_grid.data.instruments import download_instruments
from bybit_grid.config import Settings

class FakeClient:
    def __init__(self):
        self.calls=0; self.settings=Settings(data_dir='data')
    def public_get(self, endpoint, params):
        self.calls += 1
        if self.calls == 1:
            return {'result': {'list': [{'symbol':'A','status':'Trading'}], 'nextPageCursor':'n'}}
        return {'result': {'list': [{'symbol':'B','status':'Trading'}], 'nextPageCursor':''}}

def test_instruments_pagination(tmp_path):
    c=FakeClient(); c.settings.data_dir=tmp_path
    df=download_instruments(c)
    assert c.calls == 2
    assert df['symbol'].to_list() == ['A','B']
    assert (tmp_path/'metadata'/'instruments_linear.parquet').exists()
