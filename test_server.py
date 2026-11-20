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
            index = dashboard.UsageIndex(root)
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

if __name__ == '__main__':
    unittest.main()
