import unittest
import subprocess
from pathlib import Path
import tempfile
from indexer import strip_content_changes, strip_moves, strip_unchanged, strip_removal, strip_copy_or_new, strip, ChangeDescription

class TestRemovalIsolated(unittest.TestCase):
    def test_removal_simple(self):
        current = {}
        old = {'bcd': ['f3']}
        current, old, removals = strip_removal(current, old)
        self.assertEqual(current, {})
        self.assertEqual(old, {})
        self.assertEqual(removals, {'bcd': ['f3']})
    def test_removal_multiple(self):
        current = {'eee': ['f7']}
        old = {'bcd': ['f3', 'f4'], 'afd': ['f5']}
        current, old, removals = strip_removal(current, old)
        self.assertEqual(current, {'eee': ['f7']})
        self.assertEqual(old, {})
        self.assertEqual(removals, {'bcd': ['f3', 'f4'], 'afd': ['f5']})
    def test_removal_multiple_spurious(self):
        current = {'eee': ['f7']}
        old = {'bcd': ['f3', 'f4'], 'afd': ['f5'], 'eee': ['f8']}
        current, old, removals = strip_removal(current, old)
        self.assertEqual(current, {'eee': ['f7']})
        self.assertEqual(old, {'eee': ['f8']})
        self.assertEqual(removals, {'bcd': ['f3', 'f4'], 'afd': ['f5']})
class TestMoveIsolated(unittest.TestCase):
    def test_move_simple(self):
        current = {'abc': ['f2']}
        old = {'abc': ['f3']}
        current, old, moves = strip_moves(current, old)
        self.assertEqual(current, {})
        self.assertEqual(old, {})
        self.assertEqual(moves, {'abc': [['f3', 'f2']]})
    def test_move_multiple(self):
        current = {'abc': ['f3', 'f4']}
        old = {'abc': ['f1', 'f2']}
        current, old, moves = strip_moves(current, old)
        self.assertEqual(current, {})
        self.assertEqual(old, {})
        self.assertIn('abc', moves)
        self.assertTrue(moves == {'abc': [['f1', 'f3'], ['f2', 'f4']]} or moves == {'abc': [['f1', 'f4'], ['f2', 'f3']]})
    def test_move_multiple_spurious(self):
        current = {'abc': ['f3', 'f4'], 'eef': ['f8']}
        old = {'abc': ['f1', 'f2'], 'eee': ['f4']}
        current, old, moves = strip_moves(current, old)
        self.assertEqual(current, {'eef': ['f8']})
        self.assertEqual(old, {'eee': ['f4']})
        self.assertIn('abc', moves)
        self.assertTrue(moves == {'abc': [['f1', 'f3'], ['f2', 'f4']]} or moves == {'abc': [['f1', 'f4'], ['f2', 'f3']]})
    def test_move_spurious(self):
        current = {'abc': ['f2'], 'efd': ['f4', 'f1']}
        old = {'abc': ['f3'], 'eee': ['f4']}
        current, old, moves = strip_moves(current, old)
        self.assertEqual(current, {'efd': ['f4', 'f1']})
        self.assertEqual(old, {'eee': ['f4']})
        self.assertEqual(moves, {'abc': [['f3', 'f2']]})
    def test_move_intact(self):
        a = {'abc': ['f1', 'f4']}
        b = {'dfb': ['f2'], 'aaa': ['f5']}
        c, d, f = strip_moves(a,b)
        self.assertEqual(a, c)
        self.assertEqual(b, d)
        self.assertEqual(len(f), 0)
class TestContentChangeIsolated(unittest.TestCase):
    def test_content_change_simple(self):
        a = {'abc': ['f2']}
        b = {'dfb': ['f2']}
        a, b, c = strip_content_changes(a,b)
        self.assertEqual(len(a), 0)
        self.assertEqual(len(b), 0)
        self.assertIn('f2', c)
        self.assertIn('abc', c['f2'])
        self.assertIn('dfb', c['f2'])
    def test_content_change_spurious(self):
        a = {'abc': ['f2', 'f4']}
        b = {'dfb': ['f2'], 'aaa': ['f5']}
        a, b, c = strip_content_changes(a,b)
        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 1)
        self.assertIn('abc', a)
        self.assertIn('f4', a['abc'])
        self.assertIn('aaa', b)
        self.assertIn('f5', b['aaa'])
        self.assertIn('f2', c)
        self.assertIn('abc', c['f2'])
        self.assertIn('dfb', c['f2'])
    def test_content_change_intact(self):
        a = {'abc': ['f1', 'f4']}
        b = {'dfb': ['f2'], 'aaa': ['f5']}
        c, d, f = strip_content_changes(a,b)
        self.assertEqual(a, c)
        self.assertEqual(b, d)
        self.assertEqual(len(f), 0)
