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
    out = None

    # Check if the file exists before attempting to read
    if not path.exists():
        print(f"File {file_path} does not exist.")
        return None

    # Read the JSON file and return the dictionary
    try:
        with path.open('r') as file:
            out = json.load(file)
    except Exception as e:
        print("Can't open the file: {e}")
        return None
    
    if isinstance(out, dict):
        # This is an Indexer index, return it
        return out
    elif isinstance(out, list):
        return b2_listing_to_index(out)
    else:
        raise Exception("Unsupported format")

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
            # It may be an actual removal, but something else is also possible.
            # Consider input:
            # old: [sha1 -> f1, f2]
            # current [sha1 -> f1]
            # Over strip_unchanges, it becomes:
            # old: [sha1 -> f2]
            # current []
            # It's a "removal" but of a duplicate. 
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
    for sha in change_descr.moves:
        for old_path, new_path in change_descr.moves[sha]:
            print(f"File {old_path} moved to {new_path}.")
    for path in change_descr.content_changes:
        print(f"File {path} changed its contents.")
    for sha in change_descr.removals:
        for path in change_descr.removals[sha]:
            # This path is gone. However, it may be either a duplicate removed, or an actual removal.
            if sha in current:
                # Duplicate was removed
                if len(current[sha]) == 1:
                    print(f"Duplicated file {path} was removed. Its copy exists at {current[sha][0]}")
                else:
                    copies = ", ".join(current[sha])
                    print(f"Duplicated file {path} was removed. Its copies exist at {copies}")
            else:
                print(f"File {path} was removed.")
    for sha in change_descr.new:
        for path in change_descr.new[sha]:
            print(f"File {path} is new.")
    for sha in change_descr.copies:
        oldpath = change_descr.copies[sha][0]
        newpaths = change_descr.copies[sha][1]
        for path in newpaths:
            print(f"File {oldpath} was copied to {path}.")
    return change_descr

"""
B2 listing:
[
{
    "accountId": "632adbf08ef2",
    "action": "upload",
    "bucketId": "7623d20a9d2b0f90982e0f12",
    "contentMd5": "7941d80b9f9c2b40085dac94dc9ac570",
    "contentSha1": "6e63ed5da11cbe15588154a1148a866d3a4766ba",
    "contentType": "application/octet-stream",
    "fileId": "4_z7623d20a9d2b0f90982e0f12_f11301ed4954d7d4c_d20240919_m093201_c004_v0402027_t0037_u01726738321715",
    "fileInfo": {
        "src_last_modified_millis": "1726670499677"
    },
    "fileName": ".rcloneignore",
    "fileRetention": {
        "mode": null,
        "retainUntilTimestamp": null
    },
    "legalHold": null,
    "replicationStatus": null,
    "serverSideEncryption": {
        "mode": "none"
    },
    "size": 107,
    "uploadTimestamp": 1726738321715
}, ...]
Index:
{
    "f39cfff4d9da667b48d2ab66274f0b5e1e8cfe92": [
        "file3"
    ],
    "7fe70820e08a1aac0ef224d9c66ab66831cc4ab1": [
        "file2",
        "file1"
    ],
"""
def b2_listing_to_index(b2_listing):
    index = {}
    print(f"Converting b2 listing to an index...")
    count = 0
    for file in b2_listing:
        if "contentSha1" not in file:
            print("No contentSha1 in b2 listing:")
            print(file)
            continue
        if "fileName" not in file:
            print("No contentSha1 in b2 listing:")
            print(file)
            continue
        sha = file["contentSha1"]
        if sha == "none":
            try:
                sha = file["fileInfo"]["large_file_sha1"]
            except Exception as e:
                print(f"Failed to read SHA1 for {file['fileName']}: {e}")
                continue
        path = file["fileName"]
        if sha in index:
            index[sha].append(path)
        else:
            index[sha] = [path]
        count += 1
    print(f"Done, {count} entries added.")
    return index


global_current = None
global_old = None
change_descr = None
def main():
    parser = argparse.ArgumentParser(description="Indexing your files, and validating if you've lost anything.")
    subparsers = parser.add_subparsers(dest="operation", required=True, help="Operation to perform")

    # Subparser for the 'index' command
    index_parser = subparsers.add_parser("index", help="Index the files in the directory")
    index_parser.add_argument("directory", type=str, help="Directory to index")

    # Subparser for the 'validate' command
    validate_parser = subparsers.add_parser("validate", help="Validate the files in the directory")
    validate_parser.add_argument("directory", type=str, help="Directory to validate")
    validate_parser.add_argument("--target", type=str, 
                                    help="Use provided target index instead of creating one on the fly. Accepted: B2 listing, Indexer index")
    validate_parser.add_argument("--baseline", type=str, 
                                    help="Use provided baseline index instead of reading from .index. Accepted: B2 listing, Indexer index")

    args = parser.parse_args()

    # Perform the operation
    if args.operation == "index":
        d = index(args.directory)
        serialize_to_json(d, args.directory + "/.index")
    elif args.operation =="validate":
        if args.target:
            current = deserialize_from_json(args.target)
        else:
            current = index(args.directory)
        if args.baseline:
            old = deserialize_from_json(args.baseline)
        else:
            old = deserialize_from_json(args.directory + "/.index")
        global_current = current.copy()
        global_old = old.copy()
        print(len(current))
        print(len(global_current))
        change_descr = compare(current, old)


if __name__ == "__main__":
    main()
