"""Tests for the editor server routes, via Flask's test client.

Run from the repo root:  python -m unittest discover -s tests
"""
import os
import sys
import shutil
import tempfile
import unittest

import numpy as np
import soundfile as sf
import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'editor'))

import server  # noqa: E402

SR = 22050


class ServerTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        t = np.arange(3 * SR) / SR
        self.audio = os.path.join(self.tmp, 'base.wav')
        sf.write(self.audio, (0.3 * np.sin(2 * np.pi * 330 * t)).astype(np.float32), SR)
        self.score = {
            'samples': {'a': {'from': 0.0, 'to': 0.4}},
            'events': [{'t': 0.5, 'sample': 'a', 'speed': [0.8, 1.2], 'gain_db': [-9, -3]},
                       {'t': 0.5, 'sample': 'a', 'pitch': 7},
                       {'t': 1.5, 'sample': 'a', 'reverse': {'distribution': 'bernoulli', 'p': 0.5}}],
            'dynamics': [{'t': 0, 'marking': 'p'}, {'t': 2, 'marking': 'f'}],
            'golems': [{'from': 0, 'to': 3, 'character': 'lyrical'}],
        }
        self.score_path = os.path.join(self.tmp, 'score.yaml')
        with open(self.score_path, 'w') as f:
            yaml.dump(self.score, f)
        self.client = server.app.test_client()
        self._saved_preview = server.PREVIEW_TMP
        server.PREVIEW_TMP = os.path.join(self.tmp, 'preview.wav')

    def tearDown(self):
        server.PREVIEW_TMP = self._saved_preview
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _post(self, route, body):
        r = self.client.post(route, json=body)
        data = r.get_json()
        self.assertEqual(r.status_code, 200, data)
        return data

    def _preview_audio(self, body):
        d = self._post('/preview', body)
        audio, _ = sf.read(server.PREVIEW_TMP, dtype='float32')
        return d, audio

    def test_composer_preview_resolves_random_values(self):
        d = self._post('/preview', {'path': self.audio, 'score': dict(self.score), 'engine': 'v1'})
        self.assertIn('seed', d)

    def test_preview_is_reproducible_from_its_seed(self):
        body = {'path': self.audio, 'score_path': self.score_path,
                'interp': {'golems': self.score['golems'], 'v2config': {'v2': {'seed': 11}}}}
        d1, a1 = self._preview_audio(body)
        d2, a2 = self._preview_audio(body)
        self.assertEqual(d1['seed'], 11)
        self.assertTrue(np.array_equal(a1, a2))

    def test_empty_golem_list_overrides_score_golems(self):
        self._post('/preview', {'path': self.audio, 'score_path': self.score_path,
                                'interp': {'golems': []}})
        self.assertIsNotNone(server._last_preview_trace)
        self.assertTrue(all(s['character'] == 'default' for s in server._last_preview_trace))

    def test_trace_reports_all_dimensions(self):
        d = self._post('/trace', {'score_path': self.score_path, 'interp': {}})
        self.assertEqual(len(d['dimensions']), 12)

    def test_score_only_export_has_no_base(self):
        out = os.path.join(self.tmp, 'events.wav')
        d = self._post('/export_interp_wav', {'path': self.audio, 'score_path': self.score_path,
                                              'export_mode': 'score_only', 'out_path': out,
                                              'interp': {'golems': []}})
        audio, _ = sf.read(d['path'], dtype='float32')
        # Base is a steady 330 Hz tone; after the last event ends (~2 s) only
        # silence should remain if the base was dropped.
        self.assertLess(float(np.max(np.abs(audio[int(2.6 * SR):]))), 1e-4)

    def test_save_preview_audio_trims_and_pads(self):
        self._post('/preview', {'path': self.audio, 'score': dict(self.score), 'engine': 'v1'})
        full, _ = sf.read(server.PREVIEW_TMP, dtype='float32')
        out = os.path.join(self.tmp, 'clip.wav')
        d = self._post('/save_preview_audio', {'out_path': out, 'time_from': 1.0, 'time_to': 2.0,
                                               'lead_in': 0.5, 'lead_out': 0.25})
        clip, _ = sf.read(d['path'], dtype='float32')
        self.assertEqual(len(clip), int(0.5 * SR) + SR + int(0.25 * SR))
        self.assertEqual(sf.info(d['path']).subtype, sf.info(server.PREVIEW_TMP).subtype)
        np.testing.assert_allclose(clip[int(0.5 * SR):int(0.5 * SR) + SR], full[SR:2 * SR], atol=1e-4)

    def test_resume_metadata_round_trip(self):
        out = os.path.join(self.tmp, 'video.ts')
        self._post('/concerto_save_trace', {'out_path': out, 'seed': 5, 'tempo_map': [[0, 0], [3, 3]]})
        d = self._post('/concerto_load_trace', {'out_path': out})
        self.assertEqual(d['seed'], 5)
        self.assertEqual(d['tempo_map'], [[0, 0], [3, 3]])
        # .ts and suffixed (meta / viz) segment files are found
        for name in ('video_meta.ts.seg_0003.mkv', 'video.ts.seg_0000.mkv'):
            with open(os.path.join(self.tmp, name), 'wb') as f:
                f.write(b'x')
        d = self._post('/concerto_check_segments', {'out_path': out})
        self.assertEqual(d['existing'], [0, 3])

    def test_only_the_editor_page_can_use_the_server(self):
        secret = os.path.join(self.tmp, 'secret.png')
        with open(secret, 'wb') as f:
            f.write(b'\x89PNG')
        url = '/image?path=' + secret
        self.assertEqual(self.client.get(url).status_code, 200)        # editor page
        self.assertEqual(self.client.get(url, headers={'Sec-Fetch-Site': 'same-origin'}).status_code, 200)
        # A different website, another localhost port, or DNS rebinding
        self.assertEqual(self.client.get(url, headers={'Sec-Fetch-Site': 'cross-site'}).status_code, 403)
        self.assertEqual(self.client.post('/load_yaml', json={'path': self.score_path},
                                          headers={'Origin': 'http://localhost:3000'}).status_code, 403)
        self.assertEqual(self.client.get(url, headers={'Host': 'evil.example:5000'}).status_code, 403)

    def test_concurrent_frame_batches_are_written_in_order(self):
        import io, threading, time

        class SlowPipe:
            closed = False
            def __init__(self): self.frames = []
            def write(self, b):
                time.sleep(0.002)          # a busy encoder: writes block briefly
                self.frames.append(b)

        class FakeProc:
            def __init__(self): self.stdin = SlowPipe()

        proc = FakeProc()
        server._concerto_ffmpeg, server._concerto_next, server._concerto_buf = proc, 0, {}
        try:
            def send(start):
                frames = [bytes([i]) * 4 for i in range(start, start + 10)]
                self.client.post('/concerto_frames', data={
                    'frames': (io.BytesIO(b''.join(frames)), 'f'),
                    'start_index': str(start), 'count': '10', 'lengths': ','.join(['4'] * 10)})
            # Batches arrive concurrently and out of order, like 3 in-flight uploads.
            threads = [threading.Thread(target=send, args=(s,)) for s in (20, 0, 10, 40, 30)]
            for th in threads:
                th.start()
            for th in threads:
                th.join()
            self.assertEqual([f[0] for f in proc.stdin.frames], list(range(50)))
        finally:
            server._concerto_ffmpeg, server._concerto_buf = None, {}


if __name__ == '__main__':
    unittest.main()
