#!/usr/bin/env python3
import argparse
from pathlib import Path
import hashlib
import json

def sha1sum(file_path):
    sha1 = hashlib.sha1()
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):  # Read the file in chunks (8192 bytes at a time)
            sha1.update(chunk)
    return sha1.hexdigest()

def index(dir):
    path = Path(dir)
    dict = {}
    for file_path in path.rglob('*'):  # '*' matches all files and directories
        if file_path.is_file():
            checksum = sha1sum(file_path)
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

DEBUG = False

def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

def compare(current, old):
    current_paths_to_sha = {}
    for sha in current:
        for path in current[sha]:
            current_paths_to_sha[path] = sha

    debug_print("Iterating through old index.")
    for sha in old:
        debug_print(f"Found SHA {sha} with {len(old[sha])} filepaths")
        if sha in current:
            for path in old[sha]:
                if path not in current[sha] and path not in current_paths_to_sha:
                    print(f"File {path} was in the index, but is now missing.")
                elif path not in current[sha] and path in current_paths_to_sha:
                    print(f"File {path} changed its contents.")
        else:
            for path in old[sha]:
                if path in current_paths_to_sha:
                    print(f"File {path} changed its contents.")
                else:
                    print(f"File {path} was in the index, but is now missing.")

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


