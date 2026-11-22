import os
import tempfile
import subprocess
from collections import OrderedDict
import numpy as np
import soundfile as sf
import threading
from src.dsp import as_frames, to_channels, pad_frames, fit_frames, env_mul, per_channel
from src.rand import rng


def _resolve(val, default=0):
    """Resolve a fixed / range / gaussian parameter to a concrete float."""
    if isinstance(val, list) and len(val) == 2:
        return float(rng().uniform(val[0], val[1]))
    if isinstance(val, dict):
        dist = val.get('distribution', '')
        if dist == 'gaussian':
            return float(rng().normal(val.get('mean', default or 0), abs(val.get('std', 0))))
        return None if default is None else float(default)
    if val is None:
        return None if default is None else float(default)
    return float(val)


def _wet_dry_mix(dry: np.ndarray, wet_processed: np.ndarray, wet_amount: float) -> np.ndarray:
    """Equal-power crossfade for effects that transform the sound itself
    (overdrive, flanger, chorus):

        out = dry * sqrt(1 - wet) + wet_norm * sqrt(wet)

    The processed signal is loudness-matched to the dry (RMS), so wet=1 is
    the pure effect at the dry's loudness and the blend keeps the level
    steady. Reverb and delay don't use this: they add their effect on top
    of the original with separate dry and wet levels (see _reverb, _delay).

    RMS is computed on the original (unpadded) signals, then both are padded
    to the longer length.
    """
    wet_amount = float(np.clip(wet_amount, 0.0, 1.0))
    dry = as_frames(dry)
    wet = to_channels(wet_processed, dry.shape[1])
    in_rms  = _rms(dry)
    wet_rms = _rms(wet)
    n = max(len(dry), len(wet))
    dry = pad_frames(dry, n)
    wet = pad_frames(wet, n)
    if wet_amount < 1e-6:
        return dry
    if in_rms > 1e-6 and wet_rms > 1e-6:
        wet = wet * (in_rms / wet_rms)
    return (dry * float(np.sqrt(1.0 - wet_amount)) + wet * float(np.sqrt(wet_amount))).astype(np.float32)


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64)))) if len(x) else 0.0


def _dry_wet(fx: dict, wet_default: float = 0.5):
    """dry = level of the original (default 1: kept in full), wet = level of
    the effect. Both 0..1."""
    dry = float(np.clip(_resolve(fx.get('dry', 1.0), 1.0), 0.0, 1.0))
    wet = float(np.clip(_resolve(fx.get('wet', wet_default), wet_default), 0.0, 1.0))
    return dry, wet


# ── Per-FX frequency targeting ───────────────────────────────────────────────

def _band_split(clip, sr, freq_from, freq_to):
    """Split clip into (target_band, rest) using Linkwitz-Riley crossover.
    Returns (target, rest) where target + rest ≈ clip. Filters along time
    (axis 0), so (frames, channels) audio keeps its channels separate."""
    from scipy.signal import butter, sosfilt
    nyq = sr / 2.0
    order = 4  # LR4

    if freq_from and freq_to:
        lo = max(20, min(float(freq_from), nyq - 1))
        hi = max(lo + 1, min(float(freq_to), nyq - 1))
        sos_bp = butter(order, [lo, hi], btype='band',     fs=sr, output='sos')
        sos_bs = butter(order, [lo, hi], btype='bandstop',  fs=sr, output='sos')
        target = sosfilt(sos_bp, clip, axis=0).astype(np.float32)
        rest   = sosfilt(sos_bs, clip, axis=0).astype(np.float32)
    elif freq_from:
        lo = max(20, min(float(freq_from), nyq - 1))
        sos_hp = butter(order, lo, btype='high', fs=sr, output='sos')
        sos_lp = butter(order, lo, btype='low',  fs=sr, output='sos')
        target = sosfilt(sos_hp, clip, axis=0).astype(np.float32)
        rest   = sosfilt(sos_lp, clip, axis=0).astype(np.float32)
    elif freq_to:
        hi = max(20, min(float(freq_to), nyq - 1))
        sos_lp = butter(order, hi, btype='low',  fs=sr, output='sos')
        sos_hp = butter(order, hi, btype='high', fs=sr, output='sos')
        target = sosfilt(sos_lp, clip, axis=0).astype(np.float32)
        rest   = sosfilt(sos_hp, clip, axis=0).astype(np.float32)
    else:
        return clip, None

    return target, rest


