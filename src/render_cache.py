"""Reuse processed audio between renders (the editor's Mix, Concerto…).

A piece of work — one event's clip, the processed source — is identified by
a key built from everything it depends on (its settings, the audio it starts
from). It runs with its own random state; if it never drew a random number,
its result doesn't depend on the seed and is stored under the key alone, so
the next render reuses it even with a new seed (the default: every Mix is a
new performance). If it did draw, the result is stored under key + seed, so
it is reused only when the seed is the same (a fixed seed).

Results are kept in memory, least recently used dropped first, up to
MAX_BYTES. Cached arrays are read-only: callers must not modify them.
"""
import hashlib
import json
import threading
from collections import OrderedDict

import numpy as np

from src import rand

MAX_BYTES = 768 * 1024 * 1024

_lock = threading.Lock()
_store = OrderedDict()          # key -> result
_size = {'bytes': 0}
stats = {'hits': 0, 'misses': 0}


def array_digest(a: np.ndarray) -> str:
    a = np.ascontiguousarray(a)
    h = hashlib.blake2b(digest_size=16)
    h.update(str((a.dtype.str, a.shape)).encode())
    h.update(a.data)
    return h.hexdigest()


def key(*parts) -> str:
    """A key from JSON-able parts (dicts, lists, numbers, strings)."""
    s = json.dumps(parts, sort_keys=True, default=str, separators=(',', ':'))
    return hashlib.blake2b(s.encode(), digest_size=16).hexdigest()


def _nbytes(v) -> int:
    if isinstance(v, np.ndarray):
        return v.nbytes
    if isinstance(v, (tuple, list)):
        return sum(_nbytes(x) for x in v)
    return 64


def _freeze(v):
    if isinstance(v, np.ndarray):
        v.flags.writeable = False
    elif isinstance(v, (tuple, list)):
        for x in v:
            _freeze(x)
    return v


def _get(k):
    with _lock:
        if k in _store:
            _store.move_to_end(k)
            return True, _store[k]
    return False, None


def _put(k, v):
    n = _nbytes(v)
    if n > MAX_BYTES // 4:
        return                                  # too big to be worth keeping
    with _lock:
        if k in _store:
            return
        _store[k] = v
        _size['bytes'] += n
        while _size['bytes'] > MAX_BYTES and _store:
            _, old = _store.popitem(last=False)
            _size['bytes'] -= _nbytes(old)


def run(k: str, seed: int, fn):
    """fn() with its own random state seeded by `seed`, cached under k
    (or k + seed if it drew random numbers). Returns fn's result."""
    k_seed = key(k, int(seed))
    for kk in (k, k_seed):
        found, v = _get(kk)
        if found:
            stats['hits'] += 1
            return v
    stats['misses'] += 1
    state = np.random.RandomState(int(seed))
    before = state.get_state()
    with rand.use(state):
        v = fn()
    _put(k_seed if rand.drew(state, before) else k, _freeze(v))
    return v


def clear():
    with _lock:
        _store.clear()
        _size['bytes'] = 0
