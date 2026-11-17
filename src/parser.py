import yaml
import numpy as np
from src.envelope import DYNAMIC_LEVELS


def _resolve(val):
    """
    Resolve a parameter value. Three forms are accepted:

      speed: 1.0                          fixed value — returned as-is
      speed: [0.5, 2.0]                   uniform random in range [min, max]
      speed: {distribution: gaussian,     explicit named distribution
               mean: 0.75, std: 0.1}
    """
    # shorthand: [min, max] → uniform range
    if isinstance(val, list) and len(val) == 2:
        return float(np.random.uniform(val[0], val[1]))

    if not isinstance(val, dict) or 'distribution' not in val:
        return val

    dist = val['distribution']
    if dist == 'gaussian':
        return float(np.random.normal(val['mean'], val['std']))
    if dist in ('uniform', 'random'):
        return float(np.random.uniform(val['low'], val['high']))
    if dist == 'bernoulli':
        return bool(np.random.random() < val['p'])
    if dist == 'discrete':
        values  = val['values']
        weights = val.get('weights')
        if weights:
            weights = np.array(weights, dtype=float)
            weights /= weights.sum()
        return values[int(np.random.choice(len(values), p=weights))]
    raise ValueError(f"unknown distribution: '{dist}'")


def seed_everything(config: dict) -> int:
    """Seed every random source used by a render and return the seed.

    The seed comes from config['v2']['seed'], then config['seed']; if neither
    is set a fresh one is drawn. It is written back to config['v2']['seed'] so
    the interpreter uses the same value, and the caller can report it.
    """
    import random
    v2 = config.get('v2')
    if not isinstance(v2, dict):
        v2 = config['v2'] = {}
    seed = v2.get('seed', config.get('seed'))
    if seed is None:
        seed = int(np.random.SeedSequence().entropy & 0x7FFFFFFF)
    seed = int(seed)
    np.random.seed(seed)
    random.seed(seed)
    v2['seed'] = seed
    return seed


def resolve_score(score: dict) -> dict:
    """Resolve probabilistic event parameters in place and normalise markings.

    After this, event values are concrete. Call it once per render, after
    seed_everything(), so the same seed draws the same values.
    """
    # resolve probabilistic parameters in events (everything except t and sample)
    _skip_event = {'t', 'sample', 'fx', 'speeds'}
    for event in score.get('events', []):
        for key in list(event.keys()):
            if key not in _skip_event:
                event[key] = _resolve(event[key])
        if 'speeds' in event:
            event['speeds'] = [_resolve(s) for s in event['speeds']]
        for fx in event.get('fx', []):
            for key in list(fx.keys()):
                if key != 'type':
                    fx[key] = _resolve(fx[key])

    # Normalize dynamics: YAML uses 'marking', backend uses 'mark'
    for d in score.get('dynamics', []):
        if 'marking' in d and 'mark' not in d:
            d['mark'] = d.pop('marking')
    return score


def load_score(path: str) -> dict:
    with open(path, 'r') as f:
        score = yaml.safe_load(f)

    assert 'samples' in score, "score must define samples"
    assert 'events'  in score, "score must define events"

    resolve_score(score)

    # validate dynamics markings
    valid_range_marks = {'crescendo', 'decrescendo'}
    for d in score.get('dynamics', []):
        mark = d.get('mark')
        if 't' in d:
            assert mark in DYNAMIC_LEVELS, \
                f"unknown dynamic level '{mark}', use: {list(DYNAMIC_LEVELS)}"
        elif 'from' in d:
            assert mark in valid_range_marks, \
                f"range dynamic must be 'crescendo' or 'decrescendo', got '{mark}'"

    duration = score.get('duration')
    if duration:
        for name, spec in score['samples'].items():
            assert spec['to'] <= duration, \
                f"sample '{name}' ends at {spec['to']}s, exceeds duration {duration}s"
        for event in score['events']:
            assert event['t'] <= duration, \
                f"event at t={event['t']}s exceeds duration {duration}s"

    return score
