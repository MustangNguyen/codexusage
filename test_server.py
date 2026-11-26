import gc
import importlib.util
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('dashboard', Path(__file__).with_name('server.py'))
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)

class ResourceRegression(unittest.TestCase):
    def test_repeated_scans_close_database_connections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            conn = sqlite3.connect(root / 'state_5.sqlite')
            conn.execute('create table threads (id text, title text)')
            conn.execute("insert into threads values ('task', 'Title')")
            conn.commit()
            conn.close()
            index = dashboard.UsageIndex(root, kepler_db=None)
            gc.collect()
            was_enabled = gc.isenabled()
            gc.disable()  # Closing must not depend on eventual garbage collection.
            try:
                before = len(os.listdir('/proc/self/fd'))
                for _ in range(80):
                    index.scan()
                after = len(os.listdir('/proc/self/fd'))
                self.assertLessEqual(after, before + 2)
                self.assertEqual(index.titles['task'], 'Title')
            finally:
                if was_enabled:
                    gc.enable()
                gc.collect()

class TitleRegression(unittest.TestCase):
    def test_kepler_task_names_override_prompt_and_session_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with sqlite3.connect(root / 'state_5.sqlite') as conn:
                conn.execute('create table threads (id text, title text, name text)')
                conn.executemany('insert into threads values (?, ?, ?)', [
                    ('kepler', '<workspace-guidance>injected prompt', 'Session label'),
                    ('desktop', 'Original prompt', 'Renamed task'),
                    ('legacy', 'Old title', None),
                    ('injected', '<workspace-guidance>injected prompt', None),
                ])
            kepler = root / 'kepler.db'
            with sqlite3.connect(kepler) as conn:
                conn.execute('create table tasks (id text, name text)')
                conn.execute('''create table session_metadata (
                    adapter_id text, task_id text, resume_handle text,
                    platform_session_id text, prior_platform_ids text,
                    custom_label text, label text)''')
                conn.execute("insert into tasks values ('task', '13: làm vfx đào đất')")
                conn.execute('insert into session_metadata values (?, ?, ?, ?, ?, ?, ?)',
                             ('codex', 'task', 'kepler', 'platform', '["previous"]', None, 'Session label'))
            index = dashboard.UsageIndex(root, kepler_db=kepler)
            index.scan()
            for tid in ('kepler', 'platform', 'previous'):
                self.assertEqual(index.titles[tid], '13: làm vfx đào đất')
            self.assertEqual(index.titles['desktop'], 'Renamed task')
            self.assertEqual(index.titles['legacy'], 'Old title')
            self.assertNotIn('injected', index.titles)
            with sqlite3.connect(kepler) as conn:
                conn.execute("update tasks set name = 'Renamed Kepler task'")
            index.scan()
            self.assertEqual(index.titles['kepler'], 'Renamed Kepler task')

    def test_missing_or_incompatible_kepler_database_preserves_codex_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with sqlite3.connect(root / 'state_5.sqlite') as conn:
                conn.execute('create table threads (id text, title text, name text)')
                conn.execute("insert into threads values ('desktop', 'Prompt', 'Actual title')")
            kepler = root / 'kepler.db'
            index = dashboard.UsageIndex(root, kepler_db=kepler)
            index.scan()
            self.assertFalse(kepler.exists())
            self.assertEqual(index.titles['desktop'], 'Actual title')
            with sqlite3.connect(kepler) as conn:
                conn.execute('create table unrelated (id text)')
            index.scan()
            self.assertEqual(index.titles['desktop'], 'Actual title')

if __name__ == '__main__':
    unittest.main()
