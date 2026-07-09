from __future__ import annotations

import builtins
import math

int64 = int
float64 = float

class ndarray(list):
    @property
    def size(self):
        return len(self)
    def astype(self, dtype):
        return ndarray(dtype(x) for x in self)
    def __array_op(self, other, op):
        if isinstance(other, (list, ndarray)):
            return ndarray(op(a, b) for a, b in zip(self, other, strict=False))
        return ndarray(op(a, other) for a in self)
    def __lt__(self, other): return self.__array_op(other, lambda a,b: a < b)
    def __le__(self, other): return self.__array_op(other, lambda a,b: a <= b)
    def __gt__(self, other): return self.__array_op(other, lambda a,b: a > b)
    def __ge__(self, other): return self.__array_op(other, lambda a,b: a >= b)
    def __eq__(self, other): return self.__array_op(other, lambda a,b: a == b)
    def __ne__(self, other): return self.__array_op(other, lambda a,b: a != b)
    def __or__(self, other): return ndarray(bool(a) or bool(b) for a,b in zip(self, other, strict=False))
    def __and__(self, other): return ndarray(bool(a) and bool(b) for a,b in zip(self, other, strict=False))
    def __sub__(self, other): return self.__array_op(other, lambda a,b: a - b)
    def __rsub__(self, other): return ndarray(other - a for a in self)
    def __add__(self, other): return self.__array_op(other, lambda a,b: a + b)
    def __mul__(self, other): return self.__array_op(other, lambda a,b: a * b)
    def __truediv__(self, other): return self.__array_op(other, lambda a,b: a / b)


def array(values=(), dtype=None):
    return ndarray((dtype(x) if dtype else x) for x in values)

def asarray(values, dtype=None):
    return array(values, dtype)

def where(mask):
    return (ndarray(i for i, v in enumerate(mask) if v),)

def sum(values):
    return builtins.sum(values)

def max(values):
    return builtins.max(values)

def min(values):
    return builtins.min(values)

def abs(values):
    return ndarray(builtins.abs(x) for x in values)

def diff(values):
    return ndarray(values[i + 1] - values[i] for i in range(len(values) - 1))

def mean(values):
    return builtins.sum(values) / len(values) if values else math.nan


# Minimal test-environment compatibility: make Polars Series.to_numpy return this list array
try:
    import polars as _pl
    def _series_to_numpy(self, *args, **kwargs):
        return array(self.to_list())
    _pl.Series.to_numpy = _series_to_numpy
except Exception:
    pass

def ones(n, dtype=None):
    return array([1.0] * n, dtype)

def linspace(start, stop, num, dtype=None):
    if num == 1:
        return array([start], dtype)
    step = (stop - start) / (num - 1)
    return array([start + i * step for i in range(num)], dtype)

def geomspace(start, stop, num, dtype=None):
    if num == 1:
        return array([start], dtype)
    ratio = (stop / start) ** (1 / (num - 1))
    return array([start * (ratio ** i) for i in range(num)], dtype)

ndarray.tolist = lambda self: list(self)

def _getitem(self, key):
    out = list.__getitem__(self, key)
    return ndarray(out) if isinstance(key, slice) else out
ndarray.__getitem__ = _getitem

def minimum(a, b):
    if isinstance(b, (list, ndarray)):
        return ndarray(builtins.min(x, y) for x, y in zip(a, b, strict=False))
    return ndarray(builtins.min(x, b) for x in a)

def maximum(a, b):
    if isinstance(b, (list, ndarray)):
        return ndarray(builtins.max(x, y) for x, y in zip(a, b, strict=False))
    return ndarray(builtins.max(x, b) for x in a)

def all(values):
    return bool(values) if isinstance(values, bool) else builtins.all(values)

def _astype(self, dtype, copy=True):
    return ndarray(dtype(x) for x in self)
ndarray.astype = _astype
