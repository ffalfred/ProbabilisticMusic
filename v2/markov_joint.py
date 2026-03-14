from collections import deque
import numpy as np
from v2.emission import sample_output, OUTPUT_PARAMS


class JointMarkov:
    """
    Higher-order Markov chain that conditions on previous score markings AND
    previously rendered output vectors.

    History tracks (marking, output_dict) pairs with history_decay weighting:
    older entries have exponentially less influence on the emission mean.
    """

    def __init__(self, order: int, transition_table: dict,
                 cold_start_marking: str, cold_start_outputs: dict,
                 covariance: str, history_decay: float,
                 rng: np.random.Generator):
        self.order            = order
        self.transition_table = transition_table
        self.covariance       = covariance
        self.history_decay    = history_decay
        self.rng              = rng
        self._cold_outputs    = cold_start_outputs

        self.history = deque(
            [(cold_start_marking, dict(cold_start_outputs))] * order,
            maxlen=order
        )

        self._sfz_recovery = None

    def step(self, marking: str, context: dict) -> dict:
        """
        Advance one step. Returns sampled o(t) dict.

        In joint mode the base emission is shifted by a decay-weighted mean
        of previous outputs, making past performance influence the present.
        """
        transition_key = self._build_key(marking)
        output = sample_output(transition_key, self.transition_table,
                               context, self.covariance, self.rng)

        # Blend in history-weighted mean of previous outputs
        history_list = list(self.history)  # oldest to newest
        total_weight = 0.0
        weighted_out = {p: 0.0 for p in OUTPUT_PARAMS}

        for age, (_, prev_out) in enumerate(reversed(history_list)):
            if prev_out is None:
                continue
            w = self.history_decay ** (age + 1)
            for p in OUTPUT_PARAMS:
                weighted_out[p] += w * prev_out.get(p, 0.0)
            total_weight += w

        if total_weight > 0:
            blend = 0.15   # how strongly past outputs pull the current one
            for p in OUTPUT_PARAMS:
                output[p] += blend * weighted_out[p] / total_weight

        # Apply sfz recovery bias if active
        if self._sfz_recovery is not None:
            remaining, gain_bias, bright_bias, total_length = self._sfz_recovery
            fade = remaining / total_length
            output['gain_db']    += gain_bias  * fade
            output['brightness'] += bright_bias * fade
            remaining -= 1
            if remaining <= 0:
                self._sfz_recovery = None
            else:
                self._sfz_recovery = (remaining, gain_bias, bright_bias, total_length)

        # Arm sfz recovery
        entry = self.transition_table.get(
            self._resolve_entry_key(transition_key), {}
        )
        if entry.get('type') == 'shadow' and 'sfz_recovery' in entry:
            rec = entry['sfz_recovery']
            length = rec.get('length', 2)
            self._sfz_recovery = (
                length,
                rec.get('gain_bias', 0.0),
                rec.get('brightness_bias', 0.0),
                length,
            )

        self.history.append((marking, dict(output)))
        return output

    def reset_history(self, cold_start_marking: str):
        self.history = deque(
            [(cold_start_marking, dict(self._cold_outputs))] * self.order,
            maxlen=self.order
        )
        self._sfz_recovery = None

    # ------------------------------------------------------------------

    def _build_key(self, curr_marking: str) -> str:
        prev = list(self.history)[-1][0] if self.history else 'mf'
        return f"{prev}_to_{curr_marking}"

    def _resolve_entry_key(self, transition_key: str) -> str:
        from v2.emission import _resolve_key
        return _resolve_key(transition_key, self.transition_table)