class TestCopyOrNewIsolated(unittest.TestCase):
    def test_new_simple(self):
        current = {'bcd': ['f3']}
        old = {}
        current, old, copies, new = strip_copy_or_new(current, old, old)
        self.assertEqual(current, {})
        self.assertEqual(old, {})
        self.assertEqual(new, {'bcd': ['f3']})
        self.assertEqual(copies, {})
    def test_copy_simple(self):
        current = {'bcd': ['f1_copy']}
        old = {}
        old_prestrip = {'bcd': ['f1']}
        current, old, copies, new = strip_copy_or_new(current, old, old_prestrip)
        self.assertEqual(current, {})
        self.assertEqual(old, {})
        self.assertEqual(new, {})
        self.assertEqual(copies, {'bcd': ['f1', ['f1_copy']]})
    def test_copy_multiple(self):
        current = {'bcd': ['f1_copy', 'f1_copy2', 'f1_copy3'], 'eee': ['f2_copy', 'f3_copy']}
        old = {}
        old_prestrip = {'bcd': ['f1'], 'eee': ['f2', 'f3']}
        current, old, copies, new = strip_copy_or_new(current, old, old_prestrip)
        self.assertEqual(current, {})
        self.assertEqual(old, {})
        self.assertEqual(new, {})
        self.assertEqual(copies, {'bcd': ['f1', ['f1_copy', 'f1_copy2', 'f1_copy3']], 'eee': ['f2', ['f2_copy', 'f3_copy']]})
    def test_new_multiple(self):
        current = {'bcd': ['f3', 'd1/f3'], 'bababa': ['bababafile']}
        old = {}
        current, old, copies, new = strip_copy_or_new(current, old, old)
        self.assertEqual(current, {})
        self.assertEqual(old, {})
        self.assertEqual(new, {'bcd': ['f3', 'd1/f3'], 'bababa': ['bababafile']})
        self.assertEqual(copies, {})
    def test_new_and_copy(self):
        current = {'eee': ['f1_copy'], 'bcd': ['f3']}
        old = {}
        old_prestrip = {'eee': ['f1']}
        current, old, copies, new = strip_copy_or_new(current, old, old_prestrip)
        self.assertEqual(current, {})
        self.assertEqual(old, {})
        self.assertEqual(new, {'bcd': ['f3']})
        self.assertEqual(copies, {'eee': ['f1', ['f1_copy']]})
    def test_new_and_copy_multiple(self):
        current = {'tdsfdfsd': ['ft', 'd1/f3'], 'bababa': ['bababafile'], 'bcd': ['f1_copy', 'f1_copy2', 'f1_copy3'], 'eee': ['f2_copy', 'f3_copy']}
        old = {}
        old_prestrip = {'bcd': ['f1'], 'eee': ['f2', 'f3']}
        current, old, copies, new = strip_copy_or_new(current, old, old_prestrip)
        self.assertEqual(current, {})
        self.assertEqual(old, {})
        self.assertEqual(new, {'tdsfdfsd': ['ft', 'd1/f3'], 'bababa': ['bababafile']})
        self.assertEqual(copies, {'bcd': ['f1', ['f1_copy', 'f1_copy2', 'f1_copy3']], 'eee': ['f2', ['f2_copy', 'f3_copy']]})
class TestFullStrip(unittest.TestCase):
    def test_fullstrip_simple(self):
        current = {'bcd': ['f3'], 'sha1': ['d1/f1'], 'sha3': ['f2'], 'sha4': ['f4', 'f5', 'f6']}
        old = {'sha1': ['f1'], 'sha2': ['f2'], 'sha4': ['f4', 'f5'], 'sha5': ['f7']}
        change_descr = strip(current, old)
        self.assertEqual(change_descr.current_stripped, {})
        self.assertEqual(change_descr.old_stripped, {})
        self.assertEqual(change_descr.new, {'bcd': ['f3']})
        self.assertEqual(change_descr.removals, {'sha5': ['f7']})
        self.assertEqual(change_descr.copies, {'sha4': ['f4', ['f6']]})
        self.assertEqual(change_descr.moves, {'sha1': [['f1', 'd1/f1']]})
        self.assertEqual(change_descr.content_changes, {'f2': ['sha2', 'sha3']})
    def test_fullstrip_move_and_delete(self):
        current = {'bcd': ['f3'], 'sha1': ['d1/f1'], 'sha3': ['f2'], 'sha4': ['f4', 'f5', 'f6']}
        old = {'sha1': ['f1', 'f11'], 'sha2': ['f2'], 'sha4': ['f4', 'f5'], 'sha5': ['f7']}
        change_descr = strip(current, old)
        self.assertEqual(change_descr.current_stripped, {})
        self.assertEqual(change_descr.old_stripped, {})
        self.assertEqual(change_descr.new, {'bcd': ['f3']})