# ── Per-event FX dispatch ────────────────────────────────────────────────────

def _apply_single_fx(clip, sr, fx):
    """Dispatch a single FX dict to the appropriate handler.

    clip is (frames, channels). SoX effects and delay/filter/tremolo process
    all channels together (SoX's reverb gets real stereo spread), and so do
    overtones (Rubber Band); chorus and spectral inversion are mono and run per
    channel with identical random draws; plugins handle channels in apply_plugin."""
    t = fx.get('type', '')
    if   t == 'delay':               return _delay(clip, sr, fx)
    elif t == 'reverb':              return _reverb(clip, sr, fx)
    elif t == 'overdrive':           return _overdrive(clip, sr, fx)
    elif t == 'flanger':             return _flanger(clip, sr, fx)
    elif t == 'pitch':               return _pitch(clip, sr, fx)
    elif t == 'compress':            return _compress(clip, sr, fx)
    elif t == 'eq':                  return _eq(clip, sr, fx)
    elif t == 'filter':              return _filter(clip, sr, fx)
    elif t == 'chorus':              return per_channel(lambda c: _chorus(c, sr, fx), clip)
    elif t == 'tremolo':             return _tremolo(clip, sr, fx)
    elif t == 'spectral_inversion':  return per_channel(lambda c: _spectral_inversion(c, sr, fx), clip)
    elif t == 'overtones':           return _overtones(clip, sr, fx)
    elif t.startswith('morpho_'):
        from plugins import apply_plugin
        return apply_plugin(clip, sr, fx)
    return clip


def apply_fx(clip: np.ndarray, sr: int, fx_list: list) -> np.ndarray:
    """Apply a list of FX dicts to a clip sequentially.
    Each FX may optionally carry freq_from / freq_to (Hz) to restrict it
    to a frequency band; the rest of the spectrum passes through untouched.
    Returns (frames, channels) with the input's channel count."""
    clip = as_frames(clip)
    channels = clip.shape[1]
    for fx in fx_list:
        freq_from = fx.get('freq_from')
        freq_to   = fx.get('freq_to')

        if freq_from is not None or freq_to is not None:
            target, rest = _band_split(clip, sr, freq_from, freq_to)
            target = to_channels(_apply_one(target, sr, fx), channels)
            # Recombine — target may be longer than rest (reverb/delay tail)
            n = max(len(target), len(rest))
            clip = (pad_frames(rest, n) + pad_frames(target, n)).astype(np.float32)
        else:
            clip = to_channels(_apply_one(clip, sr, fx), channels)

    return clip


def _apply_one(clip, sr, fx):
    """One effect; settings given as curves change over time (src/automation.py)."""
    from src import automation
    if automation.has_curves(fx):
        return automation.apply(clip, sr, fx, _apply_single_fx)
    return _apply_single_fx(clip, sr, fx)


# ── Section and global FX ────────────────────────────────────────────────────

