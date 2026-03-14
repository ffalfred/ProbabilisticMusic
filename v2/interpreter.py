"""
V2 Expressive Interpretation Engine — entry point.

interpret(score, config) -> list[dict]
  Takes a parsed score dict and V2 config dict.
  Returns an enriched event list ready for V1 rendering.
"""

import os
import copy
import yaml
import numpy as np

from v2.context         import infer_phrase_boundaries, compute_context
from v2.emission        import sample_gradient
from v2.markov_symbolic import SymbolicMarkov
from v2.markov_joint    import JointMarkov

_TABLE_PATH = os.path.join(os.path.dirname(__file__), 'transition_table.yaml')

# Markings that use wildcard 'any_to_X' keys in the table
_WILDCARD_MARKINGS = {'sfz', 'fp', 'subito_p', 'subito_f'}
# Gradual markings — handled separately with per-second rates
_GRADUAL_MARKINGS  = {'cresc', 'decresc', 'crescendo', 'decrescendo'}


def interpret(score: dict, config: dict) -> list:
    """
    Enrich score events with V2 expressive parameters.

    Modifies copies of events; original score is unchanged.
    Returns sorted list of enriched event dicts.
    """
    with open(_TABLE_PATH) as f:
        table_root = yaml.safe_load(f)
    table = table_root['transitions']

    dynamics      = score.get('dynamics', [])
    events        = sorted(copy.deepcopy(score.get('events', [])), key=lambda e: e['t'])
    total_dur     = _total_duration(events, score)

    if not events:
        return events

    # --- Config extraction ---
    mode          = config.get('markov_mode',   'symbolic')
    order         = int(config.get('markov_order', 2))
    covariance    = config.get('covariance',    'diagonal')
    phrase_mode   = config.get('phrase_boundary', 'reset')
    history_decay = float(config.get('history_decay', 0.7))
    seed          = config.get('seed', None)

    cold_marking  = config.get('cold_start_marking', 'mf')
    cold_outputs  = config.get('cold_start_outputs', {
        'gain_db': -12.0, 'brightness': 0.5,
        'timing_offset_ms': 0.0, 'attack_shape': 0.5, 'reverb_wet': 0.3
    })

    # --- RNG ---
    rng = np.random.default_rng(seed)

    # --- Phrase boundaries ---
    phrase_boundaries = infer_phrase_boundaries(events)

    # --- Markov chain ---
    if mode == 'joint':
        chain = JointMarkov(
            order=order, transition_table=table,
            cold_start_marking=cold_marking,
            cold_start_outputs=cold_outputs,
            covariance=covariance,
            history_decay=history_decay,
            rng=rng
        )
    else:
        chain = SymbolicMarkov(
            order=order, transition_table=table,
            cold_start_marking=cold_marking,
            cold_start_outputs=cold_outputs,
            covariance=covariance,
            rng=rng
        )

    # --- Pre-compute gradual (cresc/decresc) rates once per span ---
    gradient_rates = _compute_gradient_rates(dynamics, table, rng)

    # --- Walk events ---
    for event in events:
        t = event['t']

        # Phrase boundary reset
        if phrase_mode == 'reset' and t in phrase_boundaries:
            chain.reset_history(cold_marking)

        # Find active marking at time t
        marking, marking_t, duration = _active_marking(dynamics, t)

        ctx = compute_context(events, score, t, total_dur, phrase_boundaries)

        if marking in _GRADUAL_MARKINGS:
            output = _apply_gradient(event, marking, marking_t, duration,
                                     gradient_rates, t, ctx, chain, table,
                                     covariance, rng)
        else:
            output = chain.step(marking, ctx)

        _apply_output(event, output)

    return events


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _total_duration(events: list, score: dict) -> float:
    if not events:
        return 1.0
    last_t = max(e['t'] for e in events)
    return last_t + 5.0   # rough estimate beyond last event


def _active_marking(dynamics: list, t: float) -> tuple:
    """
    Return (marking, start_time, duration_or_None) for the marking active at t.

    Priority:
      1. Any gradual range that covers t (cresc/decresc 'from'/'to')
      2. Most recent point marking at or before t
      3. Default: 'mf'
    """
    # Check gradual spans first
    for d in dynamics:
        raw = d.get('marking', d.get('mark', ''))
        _norm = _normalise_marking(raw)
        if _norm in _GRADUAL_MARKINGS:
            start = d.get('t', d.get('from', 0))
            dur   = d.get('duration', d.get('to', start) - start)
            end   = start + dur
            if start <= t <= end:
                return _norm, start, dur

    # Most recent point marking
    best_t   = -1.0
    best_mark = 'mf'
    for d in dynamics:
        raw = d.get('marking', d.get('mark', ''))
        _norm = _normalise_marking(raw)
        if _norm in _GRADUAL_MARKINGS:
            continue
        dt = d.get('t')
        if dt is None:
            continue
        if dt <= t and dt > best_t:
            best_t    = dt
            best_mark = _norm

    return best_mark, best_t, None