#        self.assertIn('sha5', change_descr.removals, {'sha5': ['f7'], 'sha1': ['f11']})
        self.assertIn('sha5', change_descr.removals)
        self.assertIn('f7', change_descr.removals['sha5'])
        self.assertIn('sha1', change_descr.removals)
        self.assertIn('f11', change_descr.removals['sha1'])
        self.assertEqual(change_descr.copies, {'sha4': ['f4', ['f6']]})
        self.assertEqual(change_descr.moves, {'sha1': [['f1', 'd1/f1']]})
        self.assertEqual(change_descr.content_changes, {'f2': ['sha2', 'sha3']})
    def test_fullstrip_remove_duplicate(self):
        old = {'sha1': ['f1', 'f11']}
        current = {'sha1': ['f1']}
        change_descr = strip(current, old)
        self.assertEqual(change_descr.current_stripped, {})
        self.assertEqual(change_descr.old_stripped, {})
        self.assertEqual(change_descr.new, {})
#        self.assertIn('sha5', change_descr.removals, {'sha5': ['f7'], 'sha1': ['f11']})
        self.assertIn('sha1', change_descr.removals)
        self.assertIn('f11', change_descr.removals['sha1'])
        self.assertEqual(change_descr.copies, {})
        self.assertEqual(change_descr.moves, {})
        self.assertEqual(change_descr.content_changes, {})
