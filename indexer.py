#!/usr/bin/env python3
import argparse
from pathlib import Path
import hashlib
import json

def sha1sum(file_path):
    sha1 = hashlib.sha1()
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):  # Read the file in chunks (8192 bytes at a time)
                sha1.update(chunk)
    except PermissionError as e:
        print(f"Skipping inaccessible file {file_path} due to missing permissions. Error: {e}")
        return None
    except Exception as e:
        print(f"Skipping inaccessible file {file_path} due to: {e}")
        return None
    return sha1.hexdigest()

def index(dir):
    path = Path(dir)
    dict = {}
    for file_path in path.rglob('*'):  # '*' matches all files and directories
        if file_path.is_file():
            checksum = sha1sum(file_path)
            if checksum is None:
                continue
            if checksum in dict:
                dict[checksum].append(str(file_path))
            else:
                dict[checksum] = [str(file_path)]
    return dict

def serialize_to_json(data, file_path):
    path = Path(file_path)

    # Check if the file exists
    if path.exists():
        confirm = input(f"File {file_path} already exists. Overwrite? (y/n): ")
        if confirm.lower() != 'y':
            print("Operation cancelled.")
            return

    # Write the dictionary to a JSON file
    with path.open('w') as file:
        json.dump(data, file, indent=4)
        print(f"Index successfully written to {file_path}")

def deserialize_from_json(file_path):
    path = Path(file_path)

    # Check if the file exists before attempting to read
    if not path.exists():
        print(f"File {file_path} does not exist.")
        return None

    # Read the JSON file and return the dictionary
    with path.open('r') as file:
        return json.load(file)

DEBUG = True

def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

# Return arrays current_stripped, old_stripped such that
# every SHA:filename pair present in both current and old
# is removed.
def strip_unchanged(current, old):
    old_stripped = {}
    current_stripped = {}
    for sha in old:
        new_sha = [x for x in old[sha] if sha not in current or x not in current[sha]]
        if len(new_sha) != 0:
            old_stripped[sha] = new_sha
    for sha in current:
        new_sha = [x for x in current[sha] if sha not in old or x not in old[sha]]
        if len(new_sha) != 0:
            current_stripped[sha] = new_sha
    return current_stripped, old_stripped

# Strip easy cases of content change.
def strip_content_changes(current, old):
    old_stripped = {}
    current_stripped = {}
    # Dict of path -> [old sha, new sha]
    content_changes = {}
    current_paths_to_sha = {}
    for sha in current:
        for path in current[sha]:
            current_paths_to_sha[path] = sha
    for sha in old:
        for path in old[sha]:
            if path in current_paths_to_sha and sha != current_paths_to_sha[path]:
                content_changes[path] = [sha, current_paths_to_sha[path]]
    
    # Recreate indexes without pairs listed in content_changes.
    for sha in old:
        for path in old[sha]:
            if path not in content_changes:
                if sha in old_stripped:
                    old_stripped[sha].append(path)
                else:
                    old_stripped[sha] = [path]
    for sha in current:
        for path in current[sha]:
            if path not in content_changes:
                if sha in current_stripped:
                    current_stripped[sha].append(path)
                else:
                    current_stripped[sha] = [path]
    return current_stripped, old_stripped, content_changes

# Strip easy cases of moves/renames.
def strip_moves(current, old):
    old_stripped = {}
    current_stripped = {}
    # Dict of sha -> [[old path, new path], ...]
    moves = {}
    # Helper dict of sha -> [oldpath1, oldpath2...]
    skiplist_old = {}
    # Helper dict of sha -> [newpath1, newpath2...]
    skiplist_current = {}
    current_paths_to_sha = {}
    for sha in current:
        for path in current[sha]:
            current_paths_to_sha[path] = sha
    for sha in old:
        if sha in current:
            for i in range(min(len(old[sha]), len(current[sha]))):
                if sha not in moves:
                    moves[sha] = [[old[sha][i], current[sha][i]]]
                    skiplist_old[sha] = [old[sha][i]]
                    skiplist_current[sha] = [current[sha][i]]
                else:
                    moves[sha].append([old[sha][i], current[sha][i]])
                    skiplist_old[sha].append(old[sha][i])
                    skiplist_current[sha].append(current[sha][i])
    
    # Recreate indexes without pairs listed in content_changes.
    for sha in old:
        for path in old[sha]:
            if sha in skiplist_old and path in skiplist_old[sha]:
                continue
            if sha in old_stripped:
                old_stripped[sha].append(path)
            else:
                old_stripped[sha] = [path]
    for sha in current:
        for path in current[sha]:
            if sha in skiplist_current and path in skiplist_current[sha]:
                continue
            if sha in current_stripped:
                current_stripped[sha].append(path)
            else:
                current_stripped[sha] = [path]
    return current_stripped, old_stripped, moves