def _normalise_marking(raw: str) -> str:
    """Map score alias names to canonical marking names."""
    mapping = {
        'crescendo':  'cresc',
        'decrescendo': 'decresc',
        'diminuendo':  'decresc',
    }
    return mapping.get(raw, raw)


def _compute_gradient_rates(dynamics: list, table: dict,
                             rng: np.random.Generator) -> dict:
    """
    Pre-sample per-second rates for every cresc/decresc span.
    Returns dict keyed by (start_time, marking).
    """
    rates = {}
    for d in dynamics:
        raw   = d.get('marking', d.get('mark', ''))
        norm  = _normalise_marking(raw)
        if norm not in _GRADUAL_MARKINGS:
            continue
        start = d.get('t', d.get('from', 0))
        key   = (start, norm)
        if key not in rates:
            rates[key] = sample_gradient(norm, table, rng)
    return rates


def _apply_gradient(event: dict, marking: str, marking_t: float,
                    duration, gradient_rates: dict,
                    t: float, ctx: dict, chain, table: dict,
                    covariance: str, rng: np.random.Generator) -> dict:
    """
    For events inside a cresc/decresc span, interpolate gain_db linearly
    across the span duration using the pre-sampled rate.
    Other parameters are sampled normally from the chain.
    """
    # Get base output from chain (for parameters other than gain_db/brightness)
    base_output = chain.step(marking, ctx)

    rate_key = (marking_t, marking)
    rates    = gradient_rates.get(rate_key, {'gain_db_per_sec': 0.0,
                                              'brightness_per_sec': 0.0})

    elapsed = t - marking_t
    base_output['gain_db']    += rates['gain_db_per_sec']    * elapsed
    base_output['brightness'] += rates['brightness_per_sec'] * elapsed

    return base_output


def _apply_output(event: dict, output: dict):
    """
    Apply sampled output vector to an event dict in-place.

    Mappings:
      gain_db           → added to event['gain_db']
      timing_offset_ms  → added to event['t'] (converted to seconds)
      reverb_wet        → injects/scales reverb FX
      attack_shape      → passed via event['_attack_shape'] for mixer
      brightness        → injects EQ boost/cut at 5kHz
    """
    # gain
    current_gain = event.get('gain_db', -6.0)
    event['gain_db'] = current_gain + output['gain_db']

    # timing
    offset_s = output['timing_offset_ms'] / 1000.0
    event['t'] = max(0.0, event['t'] + offset_s)

    # attack_shape: store for mixer (apply_fade multiplier)
    event['_attack_shape'] = output['attack_shape']

    # reverb wet — inject or scale existing reverb FX
    reverb_wet = output['reverb_wet']
    if reverb_wet != 0.0:
        _inject_reverb(event, reverb_wet)

    # brightness — inject EQ at 5kHz
    brightness = output['brightness']
    if abs(brightness) > 0.01:
        _inject_brightness(event, brightness)


def _inject_reverb(event: dict, reverb_wet: float):
    """
    Add or scale reverb FX entry on the event.
    reverb_wet is a signed float; positive = wetter, negative = drier.
    """
    fx_list = event.setdefault('fx', [])
    for fx in fx_list:
        if fx.get('type') == 'reverb':
            current = fx.get('reverberance', 50)
            fx['reverberance'] = int(np.clip(current + reverb_wet * 100, 0, 100))
            return
    # No reverb yet — only add if wet is meaningfully positive
    if reverb_wet > 0.05:
        reverberance = int(np.clip(30 + reverb_wet * 100, 0, 100))
        fx_list.append({'type': 'reverb', 'reverberance': reverberance})


def _inject_brightness(event: dict, brightness: float):
    """
    Add or update an EQ entry at 5kHz for brightness control.
    brightness is signed: positive = boost, negative = cut (in normalised units).
    Converts to dB: 1 unit ≈ 6 dB.
    """
    gain_db = float(np.clip(brightness * 6.0, -12.0, 12.0))
    fx_list = event.setdefault('fx', [])
    for fx in fx_list:
        if fx.get('type') == 'eq' and fx.get('_brightness_tag'):
            fx['gain_db'] = gain_db
            return
    fx_list.append({'type': 'eq', 'freq_hz': 5000, 'gain_db': gain_db,
                    'q': 0.7, '_brightness_tag': True})
