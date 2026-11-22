"""The random source used while rendering.

Effects and plugins draw random numbers through rng() instead of numpy's
global functions. By default rng() *is* numpy's global source (so seeding
with np.random.seed works as always); inside `with use(state):` it is that
state instead, for the current thread only. mix_events gives every event its
own state, seeded in order from the render's seed, so events can be
processed in parallel — and cached — without changing each other's random
choices.
"""
import threading

import numpy as np

_local = threading.local()


def rng() -> np.random.RandomState:
    """The current thread's random state (numpy's global one by default)."""
    st = getattr(_local, 'state', None)
    return st if st is not None else np.random.mtrand._rand


class use:
    """`with use(np.random.RandomState(seed)):` — draws in this thread come
    from that state until the block ends."""

    def __init__(self, state: np.random.RandomState):
        self.state = state

    def __enter__(self):
        self.prev = getattr(_local, 'state', None)
        _local.state = self.state
        return self.state

    def __exit__(self, *exc):
        _local.state = self.prev
        return False


def drew(state: np.random.RandomState, before) -> bool:
    """Whether `state` was drawn from since get_state() returned `before`."""
    after = state.get_state()
    return not (after[2] == before[2] and after[3] == before[3]
                and np.array_equal(after[1], before[1]))