# Strip easy cases of removal. Assumption: content changes, moves are already removed.
def strip_removal(current, old):
    old_stripped = {}
    # Dict of sha -> [old paths]
    removals = {}
    for sha in old:
        if sha not in current:
            for path in old[sha]:
                if sha in removals:
                    removals[sha].append(path)
                else:
                    removals[sha] = [path]
    
    # Recreate indexes without pairs listed in content_changes.
    for sha in old:
        for path in old[sha]:
            if sha not in removals:
                if sha in old_stripped:
                    old_stripped[sha].append(path)
                else:
                    old_stripped[sha] = [path]
    return current, old_stripped, removals

# Strip easy cases of copies or new files. Assumption: content changes, moves, removals are already removed.
# old_orig contains old index before any changes.
def strip_copy_or_new(current, old, old_orig):
    new_stripped = {}
    old_stripped = {}
    # Dict of sha -> [new paths]
    new = {}
    # Dict of sha -> [old path, [new path1, new path2...]]
    copies = {}
    for sha in current:
        if sha not in old:
            # All paths in current[sha] are new or copies
            if sha in old_orig:
                # It's a copy. Append to the copies dict
                for path in current[sha]:
                    if sha in copies:
                        copies[sha][1].append(path)
                    else:
                        copies[sha] = [old_orig[sha][0], [path]]
            else:
                # It's a new file(s)
                new[sha] = current[sha]
        else:
            '''
            There's same SHA in both old and current. What can be the case?
            [f1, f2, f3] -> [f1, f2, f3, f4] <- f1, f2, f3 would get stripped in earlier step
            [f4] -> [d1/f5] <- that would get removed in "move" step
            [f1, f2] -> [f3, f4] <- that would also get removed in "move" step
            Cases:
             1) same length
             [f1] -> [f1] <- impossible because it would be stripped in "unchanged" step
             [f1] -> [f2] <- impossible because that would get removed in "move" step
             2) current index is longer; intersection is non-empty
             [f1] -> [f1, f2] <- impossible because "unchanged" step
             3) current index is longer; intersection is empty
             [f1] -> [f2, f3, f4, f5...] <- this would get flagged as move, causing old to go empty XXX [worth checking with a test case]
             4) old index is longer; intersection non-empty
             [f1, f2, f3...] -> [f1] <- impossible because "unchanged" step
             5) old index is longer; intersection empty
             [f2, f3, f4...] -> [f1] <- this would also get flagged as move causing current to go empty XXX
            '''
            print(f"This is a really unexpected case. There's same SHA in both old and current index. SHA {sha}, current[sha] {current[sha]}, old[sha] {old[sha]}")
            assert False

    # Recreate indexes without pairs listed in content_changes.
    # old index can be returned as-is, because:
    #   1. File that was copied is removed as unchanged
    #   2. File that's new resides only in current index
    current_stripped = {}
    for sha in current:
        for path in current[sha]:
            if sha in new and path in new[sha]:
                continue
            if sha in copies and path in copies[sha][1]:
                continue
            if sha in current_stripped:
                current_stripped[sha].append(path)
            else:
                current_stripped[sha] = [path]
    return current_stripped, old, copies, new

class ChangeDescription:
    def __init__(self):
        self.current_stripped = {}
        self.old_stripped = {}
        self.content_changes = {}
        self.moves = {}
        self.removals = {}
        self.copies = {}
        self.new = {}
    def __str__(self):
        return (
            f"ChangeDescription:\n"
            f"  current_stripped: {self.current_stripped}\n"
            f"  old_stripped: {self.old_stripped}\n"
            f"  content_changes: {self.content_changes}\n"
            f"  moves: {self.moves}\n"
            f"  removals: {self.removals}\n"
            f"  copies: {self.copies}\n"
            f"  new: {self.new}\n"
        )