def apply_zone(audio: np.ndarray, sr: int, i0: int, i1: int, fx_list: list, zone: dict) -> np.ndarray:
    """Effects on samples i0..i1 of (frames, channels) audio — an FX zone.

    Without `fade`, the zone is replaced by its processed version, and any
    tail the effects add (reverb, delay) rings on past the zone, on top of
    what follows. With `fade: true`, the effects' contribution (processed −
    original) fades in and out over `fade_in_s` / `fade_out_s` (default a
    tenth of the zone, 0.01–1 s) while the original stays, so the zone
    blends in without a seam. Returns new audio, longer if a tail ran past
    the end.
    """
    channels = audio.shape[1]
    i0 = max(0, int(i0))
    i1 = min(int(i1), len(audio))
    if i0 >= len(audio) or i0 >= i1:
        return audio
    audio = audio.copy()
    segment = audio[i0:i1].copy()
    processed = to_channels(apply_fx(segment, sr, fx_list), channels)
    core_len = i1 - i0

    if zone.get('fade'):
        # Default fade is 1:10 of the zone, clamped to [0.01, 1.0] seconds
        default_s = max(0.01, min(1.0, core_len / sr / 10.0))
        fi_n = min(int(float(zone.get('fade_in_s',  default_s)) * sr), core_len // 2)
        fo_n = min(int(float(zone.get('fade_out_s', default_s)) * sr), core_len // 2)
        # Envelope the effects' contribution (the delta), not the whole
        # processed buffer: the original stays intact at the edges and the
        # tail extension is bounded
        dry_padded = np.zeros_like(processed)
        dry_padded[:core_len] = segment
        delta = processed - dry_padded
        from src.envelope import fade_ramp, DEFAULT_FADE_CURVE
        curve = zone.get('fade_curve', DEFAULT_FADE_CURVE)
        env = np.ones(len(delta), dtype=np.float32)
        if fi_n > 0:
            env[:fi_n] = fade_ramp(fi_n, curve)
        if fo_n > 0:
            fo_end = min(len(delta), core_len + fo_n)
            env[core_len:fo_end] = fade_ramp(fo_end - core_len, curve)[::-1]
            env[fo_end:] = 0.0
        else:
            env[core_len:] = 0.0          # no tail bleed if fade_out is 0
        delta = env_mul(delta, env)
        out_end = i0 + len(delta)
        audio = pad_frames(audio, out_end)
        audio[i0:out_end] += delta        # original already there: add the effect
    else:
        audio[i0:i1] = 0.0
        out_end = i0 + len(processed)
        audio = pad_frames(audio, out_end)
        audio[i0:out_end] += processed
    return audio


def apply_section_fx(audio: np.ndarray, sr: int, fx_sections: list,
                     tempo_map: list = None, score_to_real=None) -> np.ndarray:
    """FX zones on the whole output (source + events), after the tempo stretch.

    Each section is a zone like fx_ranges: {from, to, fx: [...], fade,
    fade_in_s, fade_out_s} — an effect chain whose tails ring past the zone
    (see apply_zone). Times are score times, mapped to the rendered audio
    through the tempo map, so a section sits where it is drawn.
    The older form, one effect written flat in the section ({from, to, type,
    ...params}), still works: it gets short crossfades and no tail, as before.
    """
    if not fx_sections:
        return audio
    audio = as_frames(audio)
    to_real = (lambda t: score_to_real(t, tempo_map)) if (tempo_map and score_to_real) else (lambda t: t)
    for sec in fx_sections:
        if sec.get('muted'):
            continue
        if 'fx' in sec:
            fx_list, zone = sec['fx'], sec
        else:
            fx_list = [{k: v for k, v in sec.items() if k not in ('from', 'to', 'label', 'muted')}]
            zone = {'fade': True, 'fade_in_s': 0.006, 'fade_out_s': 0.006}
        t_from = float(sec.get('from', 0))
        t_to = float(sec['to']) if sec.get('to') is not None else None
        i0 = int(to_real(t_from) * sr)
        i1 = int(to_real(t_to) * sr) if t_to is not None else len(audio)
        audio = apply_zone(audio, sr, i0, i1, fx_list, zone)
    return audio


def apply_global_fx(audio: np.ndarray, sr: int, fx_global: list) -> np.ndarray:
    """Apply FX to the entire track output."""
    if not fx_global:
        return audio
    return apply_fx(audio, sr, fx_global)


# ── Classic FX implementations ───────────────────────────────────────────────

def _delay(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Echoes added after the original.

    dry      level of the original (1 = full)
    wet      level of the first echo, relative to the original
    feedback each further echo is this much of the previous one
    time     seconds between echoes

    E.g. dry 1, wet 0.5, feedback 0.6 → note 1.0, echoes 0.5, 0.3, 0.18, …
    Echoes continue until they fall below -60 dB (at most 30 s of tail).
    """
    time     = float(np.clip(_resolve(fx.get('time', fx.get('delay_sec', 0.3)), 0.3), 0.01, 4.0))
    feedback = float(np.clip(_resolve(fx.get('feedback', 0.6), 0.6), 0.0, 0.95))
    dry, wet = _dry_wet(fx)

    clip = as_frames(clip)
    delay_samples = int(round(time * sr))
    if delay_samples < 1 or len(clip) == 0:
        return (clip * dry).astype(np.float32)

    amps = []
    a = wet
    while a >= 1e-3 and len(amps) * time < 30.0:
        amps.append(a)
        a *= feedback
        if feedback <= 0:
            break
    out = np.zeros((len(clip) + delay_samples * len(amps), clip.shape[1]), dtype=np.float32)
    out[:len(clip)] = clip * dry
    for tap, amp in enumerate(amps, start=1):
        off = delay_samples * tap
        out[off:off + len(clip)] += clip * amp
    return out


def _reverb_params(fx: dict):
    # Support both old 'reverberance' param and new 'room' alias
    room = _resolve(fx.get('room', None), None)
    if room is not None:
        reverberance = int(np.clip(room * 100, 0, 100))
    else:
        reverberance = int(np.clip(_resolve(fx.get('reverberance', 50), 50), 0, 100))
    damping    = int(np.clip(_resolve(fx.get('damping', 50), 50), 0, 100))
    room_scale = int(np.clip(_resolve(fx.get('room_scale', 100), 100), 0, 100))
    pre_delay  = int(np.clip(_resolve(fx.get('pre_delay', 0), 0), 0, 500))
    return reverberance, damping, room_scale, pre_delay


# SoX's reverb is a fixed linear filter, so its response to one click (the
# impulse response) describes it completely. Recorded once per setting and
# applied by FFT convolution, a short event costs ~50 ms instead of running
# SoX over the whole (mostly silent) tail. Matches SoX to about -85 dB.
_IR_CACHE   = OrderedDict()   # (sox args, sr, channels) -> (frames, ch_in, ch_out)
_SPEC_CACHE = OrderedDict()   # (ir key, nfft) -> rfft of the IR, complex64
_IR_LOCK    = threading.RLock()   # events are processed in parallel threads


def _reverb_ir(args: list, sr: int, channels: int, pad_s: float) -> np.ndarray:
    key = (tuple(args), sr, channels)
    with _IR_LOCK:
        if key in _IR_CACHE:
            _IR_CACHE.move_to_end(key)
            return _IR_CACHE[key]
        return _record_ir(key, args, sr, channels, pad_s)


def _record_ir(key, args, sr, channels, pad_s):
    for _ in range(4):
        n = int(pad_s * sr)
        resp = []
        for c in range(channels):                    # a click in each input channel
            imp = np.zeros((n, channels), np.float32)
            imp[0, c] = 0.25
            resp.append(_sox(imp, sr, args, linear=False) / 0.25)
        ir = np.stack(resp, axis=1)                  # (frames, ch_in, ch_out)
        level = np.max(np.abs(ir), axis=(1, 2))
        peak = float(level.max())
        if peak <= 0 or level[-int(0.05 * sr):].max() < peak * 1e-4:   # rang out (-80 dB)
            break
        pad_s *= 2
    if peak > 0:
        ir = ir[:int(np.nonzero(level > peak * 1e-4)[0].max()) + 1]
    _IR_CACHE[key] = ir.astype(np.float32)
    while len(_IR_CACHE) > 16:
        _IR_CACHE.popitem(last=False)
    return _IR_CACHE[key]


def _convolve_ir(clip: np.ndarray, ir: np.ndarray, key) -> np.ndarray:
    from scipy import fft as sfft
    n, L = len(clip), len(ir)
    nfft = 1 << int(np.ceil(np.log2(n + L - 1)))     # few sizes → spectra get reused
    skey = (key, nfft)
    with _IR_LOCK:
        if skey in _SPEC_CACHE:
            _SPEC_CACHE.move_to_end(skey)
            H = _SPEC_CACHE[skey]
        else:
            H = sfft.rfft(ir, nfft, axis=0).astype(np.complex64)
            _SPEC_CACHE[skey] = H
            while len(_SPEC_CACHE) > 8:
                _SPEC_CACHE.popitem(last=False)
    X = sfft.rfft(clip, nfft, axis=0)     # (bins, ch_in)
    Y = np.einsum('bi,bio->bo', X, H)                 # each output sums every input
    return sfft.irfft(Y, nfft, axis=0)[:n + L - 1].astype(np.float32)


def reverb_wet(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """The reverb alone (no original), loudness-matched to `clip` while the
    original sounds, and long enough for the tail to die away (-60 dB).

    SoX returns exactly as much audio as it is given, which used to cut the
    reverb off at the end of the clip. The tail length comes from the
    setting's impulse response (reverberance 100 rings ~11 s, 50 ~2 s).
    Short clips are convolved with it; long ones (the whole mix) go through
    SoX directly, padded by the tail length.
    """
    reverberance, damping, room_scale, pre_delay = _reverb_params(fx)
    clip = as_frames(clip)
    n, ch = len(clip), clip.shape[1]
    if n == 0:
        return clip
    # `-w`: wet only. Stereo depth 100 (full); wet gain 0 dB.
    args = ['reverb', '-w', str(reverberance), str(damping), str(room_scale), '100', str(pre_delay), '0']
    pad_s = 0.5 + pre_delay / 1000 + 12.0 * (reverberance / 100) ** 2 * (0.3 + 0.7 * room_scale / 100)
    ir = _reverb_ir(args, sr, ch, pad_s)
    if n <= 4 * len(ir):
        wet = _convolve_ir(clip, ir, (tuple(args), sr, ch))
    else:
        wet = _sox(pad_frames(clip, n + len(ir)), sr, args)

    level = np.max(np.abs(wet), axis=1)
    peak = float(level.max())
    if peak <= 0:
        return np.zeros_like(clip)
    end = max(n, int(np.nonzero(level > peak * 1e-3)[0].max()) + 1)    # -60 dB
    wet = wet[:end]
    fade = min(int(0.02 * sr), end - n)                                  # smooth the cut
    if fade > 1:
        wet[end - fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)[:, None]
    # As loud as the original while it sounds: RMS over the original's span.
    in_rms, w_rms = _rms(clip), _rms(wet[:n])
    if in_rms > 1e-9 and w_rms > 1e-9:
        wet = wet * (in_rms / w_rms)
    return wet.astype(np.float32)


def _reverb(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Reverb added to the original.

    dry  level of the original (1 = full)
    wet  level of the reverb: 1 = as loud as the original while it sounds
    The tail rings on past the end of the clip until it dies away.
    """
    dry, wet = _dry_wet(fx)
    clip = as_frames(clip)
    if wet <= 0:
        return (clip * dry).astype(np.float32)
    out = reverb_wet(clip, sr, fx) * wet
    out[:len(clip)] += clip * dry
    return out.astype(np.float32)


def _overdrive(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    # Support both old 'gain' param and new 'drive' param
    drive = fx.get('drive', None)
    if drive is not None:
        gain = int(np.clip(_resolve(drive, 0.6) * 100, 0, 100))
    else:
        gain = int(np.clip(_resolve(fx.get('gain', 60), 60), 0, 100))
    tone = int(np.clip(_resolve(fx.get('tone', fx.get('colour', 20)), 20), 0, 100))
    wet  = _resolve(fx.get('wet', 1.0), 1.0)

    distorted = _sox(clip, sr, ['overdrive', str(gain), str(tone)], linear=False)
    # 'replace' mode: at wet=1 the signal IS the distorted version (loudness
    # matched to dry, so no volume jump). At wet=0 it's pure dry. Drop wet
    # for parallel distortion blends.
    return _wet_dry_mix(clip, distorted, wet)


def _flanger(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    delay = np.clip(_resolve(fx.get('delay_ms', 0),   0),   0,   30)
    depth = np.clip(_resolve(fx.get('depth', fx.get('depth_ms', 6)), 6), 0, 10)
    speed = np.clip(_resolve(fx.get('rate', fx.get('speed_hz', 2.0)), 2.0), 0.1, 10)
    feedback = np.clip(_resolve(fx.get('feedback', 80), 80), -95, 95)
    wet      = _resolve(fx.get('wet', 0.7), 0.7)

    # sox flanger args: delay depth regen width speed shape phase interp
    # regen (-95..95) = feedback %, width 71 = sox default, phase 25 = sox default
    flanged = _sox(clip, sr, [
        'flanger',
        str(round(delay, 2)),
        str(round(depth, 2)),
        str(round(feedback, 0)),
        '71',
        str(round(speed, 2)),
        'sine', '25', 'linear',
    ])
    # 'replace' mode: at wet=1 you hear pure flanged signal at dry loudness
    # (source replaced by the modulated version).
    return _wet_dry_mix(clip, flanged, wet)


def _pitch(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    semitones = fx.get('semitones', None)
    if semitones is not None:
        cents = int(np.clip(_resolve(semitones, 0) * 100, -2400, 2400))
    else:
        cents = int(np.clip(_resolve(fx.get('cents', 0), 0), -2400, 2400))
    return _sox(clip, sr, ['pitch', str(cents)])


def _compress(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    threshold  = np.clip(_resolve(fx.get('threshold', fx.get('threshold_db', -20)), -20), -80, 0)
    ratio      = max(1.0, np.clip(_resolve(fx.get('ratio', 4), 4), 1, 50))
    attack     = np.clip(_resolve(fx.get('attack',  0.01), 0.01), 0.001, 2.0)
    release    = np.clip(_resolve(fx.get('release', 0.3),  0.3),  0.01,  5.0)
    makeup     = np.clip(_resolve(fx.get('makeup_db', 0),  0),    -20,   40)
    above_out  = threshold + (0 - threshold) / ratio
    transfer   = f"6:-80,-80,{threshold},{threshold},0,{above_out:.1f}"
    return _sox(clip, sr, ['compand', f"{attack:.4f},{release:.4f}", transfer,
                           str(round(makeup, 1))], linear=False)


def _eq(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    # Support both single-band and multi-band ('bands' list)
    bands = fx.get('bands')
    if bands and isinstance(bands, list):
        result = clip
        for band in bands:
            freq = np.clip(_resolve(band.get('freq', 1000), 1000), 20, sr / 2 - 1)
            gain = np.clip(_resolve(band.get('gain', 0), 0), -40, 40)
            q    = max(0.1, _resolve(band.get('q', 1.0), 1.0))
            result = _sox(result, sr, ['equalizer', str(round(freq, 1)),
                                       f"{round(q, 2)}q", str(round(gain, 1))])
        return result

    freq = np.clip(_resolve(fx.get('freq_hz', fx.get('freq', 1000)), 1000), 20, sr / 2 - 1)
    gain = np.clip(_resolve(fx.get('gain_db', fx.get('gain', 0)), 0), -40, 40)
    q    = max(0.1, _resolve(fx.get('q', 1.0), 1.0))
    return _sox(clip, sr, ['equalizer', str(round(freq, 1)),
                           f"{round(q, 2)}q", str(round(gain, 1))])


# ── New FX ───────────────────────────────────────────────────────────────────

def _filter(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Lowpass / highpass / bandpass filter using scipy."""
    from scipy.signal import butter, sosfilt

    cutoff    = np.clip(_resolve(fx.get('cutoff', 1000), 1000), 20, sr / 2 - 1)
    resonance = np.clip(_resolve(fx.get('resonance', 0), 0), 0, 1)
    ftype     = fx.get('filter_type', fx.get('type_', 'lp')).lower()

    # Map resonance 0–1 to Q 0.5–12
    q = 0.5 + resonance * 11.5

    btype_map = {'lp': 'low', 'hp': 'high', 'bp': 'band',
                 'lowpass': 'low', 'highpass': 'high', 'bandpass': 'band'}
    btype = btype_map.get(ftype, 'low')

    try:
        if btype == 'band':
            # Bandpass needs [low, high] — use cutoff ± bandwidth
            bw = cutoff * 0.3 / max(q, 0.5)
            low  = max(20, cutoff - bw)
            high = min(sr / 2 - 1, cutoff + bw)
            sos = butter(2, [low, high], btype='band', fs=sr, output='sos')
        else:
            sos = butter(2, cutoff, btype=btype, fs=sr, output='sos')
        return sosfilt(sos, as_frames(clip), axis=0).astype(np.float32)
    except Exception:
        return clip


def _chorus(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Chorus effect — modulated delay mixed with dry signal."""
    rate  = np.clip(_resolve(fx.get('rate', 1.5), 1.5), 0.1, 10)
    depth = np.clip(_resolve(fx.get('depth', 0.5), 0.5), 0.0, 1.0)
    wet   = np.clip(_resolve(fx.get('wet', 0.5), 0.5), 0.0, 1.0)

    # Modulated delay in samples
    max_delay_ms = 25.0 * depth
    max_delay_samples = int(max_delay_ms * sr / 1000)
    if max_delay_samples < 1:
        return clip

    n = len(clip)
    t = np.arange(n, dtype=np.float32)
    mod = max_delay_samples * 0.5 * (1 + np.sin(2 * np.pi * rate * t / sr))
    mod = mod.astype(np.float32)

    # Read position i - mod[i], linearly interpolated (before the start of
    # the clip the dry sample is used)
    pos   = np.arange(n, dtype=np.float32) - mod
    lo    = np.clip(np.floor(pos).astype(np.int64), 0, n - 1)
    hi    = np.minimum(lo + 1, n - 1)
    frac  = (pos - np.floor(pos)).astype(np.float32)
    result = np.where(pos >= 0, clip[lo] * (1 - frac) + clip[hi] * frac, clip).astype(np.float32)

    return _wet_dry_mix(clip, result, wet)


def _tremolo(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Tremolo — amplitude modulation at a given rate."""
    rate  = np.clip(_resolve(fx.get('rate', 5.0), 5.0), 0.1, 30)
    depth = np.clip(_resolve(fx.get('depth', 0.5), 0.5), 0.0, 1.0)

    n = len(clip)
    t = np.arange(n, dtype=np.float32) / sr
    mod = 1.0 - depth * 0.5 * (1 + np.sin(2 * np.pi * rate * t))
    return env_mul(clip, mod)


# ── Spectral FX ──────────────────────────────────────────────────────────────

def _spectral_inversion(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Invert spectral amplitude within a frequency band."""
    try:
        import librosa
    except ImportError:
        return clip

    low_hz       = max(0, _resolve(fx.get('low_hz', 20), 20))
    high_hz      = min(sr / 2 - 1, _resolve(fx.get('high_hz', 10000), 10000))
    amount       = np.clip(_resolve(fx.get('amount', 100), 100), 0, 100) / 100.0
    dry_wet      = np.clip(_resolve(fx.get('dry_wet', 100), 100), 0, 100) / 100.0
    threshold_db = _resolve(fx.get('threshold_db', -60), -60)
    n_fft        = int(fx.get('fft_size', 2048))

    audio = clip.astype(np.float32)
    D     = librosa.stft(audio, n_fft=n_fft)
    mag, phase = np.abs(D), np.angle(D)

    freqs      = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    freq_mask  = (freqs >= low_hz) & (freqs <= high_hz)

    global_max = float(np.max(mag)) if np.max(mag) > 0 else 1.0
    thresh_lin = global_max * (10.0 ** (threshold_db / 20.0))

    band_mag = mag[freq_mask, :]
    if band_mag.size > 0:
        b_max = float(np.max(band_mag))
        b_min = float(np.min(band_mag))
        inv_band = (b_max + b_min) - band_mag
        inv_band = band_mag + (inv_band - band_mag) * amount

        above = band_mag > thresh_lin
        band_mag[above] = inv_band[above]
        mag[freq_mask, :] = band_mag

    D_inv = mag * np.exp(1j * phase)
    y_inv = librosa.istft(D_inv, length=len(audio))

    # RMS-match y_inv to the input so spectral peaks don't make the
    # inverted signal much louder than the dry one.
    in_rms  = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    out_rms = float(np.sqrt(np.mean(y_inv.astype(np.float64) ** 2)))
    if in_rms > 1e-6 and out_rms > 1e-6:
        y_inv = y_inv * (in_rms / out_rms)

    result = audio * (1.0 - dry_wet) + y_inv * dry_wet
    return result.astype(np.float32)


def _overtones(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Add synthetic harmonics (overtones) above the fundamental: pitch-shifted
    copies at the nearest semitone to each harmonic (octave, 12th, ...).
    `clip` is (frames, channels); channels are shifted together."""
    from src.stretch import pitch_shift, parallel_map

    n_harmonics = max(1, int(fx.get('n_harmonics', 3)))
    gain_db     = np.clip(_resolve(fx.get('gain_db', -6), -6), -60, 12)
    gain_lin    = 10.0 ** (gain_db / 20.0)

    result = clip.astype(np.float32).copy()

    harmonics = range(2, n_harmonics + 2)
    shifted = parallel_map(lambda h: pitch_shift(clip, sr, float(round(12.0 * np.log2(h)))), harmonics)
    for h, harmonic in zip(harmonics, shifted):
        # Gentler falloff: 1/sqrt(h-1) so higher harmonics stay audible
        h_gain = gain_lin / float(np.sqrt(h - 1))
        min_len = min(len(result), len(harmonic))
        result[:min_len] += harmonic[:min_len] * h_gain

    return result.astype(np.float32)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sox(clip: np.ndarray, sr: int, effect: list, linear: bool = True) -> np.ndarray:
    """Run one SoX effect on `clip` (frames, channels) and return the result
    with the same channels — SoX processes them together, e.g. reverb's
    stereo depth and flanger's channel phase offset spread a stereo input.

    Audio goes to and from SoX as 32-bit float: 16-bit temp files make SoX
    add random dither, so the same seed gave different output. SoX still
    clips at ±1, and pre-normalisation mixes often exceed that, so for
    linear effects the signal is scaled down for headroom and back up
    afterwards. Level-dependent effects (overdrive, compand) pass
    linear=False and see the signal at its real level.
    """
    peak = float(np.max(np.abs(clip))) if len(clip) else 0.0
    gain = peak / 0.25 if linear and peak > 0.25 else 1.0
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        tmp_in = f.name
    tmp_out = tmp_in.replace('.wav', '_out.wav')
    try:
        sf.write(tmp_in, clip / gain, sr, subtype='FLOAT')
        subprocess.run(['sox', tmp_in, '-e', 'floating-point', '-b', '32', tmp_out, *effect],
                       check=True, capture_output=True)
        result, _ = sf.read(tmp_out, dtype='float32', always_2d=True)
    finally:
        for p in (tmp_in, tmp_out):
            try: os.remove(p)
            except OSError: pass
    return to_channels(result * gain, as_frames(clip).shape[1])
