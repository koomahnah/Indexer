#!/usr/bin/env python3
import argparse
from pathlib import Path
import hashlib
import numpy
import imagehash
from PIL import Image
import json

def is_image(filename):
    f = str(filename).lower()
    return f.endswith('.png') or f.endswith('.jpg') or \
        f.endswith('.jpeg') or f.endswith('.bmp') or \
        f.endswith('.gif') or f.endswith('.svg')

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

def ddhash(image, hash_size=8):
	# type: (Image.Image, int) -> ImageHash
	# resize(w, h), but numpy.array((h, w))
	if hash_size < 2:
		raise ValueError('Hash size must be greater than or equal to 2')

    # BILINEAR & 6 bits is pretty ok
	image = image.convert('L').resize((hash_size + 1, hash_size), Image.Resampling.HAMMING)
	pixels = numpy.asarray(image)
	# compute differences between columns
	diff = pixels[:, 1:] > pixels[:, :-1]
	return imagehash.ImageHash(diff)
 
"""
This function intends to hash files such that hashing is immune to multiples
of 90 degree rotation. Ie. you rotate the file 90deg or more, hash stays the same.
It could be done by computing 4 hashes: 0deg, 90deg, ... 270deg and sorting. But two
hashings will be enough supposing we always start from the vertical orientation.
"""
def dhash(file_path):
    f = Image.open(file_path)
    rotation = 0
    hashes = [0, 0]
    if f.width > f.height:
        # Always rotate to vertical
        rotation = 90
    hashes[0] = str(ddhash(f.rotate(rotation, expand=True), hash_size=5))
    hashes[1] = str(ddhash(f.rotate(rotation + 180, expand=True), hash_size=5))
    hashes.sort()
    return "".join(hashes)

def index(dir, old_reversed, old_timestamps, image_mode):
    path = Path(dir)
    dict = {}
    for file_path in path.rglob('*'):  # '*' matches all files and directories
        if file_path.is_file():
            current_mod_time = file_path.stat().st_mtime
            if old_timestamps and old_reversed and str(file_path) in old_timestamps and current_mod_time == old_timestamps[str(file_path)]:
                checksum = old_reversed[str(file_path)]
            else:
                if image_mode and is_image(file_path):
                    try:
                        checksum = dhash(file_path)
                    except Exception as e:
                        print(f"Failed to compute image hash for {file_path}: {e}. \n Falling back to SHA.")
                        checksum = sha1sum(file_path)
                else:
                    checksum = sha1sum(file_path)

            if checksum is None:
                continue
            if checksum in dict:
                dict[checksum].append(str(file_path))
            else:
                dict[checksum] = [str(file_path)]
    return dict

# Path -> sha
def reverse_index(index):
    reverse = {}
    for sha in index:
        for path in index[sha]:
            reverse[path] = sha
    return reverse

def stamp_times(reverse_index):
    timestamps = {}
    for path in reverse_index:
        path2 = Path(path)
        current_mod_time = path2.stat().st_mtime
        timestamps[path] = current_mod_time
    return timestamps


def serialize_to_json(data, file_path, prompt=True):
    path = Path(file_path)

    # Check if the file exists
    if path.exists() and prompt:
        confirm = input(f"File {file_path} already exists. Overwrite? (y/n): ")
        if confirm.lower() != 'y':
            print("Operation cancelled.")
            return

    # Write the dictionary to a JSON file
    with path.open('w') as file:
        json.dump(data, file, indent=4)
        print(f"INFO: Index successfully written to {file_path}.")

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

def serialize_all(index, reverse_index, timestamp_index, dir, image_mode, prompt=True):
    sufix = ""
    if image_mode:
        sufix = "_dhash"
    if index:
        serialize_to_json(index, dir + "/.index" + sufix, prompt)
    if reverse_index:
        serialize_to_json(reverse_index, dir + "/.index_reversed" + sufix, prompt)
    if timestamp_index:
        serialize_to_json(timestamp_index, dir + "/.index_timestamps" + sufix, prompt)