def strip(current, old, debug=False):
    change_descr = ChangeDescription()
    change_descr.current_stripped, change_descr.old_stripped = strip_unchanged(current, old)
    if debug:
        print("Stripped unchanged.", change_descr)
    change_descr.current_stripped, change_descr.old_stripped, change_descr.content_changes = strip_content_changes(change_descr.current_stripped, change_descr.old_stripped)
    if debug:
        print("Stripped content changes.", change_descr)
    change_descr.current_stripped, change_descr.old_stripped, change_descr.moves = strip_moves(change_descr.current_stripped, change_descr.old_stripped)
    if debug:
        print("Stripped moves.", change_descr)
    change_descr.current_stripped, change_descr.old_stripped, change_descr.removals = strip_removal(change_descr.current_stripped, change_descr.old_stripped)
    if debug:
        print("Stripped removals.", change_descr)
    change_descr.current_stripped, change_descr.old_stripped, change_descr.copies, change_descr.new = strip_copy_or_new(change_descr.current_stripped, change_descr.old_stripped, old)
    if debug:
        print("Stripped copies and new.", change_descr)
    return change_descr

def compare(current, old):
    change_descr = strip(current, old)
    for path in change_descr.content_changes:
        print(f"File {path} changed its contents.")
    for sha in change_descr.moves:
        for old_path, new_path in change_descr.moves[sha]:
            print(f"File {old_path} moved to {new_path}.")
    for sha in change_descr.removals:
        for path in change_descr.removals[sha]:
            print(f"File {path} was in the index, but is now missing.")
    for sha in change_descr.new:
        for path in change_descr.new[sha]:
            print(f"File {path} is new.")
    for sha in change_descr.copies:
        oldpath = change_descr.copies[sha][0]
        newpaths = change_descr.copies[sha][1]
        for path in newpaths:
            print(f"File {oldpath} was copied to {path}.")

# def compare(current, old):
#     current_paths_to_sha = {}
#     for sha in current:
#         for path in current[sha]:
#             current_paths_to_sha[path] = sha
#     old_paths_to_sha = {}
#     for sha in old:
#         for path in old[sha]:
#             old_paths_to_sha[path] = sha
# 
#     debug_print("Iterating through old index.")
#     for sha in old:
#         debug_print(f"Found old SHA {sha} with {len(old[sha])} filepaths")
#         if sha in current:
#             for path in old[sha]:
#                 if path not in current[sha] and path not in current_paths_to_sha:
#                     print(f"File {path} was in the index, but is now missing.")
#                 elif path not in current[sha] and path in current_paths_to_sha:
#                     print(f"File {path} changed its contents.")
#         else:
#             for path in old[sha]:
#                 if path in current_paths_to_sha:
#                     print(f"File {path} changed its contents.")
#                 else:
#                     print(f"File {path} was in the index, but is now missing.")
#     
#     for sha in current:
#         debug_print(f"Found current SHA {sha} with {len(current[sha])} filepaths")
#         if sha in old:
#             if len(old[sha]) == len(current[sha]) and len(old[sha]) == 1:
#                 # One path for SHA in both current and new. Is it the same?
#                 if old[sha] != current[sha]:
#                     print(f"File {old[sha]} moved to {current[sha]}.")
#             elif old[sha].sort() == current[sha].sort():
#                 # More paths with the same SHA, but all duplicates stay where they were.
#                 pass
#             else:
#                 # Many paths with the same SHA. Current index is different than old.
#                 # Example:
#                 # old
#                 #   f1.txt a39a3ee5e6
#                 #   f2.txt a39a3ee5e6
#                 #   f3.txt d9310ab13e
#                 # new
#                 #   d1/f1.txt a39a3ee5e6
#                 #   d1/f2.txt a39a3ee5e6
#                 #   f3.txt d9310ab13e
#                 #   f4.txt a39a3ee5e6
#                 print(f"Duplicated file at paths {old[sha].sort()} is now at {current[sha].sort()}")
#         else:
#             # This is a new SHA. Either it's a new file, or it changed its contents.
#             for path in current[sha]:
#                 if path not in old_paths_to_sha:
#                     print(f"File {path} is new.")

def main():
    parser = argparse.ArgumentParser(description="Indexing your files, and validating if you've lost anything.")
    
    parser.add_argument("operation", choices=["index", "validate"],
                        help="Operation to perform: index")
    
    parser.add_argument("directory", type=str, help="Directory to index/validate")
    
    args = parser.parse_args()
    
    # Perform the operation
    if args.operation == "index":
        d = index(args.directory)
        serialize_to_json(d, args.directory + "/.index")
    elif args.operation =="validate":
        current = index(args.directory)
        old = deserialize_from_json(args.directory + "/.index")
        compare(current, old)


if __name__ == "__main__":
    main()
