import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.repo = self.root / 'repo with spaces % $ and "quotes"'
        self.repo.mkdir()
        for name in ('install.sh', 'codexusage', 'codex-usage-dashboard.service', 'server.py'):
            shutil.copy2(Path(__file__).with_name(name), self.repo / name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'systemctl.log'
        stub = self.bin / 'systemctl'
        stub.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$INSTALL_TEST_LOG"\nexit "${INSTALL_TEST_EXIT:-0}"\n')
        stub.chmod(0o755)
        self.env = {**os.environ, 'HOME': str(self.home), 'SHELL': '/bin/zsh',
                    'XDG_CONFIG_HOME': str(self.home / '.config'),
                    'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                    'INSTALL_TEST_LOG': str(self.log)}

    def run_installer(self):
        return subprocess.run(['bash', str(self.repo / 'install.sh')], env=self.env,
                              capture_output=True, text=True)

    def test_install_and_reinstall_from_arbitrary_location(self):
        for _ in range(2):
            result = self.run_installer()
            self.assertEqual(result.returncode, 0, result.stderr)
        launcher = self.home / '.local/bin/codexusage'
        self.assertTrue(os.access(launcher, os.X_OK))
        self.assertEqual(launcher.read_bytes(), (self.repo / 'codexusage').read_bytes())
        unit = (self.home / '.config/systemd/user/codex-usage-dashboard.service').read_text()
        self.assertNotIn('@SERVER@', unit)
        self.assertNotIn('@PYTHON@', unit)
        self.assertIn('repo with spaces %% $$ and \\"quotes\\"/server.py', unit)
        for name in ('.profile', '.bashrc', '.zshrc'):
            self.assertEqual((self.home / name).read_text().count('export PATH='), 1)
        calls = self.log.read_text().splitlines()
        self.assertEqual(calls.count('--user restart codex-usage-dashboard.service'), 2)
        self.assertEqual(calls[-1], '--user is-active --quiet codex-usage-dashboard.service')

    def test_unavailable_user_service_manager_leaves_home_untouched(self):
        self.env['INSTALL_TEST_EXIT'] = '1'
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.home.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
