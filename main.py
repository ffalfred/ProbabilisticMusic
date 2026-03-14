import os
import sys
import argparse
import yaml

from src.parser        import load_score
from src.sample_engine import build_bank
from src.scheduler     import get_events
from src.renderer      import render


def _load_config() -> dict:
    """Load config.yaml from the same directory as main.py, or return defaults."""
    cfg_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def _next_output_path(score_path: str, input_path: str) -> str:
    """
    Build output path: output/output_<score>_<base>_<NNN>.wav
    NNN auto-increments unless seed is set and file already exists.
    """
    os.makedirs('output', exist_ok=True)
    score_stem = os.path.splitext(os.path.basename(score_path))[0]
    base_stem  = os.path.splitext(os.path.basename(input_path))[0]
    prefix     = f"output/output_{score_stem}_{base_stem}"

    n = 1
    while True:
        path = f"{prefix}_{n:03d}.wav"
        if not os.path.exists(path):
            return path
        n += 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='StrategicOpacity renderer')
    parser.add_argument('-i', '--input', required=True, help='Input file (wav or mp4)')
    parser.add_argument('-s', '--score', required=True, help='Score file')
    args = parser.parse_args()

    config = _load_config()
    engine = config.get('engine', 'v1')

    score             = load_score(args.score)
    score['base_track'] = args.input

    bank, sr, base = build_bank(score)

    if engine == 'v2':
        # Add v2/ directory to path so relative imports work
        sys.path.insert(0, os.path.dirname(__file__))
        from v2.interpreter import interpret
        events = interpret(score, config)
    else:
        events = get_events(score)

    out_path = _next_output_path(args.score, args.input)
    render(score, bank, events, sr, base, wav_path=out_path)