class TestContentChange(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_dir2 = tempfile.TemporaryDirectory(dir=self.temp_dir.name)
        self.temp_dir3 = tempfile.TemporaryDirectory(dir=self.temp_dir.name)
        self.temp_dir_path = Path(self.temp_dir.name)
    def tearDown(self):
        self.temp_dir.cleanup()
    def test_process_file(self):
        # temp_dir/
        #   file1
        #   file2
        #   temp_dir2/
        #       file3
        #       file4
        #   temp_dir3/
        #       file3
        #       file4
        file1 = Path(self.temp_dir.name) / "file1"
        file2 = Path(self.temp_dir.name) / "file2"
        file3 = Path(self.temp_dir2.name) / "file3"
        file4 = Path(self.temp_dir2.name) / "file4"
        file5 = Path(self.temp_dir3.name) / "file3"
        file6 = Path(self.temp_dir3.name) / "file4"
        file1.write_text("hello world")
        file2.write_text("test test")
        file3.write_text("test")
        file4.write_text("test"*4096*4096)
        file5.write_text("tst"*4096*4096)
        file6.write_text("tst"*4096*4096)

        result = subprocess.run(
            ["python3", "indexer.py", "index", str(self.temp_dir_path)],
            capture_output=True, text=True
        )
        
        file1.write_text("hhhhello world")

        result = subprocess.run(
            ["python3", "indexer.py", "validate", str(self.temp_dir_path), "--script"],
            capture_output=True, text=True
        )

        print(result.stdout)
        # Check if the output is correct
        self.assertIn(f"File {str(file1)} changed its contents", result.stdout)
        for file in [file2, file3, file4, file5, file6]:
            self.assertNotIn(f"{str(file)}", result.stdout)
        self.assertEqual(result.returncode, 0)
class TestDuplicateRemoval(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_dir2 = tempfile.TemporaryDirectory(dir=self.temp_dir.name)
        self.temp_dir3 = tempfile.TemporaryDirectory(dir=self.temp_dir.name)
        self.temp_dir_path = Path(self.temp_dir.name)
    def tearDown(self):
        self.temp_dir.cleanup()
    def test_process_file(self):
        # temp_dir/
        #   file1
        #   file2
        #   temp_dir2/
        #       file3
        #       file4
        #   temp_dir3/
        #       file3
        #       file4
        file1 = Path(self.temp_dir.name) / "file1"
        file2 = Path(self.temp_dir.name) / "file2"
        file3 = Path(self.temp_dir2.name) / "file3"
        file4 = Path(self.temp_dir2.name) / "file4"
        file5 = Path(self.temp_dir3.name) / "file3"
        file6 = Path(self.temp_dir3.name) / "file4"
        file1.write_text("hello world")
        file2.write_text("test test")
        file3.write_text("test")
        file4.write_text("test") # Duplicate of file3
        file5.write_text("tst"*4096*4096)
        file6.write_text("tst"*4096*4096)

        result = subprocess.run(
            ["python3", "indexer.py", "index", str(self.temp_dir_path)],
            capture_output=True, text=True
        )
        
        file4.unlink()

        result = subprocess.run(
            ["python3", "indexer.py", "validate", str(self.temp_dir_path), "--script"],
            capture_output=True, text=True
        )

        print(result.stdout)
        # Check if the output is correct
        self.assertIn(f"Duplicated file {str(file4)} was removed. Its copy exists at {str(file3)}", result.stdout)
        for file in [file1, file2, file5, file6]:
            self.assertNotIn(f"{str(file)}", result.stdout)
        self.assertEqual(result.returncode, 0)

class TestContentAndRemoveNestedDirs(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_dir2 = tempfile.TemporaryDirectory(dir=self.temp_dir.name)
        self.temp_dir3 = tempfile.TemporaryDirectory(dir=self.temp_dir.name)
        self.temp_dir_path = Path(self.temp_dir.name)
    def tearDown(self):
        self.temp_dir.cleanup()
    def test_process_file(self):
        file1 = Path(self.temp_dir.name) / "file1"
        file2 = Path(self.temp_dir.name) / "file2"
        file3 = Path(self.temp_dir2.name) / "file3"
        file4 = Path(self.temp_dir2.name) / "file4"
        file5 = Path(self.temp_dir3.name) / "file3"
        file6 = Path(self.temp_dir3.name) / "file4"
        file1.write_text("hello world")
        file2.write_text("test test")
        file3.write_text("test")
        file4.write_text("test"*4096*4096)
        file5.write_text("tst"*4096*4096)
        file6.write_text("tst"*4096*4096)

        result = subprocess.run(
            ["python3", "indexer.py", "index", str(self.temp_dir_path)],
            capture_output=True, text=True
        )
        
        file2.unlink()
        file3.unlink()
        file4.write_text("t")

        result = subprocess.run(
            ["python3", "indexer.py", "validate", str(self.temp_dir_path), "--script"],
            capture_output=True, text=True
        )

        print(result.stdout)
        # Check if the output is correct
        self.assertIn(f"File {str(file2)} was removed", result.stdout)
        self.assertIn(f"File {str(file3)} was removed", result.stdout)
        self.assertIn(f"File {str(file4)} changed its contents", result.stdout)
        for file in [file1, file5, file6]:
            self.assertNotIn(f"{str(file)}", result.stdout)
        self.assertEqual(result.returncode, 0)

class TestContentAndRemoveNestedDirsLarge(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.nested_dirs_lv1 = [tempfile.TemporaryDirectory(dir=self.temp_dir.name) for i in range(100)]
        self.nested_dirs_lv2 = [tempfile.TemporaryDirectory(dir=nested_dir.name) for nested_dir in self.nested_dirs_lv1]
        self.temp_dir_path = Path(self.temp_dir.name)
    def tearDown(self):
        self.temp_dir.cleanup()
    def test_process_file(self):
        files_to_unlink = []
        files_to_change = []
        other_files = []
        for i in range(0,100):
            file = Path(self.temp_dir.name) / f"file{i}"
            file.write_text(f"test{i}"*(i+1))
            if i % 7 == 0:
                files_to_unlink.append(file)
            elif i % 8 == 0:
                files_to_change.append(file)
            else:
                other_files.append(file)
        for i in range(0,100):
            file = Path(self.nested_dirs_lv1[i].name) / f"file{i}"
            file.write_text(f"test{i}"*(i+1))
            if i % 7 == 0:
                files_to_unlink.append(file)
            elif i % 8 == 0:
                files_to_change.append(file)
            else:
                other_files.append(file)
        for i in range(0,100):
            file = Path(self.nested_dirs_lv2[i].name) / f"file{i}"
            file.write_text(f"test{i}"*(i+1))
            if i % 7 == 0:
                files_to_unlink.append(file)
            elif i % 8 == 0:
                files_to_change.append(file)
            else:
                other_files.append(file)

        result = subprocess.run(
            ["python3", "indexer.py", "index", str(self.temp_dir_path)],
            capture_output=True, text=True
        )
        
        for file in files_to_unlink:
            file.unlink()
        for file in files_to_change:
            file.write_text("overwritten")

        result = subprocess.run(
            ["python3", "indexer.py", "validate", str(self.temp_dir_path), "--script"],
            capture_output=True, text=True
        )

        print(result.stdout)
        # Check if the output is correct
        for file in files_to_unlink:
            self.assertIn(f"File {str(file)} was removed", result.stdout)
        for file in files_to_change:
            self.assertIn(f"File {str(file)} changed its contents", result.stdout)
        for file in other_files:
            self.assertNotIn(f"{str(file)} ", result.stdout)
        self.assertEqual(result.returncode, 0)
if __name__ == "__main__":
    unittest.main()
