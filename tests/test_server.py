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

    def test_source_only_preview_is_the_loaded_audio(self):
        # Concerto's "Source"/"Raw" audio: a score with no events
        self._post('/preview', {'path': self.audio, 'engine': 'v1',
                                'score': {'samples': {}, 'events': []}})
        rendered, _ = sf.read(server.PREVIEW_TMP, dtype='float32')
        source, _ = sf.read(self.audio, dtype='float32')
        self.assertEqual(len(rendered), len(source))
        # the source at its real level (no normalising; below the brake's ceiling)
        np.testing.assert_allclose(rendered, source, atol=1e-4)

    def test_preview_keeps_the_performed_level(self):
        # A quieter source renders quieter: nothing turns it back up.
        quiet = os.path.join(self.tmp, 'quiet.wav')
        sf.write(quiet, sf.read(self.audio, dtype='float32')[0] * 0.1, SR)
        levels = []
        for path in (self.audio, quiet):
            d = self._post('/preview', {'path': path, 'score': dict(self.score), 'engine': 'v1',
                                        '_config': {'seed': 3}})
            levels.append(d['loudness']['lufs'])
        self.assertAlmostEqual(levels[0] - levels[1], 20.0, delta=0.5)

    def test_brake_switch(self):
        loud = os.path.join(self.tmp, 'loud.wav')
        sf.write(loud, sf.read(self.audio, dtype='float32')[0] * 5, SR, subtype='FLOAT')
        body = {'path': loud, 'engine': 'v1', 'score': {'samples': {}, 'events': []}}
        on = self._post('/preview', {**body, 'loudness': {'brake': True}})['loudness']
        self.assertGreater(on['brake_db'], 0)
        self.assertLessEqual(on['peak_db'], -1.0 + 1e-3)
        off = self._post('/preview', {**body, 'loudness': {'brake': False}})['loudness']
        self.assertEqual(off['brake_db'], 0)
        self.assertGreater(off['peak_db'], 0)          # reported: these peaks will clip

    def test_export_loudness_target_and_range(self):
        from src.loudness import measure_lufs
        common = {'path': self.audio, 'score_path': self.score_path, 'audio_format': 'wav32f',
                  'interp': {'golems': [], 'v2config': {'v2': {'seed': 4}}},
                  'loudness': {'adjust': 'target', 'target_lufs': -23, 'brake': True}}
        full = self._post('/export_interp_wav', {**common, 'out_path': os.path.join(self.tmp, 'full.wav')})
        audio, _ = sf.read(full['path'], dtype='float32')
        self.assertAlmostEqual(measure_lufs(audio, SR), -23.0, delta=0.1)
        self.assertAlmostEqual(full['loudness']['lufs'], -23.0, delta=0.1)
        # A range gets the gain of the whole piece, not its own
        part = self._post('/export_interp_wav', {**common, 'out_path': os.path.join(self.tmp, 'part.wav'),
                                                 'time_from': 1.0, 'time_to': 2.0})
        clip, _ = sf.read(part['path'], dtype='float32')
        np.testing.assert_allclose(clip, audio[SR:2 * SR], atol=1e-5)

    def test_export_match_source(self):
        from src.loudness import measure_lufs
        d = self._post('/export_interp_wav', {
            'path': self.audio, 'score_path': self.score_path, 'audio_format': 'wav32f',
            'out_path': os.path.join(self.tmp, 'm.wav'), 'interp': {'golems': []},
            'loudness': {'adjust': 'source', 'brake': False}})
        audio, _ = sf.read(d['path'], dtype='float32')
        source, _ = sf.read(self.audio, dtype='float32')
        self.assertAlmostEqual(measure_lufs(audio, SR), measure_lufs(source, SR), delta=0.1)

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

    def test_composer_export_is_what_mix_plays(self):
        # The Composer exports its current state, rendered like its Mix
        cfg = {'seed': 21}
        _, played = self._preview_audio({'path': self.audio, 'score': dict(self.score), 'engine': 'v1',
                                         '_config': cfg, 'loudness': {'brake': True}})
        d = self._post('/export_audio', {'path': self.audio, 'score': dict(self.score), 'engine': 'v1',
                                         '_config': cfg, 'audio_format': 'wav32f',
                                         'out_path': os.path.join(self.tmp, 'composer.wav'),
                                         'loudness': {'adjust': 'none', 'brake': True}})
        exported, _ = sf.read(d['path'], dtype='float32')
        np.testing.assert_allclose(exported, played, atol=1e-6)
        self.assertTrue(d['path'].endswith('composer.wav'))

    def test_composer_export_modes_and_default_name(self):
        common = {'path': self.audio, 'score': dict(self.score), 'audio_format': 'flac',
                  'loudness': {'brake': False}}
        raw = self._post('/export_audio', {**common, 'export_mode': 'raw',
                                           'out_path': os.path.join(self.tmp, 'raw.wav')})
        self.assertTrue(raw['path'].endswith('raw.flac'))               # extension follows format
        audio, _ = sf.read(raw['path'], dtype='float32')
        source, _ = sf.read(self.audio, dtype='float32')
        np.testing.assert_allclose(audio, source, atol=1e-4)            # FLAC is 24-bit
        d = self._post('/export_audio', {**common, 'export_mode': 'score_only'})
        try:
            self.assertIn('composer_base_', os.path.basename(d['path']))  # output/composer_<audio>_<time>
        finally:
            os.remove(d['path'])

    def test_score_only_export_has_no_base(self):
        out = os.path.join(self.tmp, 'events.wav')
        d = self._post('/export_interp_wav', {'path': self.audio, 'score_path': self.score_path,
                                              'export_mode': 'score_only', 'out_path': out,
                                              'interp': {'golems': []}})
        audio, _ = sf.read(d['path'], dtype='float32')
        # Base is a steady 330 Hz tone; after the last event ends (~2 s) only
        # silence should remain if the base was dropped.
        self.assertLess(float(np.max(np.abs(audio[int(2.6 * SR):]))), 1e-4)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'needs ffmpeg')
    def test_concerto_presets_carry_real_audio(self):
        # The "2" presets used to put PCM in MPEG-TS, which ffmpeg writes as a
        # data stream: no audio. Now AC-3 in .ts; the "3" presets PCM in .mov.
        import subprocess, json
        vid = os.path.join(self.tmp, 'v.mkv')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=size=160x120:rate=10:duration=1',
                        '-c:v', 'libx265', '-preset', 'ultrafast', '-x265-params', 'log-level=error', vid],
                       check=True)                              # the segments are HEVC, as in a render
        for key, codec in (('t2', 'ac3'), ('t3', 'pcm_s24le'), ('t1', 'aac')):
            preset = server._CONCERTO_PRESETS[key]
            out = os.path.join(self.tmp, 'out_' + key + preset['ext'])
            subprocess.run(server._concerto_mux_cmd(preset, vid, self.audio, out), check=True, capture_output=True)
            streams = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,codec_name',
                                                 '-of', 'json', out], capture_output=True).stdout)['streams']
            with self.subTest(key):
                self.assertIn({'codec_type': 'audio', 'codec_name': codec}, streams)

    def test_save_preview_audio_trims_and_pads(self):
        self._post('/preview', {'path': self.audio, 'score': dict(self.score), 'engine': 'v1'})
        full, _ = sf.read(server.PREVIEW_TMP, dtype='float32')
        out = os.path.join(self.tmp, 'clip.wav')
        d = self._post('/save_preview_audio', {'out_path': out, 'time_from': 1.0, 'time_to': 2.0,
                                               'lead_in': 0.5, 'lead_out': 0.25})
        clip, _ = sf.read(d['path'], dtype='float32')
        self.assertEqual(len(clip), int(0.5 * SR) + SR + int(0.25 * SR))
        self.assertEqual(sf.info(server.PREVIEW_TMP).subtype, 'FLOAT')    # exact render
        self.assertEqual(sf.info(d['path']).subtype, 'PCM_24')             # default format
        np.testing.assert_allclose(clip[int(0.5 * SR):int(0.5 * SR) + SR], full[SR:2 * SR], atol=1e-4)

    def test_save_preview_audio_formats(self):
        self._post('/preview', {'path': self.audio, 'score': dict(self.score), 'engine': 'v1'})
        full, _ = sf.read(server.PREVIEW_TMP, dtype='float32')
        out = os.path.join(self.tmp, 'video.mp4')     # Concerto passes the video path
        for fmt, ext, subtype in (('wav32f', '.wav', 'FLOAT'), ('flac', '.flac', 'PCM_24'),
                                  ('wav16', '.wav', 'PCM_16')):
            with self.subTest(fmt=fmt):
                d = self._post('/save_preview_audio', {'out_path': out, 'audio_format': fmt})
                self.assertEqual(d['path'], os.path.join(self.tmp, 'video' + ext))
                self.assertEqual(sf.info(d['path']).subtype, subtype)
                audio, _ = sf.read(d['path'], dtype='float32')
                if fmt == 'wav32f':
                    np.testing.assert_array_equal(audio, full)          # bit-exact copy
                else:
                    np.testing.assert_allclose(audio, full, atol=1e-4)

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

    def _stems(self, path, **opts):
        d = self._post('/separate', {'path': path, **opts})
        return {s['name']: sf.read(s['path'], dtype='float32', always_2d=True)[0] for s in d['stems']}

    def test_stems_keep_the_stereo_image(self):
        t = np.arange(2 * SR) / SR
        tone = 0.3 * np.sin(2 * np.pi * 220 * t)
        clicks = np.zeros_like(t); clicks[::SR // 4] = 0.8
        src = np.stack([tone + clicks, np.zeros_like(t)], axis=1).astype(np.float32)  # all left
        path = os.path.join(self.tmp, 'lr.wav')
        sf.write(path, src, SR, subtype='FLOAT')
        for opts in ({'method': 'hpss'}, {'method': 'nmf', 'n_components': 2},
                     {'method': 'nmf', 'n_components': 2, 'nmf_mode': 'naive'},
                     {'method': 'freqband', 'bands': [{'low': 0, 'high': 1000}, {'low': 1000, 'high': 11025}]}):
            with self.subTest(**{k: v for k, v in opts.items() if k != 'bands'}):
                stems = self._stems(path, **opts)
                for name, y in stems.items():
                    self.assertEqual(y.shape, src.shape, name)                 # stereo, full length
                    self.assertLess(float(np.max(np.abs(y[:, 1]))), 1e-4, name)  # right stays silent
                if opts.get('nmf_mode') != 'naive':
                    # soft masks / band masks partition the spectrum → stems sum to the source
                    np.testing.assert_allclose(sum(stems.values()), src, atol=2e-3)

    def test_mono_stems_match_standard_hpss(self):
        import librosa
        y = (0.3 * np.sin(2 * np.pi * 220 * np.arange(SR) / SR)).astype(np.float32)
        y[::SR // 5] += 0.8
        path = os.path.join(self.tmp, 'm.wav')
        sf.write(path, y, SR, subtype='FLOAT')
        stems = self._stems(path, method='hpss')
        h, p = librosa.effects.hpss(y)
        self.assertEqual(stems['harmonic'].shape, (len(y), 1))                  # still mono
        np.testing.assert_allclose(stems['harmonic'][:, 0], h, atol=1e-5)
        np.testing.assert_allclose(stems['percussive'][:, 0], p, atol=1e-5)

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