def deserialize_all(dir, image_mode):
    sufix = ""
    if image_mode:
        sufix = "_dhash"
    index = deserialize_from_json(dir + "/.index" + sufix)
    reverse_index = deserialize_from_json(dir + "/.index_reversed" + sufix)
    timestamp_index = deserialize_from_json(dir + "/.index_timestamps" + sufix)
    return index, reverse_index, timestamp_index


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
    current_paths_to_sha = reverse_index(current)
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
    current_paths_to_sha = reverse_index(current)
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

def list_duplicates(current):
    for sha in current:
        if len(current[sha]) > 1:
            print(f"Duplicates: {', '.join(current[sha])}")

change_descr = None
def main():
    parser = argparse.ArgumentParser(description="Indexing your files, and validating if you've lost anything.")
    subparsers = parser.add_subparsers(dest="operation", required=True, help="Operation to perform")

    # Subparser for the 'index' command
    index_parser = subparsers.add_parser("index", help="Index the files in the directory")
    index_parser.add_argument("directory", type=str, help="Directory to index")
    index_parser.add_argument("--image-mode", action='store_true',
                                    help="Use hashing dedicated for images. This treats similar images as same files.")

    # Subparser for the 'duplicate-info'
    duplicate_parser = subparsers.add_parser("duplicate-info", help="List info about duplicates in current tree")
    duplicate_parser.add_argument("directory", type=str, help="Directory to list duplicates in")
    duplicate_parser.add_argument("--image-mode", action='store_true',
                                    help="Use hashing dedicated for images. This treats similar images as same files.")

    # Subparser for the 'validate' command
    validate_parser = subparsers.add_parser("validate", help="Validate the files in the directory")
    validate_parser.add_argument("directory", type=str, help="Directory to validate")
    validate_parser.add_argument("--target", type=str, 
                                    help="Use provided target index instead of creating one on the fly. Accepted: B2 listing, Indexer index")
    validate_parser.add_argument("--baseline", type=str, 
                                    help="Use provided baseline index instead of reading from .index. Accepted: B2 listing, Indexer index")
    validate_parser.add_argument("--script", action='store_true',
                                    help="Never prompt y/n and go with default. Useful for scripts.")
    validate_parser.add_argument("--image-mode", action='store_true',
                                    help="Use hashing dedicated for images. This treats similar images as same files.")

    args = parser.parse_args()

    # Perform the operation
    if args.operation == "index":
        d = index(args.directory, None, None, args.image_mode)
        r = reverse_index(d)
        t = stamp_times(r)
        serialize_all(d, r, t, args.directory, args.image_mode)
    elif args.operation =="validate":
        if args.baseline:
            old = deserialize_from_json(args.baseline)
            old_reversed = deserialize_from_json(args.baseline + "_reversed")
            old_timestamps = deserialize_from_json(args.baseline + "_timestamps")
        else:
            old, old_reversed, old_timestamps = deserialize_all(args.directory, args.image_mode);
        if args.target:
            current = deserialize_from_json(args.target)
        else:
            current = index(args.directory, old_reversed, old_timestamps, args.image_mode)
        change_descr = compare(current, old)
        if not args.target and not args.script:
            print("Overwrite old index? [y/N] ", end='')
            choice = input().lower()
            if choice == "y":
                serialize_all(current, old_reversed, old_timestamps, args.directory, args.image_mode, prompt=False)
            else:
                print("Ok, not doing anything.")
    elif args.operation == "duplicate-info":
        old_reversed = deserialize_from_json(args.directory + "/.index_reversed")
        old_timestamps = deserialize_from_json(args.directory + "/.index_timestamps")
        if old_reversed:
            print(f"INFO: Loaded reverse index with {len(old_reversed)} entries.")
        else:
            print("INFO: Reverse index missing.")
        if old_timestamps:
            print(f"INFO: Loaded timestamps index with {len(old_timestamps)} entries.")
        else:
            print("INFO: timestamps index missing.")
        current = index(args.directory, old_reversed, old_timestamps, args.image_mode)
        list_duplicates(current)


if __name__ == "__main__":
    main()
