"""Exercise branch guards against an isolated local Git remote."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ExperimentalBranchGuardTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / '.audio-model-check-hooks'
        parent.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temporary.name).resolve()
        self.assertTrue(self.root.is_relative_to(parent.resolve()))
        self.addCleanup(self.temporary.cleanup)
        self.work = self.root / 'work'
        self.work.mkdir()
        self.git('init', '--bare', str(self.root / 'remote.git'))
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Hook Test')
        self.git('config', 'user.email', 'hook-test@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'tag.gpgsign', 'false')
        self.git('config', 'core.hooksPath', (ROOT / '.githooks').as_posix())
        self.git('remote', 'add', 'origin', str(self.root / 'remote.git'))
        (self.work / '.gitignore').write_text('/experimentals/\n', encoding='utf-8')
        self.git('add', '.gitignore')
        self.git('commit', '-m', 'Initial main')
        self.main = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('push', '-u', 'origin', 'main')

    def git(self, *args, blocked=False):
        result = subprocess.run(['git', *args], cwd=self.work, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=30)
        if blocked:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn('Blocked: experimentals/', result.stderr)
        else:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def add_experiment(self):
        folder = self.work / 'experimentals'
        folder.mkdir()
        (folder / 'example.txt').write_text('Example experiment\n', encoding='utf-8')
        self.git('add', '-f', 'experimentals/example.txt')

    def test_main_blocks_forced_add(self):
        self.add_experiment()
        self.git('commit', '-m', 'Wrong branch', blocked=True)
        self.assertEqual(self.git('rev-parse', 'HEAD').stdout.strip(), self.main)

    def test_experiments_push_only_to_experimental(self):
        self.git('switch', '-c', 'experimental')
        self.add_experiment()
        self.git('commit', '-m', 'Experiment')
        self.git('push', '-u', 'origin', 'experimental')
        self.git('push', 'origin', 'experimental:main', blocked=True)
        self.git('tag', 'experiment-tag')
        self.git('push', 'origin', 'refs/tags/experiment-tag', blocked=True)
        remote_main = self.git('ls-remote', 'origin', 'refs/heads/main').stdout.split()[0]
        self.assertEqual(remote_main, self.main)

    def test_deleting_experiments_does_not_hide_their_history(self):
        self.git('switch', '-c', 'experimental')
        self.add_experiment()
        self.git('commit', '-m', 'Experiment')
        self.git('rm', 'experimentals/example.txt')
        self.git('commit', '-m', 'Delete experiment')
        self.git('push', 'origin', 'experimental:main', blocked=True)
