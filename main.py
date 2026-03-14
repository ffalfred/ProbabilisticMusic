import argparse
from src.parser        import load_score
from src.sample_engine import build_bank
from src.scheduler     import get_events
from src.renderer      import render

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='StrategicOpacity renderer')
    parser.add_argument('-i', '--input', required=True, help='Input file (wav or mp4)')
    parser.add_argument('-s', '--score', required=True, help='Score file')
    args = parser.parse_args()

    score = load_score(args.score)
    score['base_track'] = args.input

    bank, sr, base = build_bank(score)
    events         = get_events(score)
    render(score, bank, events, sr, base)