def get_events(score: dict) -> list[dict]:
    events = score.get('events', [])
    return sorted(events, key=lambda e: e['t'])
