import unittest
import subprocess
from pathlib import Path
import tempfile

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
            ["python3", "indexer.py", "validate", str(self.temp_dir_path)],
            capture_output=True, text=True
        )

        print(result.stdout)
        # Check if the output is correct
        self.assertIn(f"File {str(file1)} changed its contents", result.stdout)
        for file in [file2, file3, file4, file5, file6]:
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
            ["python3", "indexer.py", "validate", str(self.temp_dir_path)],
            capture_output=True, text=True
        )

        print(result.stdout)
        # Check if the output is correct
        self.assertIn(f"File {str(file2)} was in the index, but is now missing", result.stdout)
        self.assertIn(f"File {str(file3)} was in the index, but is now missing", result.stdout)
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
            ["python3", "indexer.py", "validate", str(self.temp_dir_path)],
            capture_output=True, text=True
        )

        print(result.stdout)
        # Check if the output is correct
        for file in files_to_unlink:
            self.assertIn(f"File {str(file)} was in the index, but is now missing", result.stdout)
        for file in files_to_change:
            self.assertIn(f"File {str(file)} changed its contents", result.stdout)
        for file in other_files:
            self.assertNotIn(f"{str(file)} ", result.stdout)
        self.assertEqual(result.returncode, 0)
if __name__ == "__main__":
    unittest.main()
