from collections import deque
import numpy as np
from v2.emission import sample_output, OUTPUT_PARAMS


class SymbolicMarkov:
    """
    Higher-order Markov chain that conditions only on previous score markings.
    History tracks (marking, None) pairs — outputs are not fed back into context.
    """

    def __init__(self, order: int, transition_table: dict,
                 cold_start_marking: str, cold_start_outputs: dict,
                 covariance: str, rng: np.random.Generator):
        self.order            = order
        self.transition_table = transition_table
        self.covariance       = covariance
        self.rng              = rng

        # History: deque of (marking, output_or_None), oldest first
        self.history = deque(
            [(cold_start_marking, None)] * order,
            maxlen=order
        )

        # sfz recovery state: (events_remaining, gain_bias, brightness_bias)
        self._sfz_recovery = None

    def step(self, marking: str, context: dict) -> dict:
        """
        Advance one step. Returns sampled o(t) dict.
        """
        transition_key = self._build_key(marking)
        output = sample_output(transition_key, self.transition_table,
                               context, self.covariance, self.rng)

        # Apply sfz recovery bias if active
        if self._sfz_recovery is not None:
            remaining, gain_bias, bright_bias, total_length = self._sfz_recovery
            # Linear fade: full bias on step 1, half on step 2, etc.
            fade = remaining / total_length
            output['gain_db']    += gain_bias  * fade
            output['brightness'] += bright_bias * fade
            remaining -= 1
            if remaining <= 0:
                self._sfz_recovery = None
            else:
                self._sfz_recovery = (remaining, gain_bias, bright_bias, total_length)

        # Arm sfz recovery for next events
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

        self.history.append((marking, None))
        return output

    def reset_history(self, cold_start_marking: str):
        """Wipe history at a phrase boundary and refill with cold start."""
        self.history = deque(
            [(cold_start_marking, None)] * self.order,
            maxlen=self.order
        )
        self._sfz_recovery = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_key(self, curr_marking: str) -> str:
        """Build transition key from history window + current marking."""
        prev = list(self.history)[-1][0] if self.history else 'mf'
        return f"{prev}_to_{curr_marking}"

    def _resolve_entry_key(self, transition_key: str) -> str:
        """Return the actual key used in transition_table for a given key."""
        from v2.emission import _resolve_key
        return _resolve_key(transition_key, self.transition_table)
