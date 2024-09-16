import os
from pathlib import Path
import re
import sys
import shutil
import subprocess
import logging

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    filename='test_extraction.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

import re
from collections import defaultdict
from typing import List, Tuple, Dict, Union

# Define types for clarity
SExpr = Union[str, List['SExpr']]

def tokenize(s: str) -> List[str]:
    """
    Tokenize the input string into a list of tokens for S-expression parsing.
    """
    # Remove comments and unnecessary whitespaces
    s = re.sub(r";;.*", "", s)  # Remove comments starting with ;;
    s = re.sub(r'\s+', ' ', s)  # Replace multiple whitespaces with single space
    tokens = re.findall(r'\(|\)|[^\s()]+', s)
    return tokens

def parse_sexpr(tokens: List[str]) -> SExpr:
    """
    Parse tokens into a nested S-expression.
    """
    if not tokens:
        raise SyntaxError("Unexpected EOF while reading")
    
    token = tokens.pop(0)
    if token == '(':
        L = []
        while tokens[0] != ')':
            L.append(parse_sexpr(tokens))
            if not tokens:
                raise SyntaxError("Unexpected EOF while reading")
        tokens.pop(0)  # Remove ')'
        return L
    elif token == ')':
        raise SyntaxError("Unexpected )")
    else:
        return token

def parse_mse_content(content: str) -> List[SExpr]:
    """
    Parse the entire MSE file content into a list of S-expressions.
    """
    tokens = tokenize(content)
    sexprs = []
    while tokens:
        sexprs.append(parse_sexpr(tokens))
    return sexprs

def extract_entries(sexprs: List[SExpr]) -> List[SExpr]:
    """
    Extract top-level SOMIX entries from the parsed S-expressions.
    """
    entries = []
    for expr in sexprs:
        if isinstance(expr, list):
            for item in expr:
                if isinstance(item, list) and len(item) > 0 and item[0].startswith("SOMIX."):
                    entries.append(item)
    return entries

def normalize_ids(entries: List[SExpr]) -> Tuple[List[SExpr], Dict[str, str]]:
    """
    Normalize numeric IDs by replacing them with consistent identifiers.
    Returns the updated entries and a mapping from original IDs to new identifiers.
    """
    id_map = {}
    unique_names = {}
    normalized_entries = []

    # First pass: Assign new identifiers based on uniqueName or other unique attribute
    for entry in entries:
        if entry[0] in {"SOMIX.Grouping", "SOMIX.Code", "SOMIX.Data"}:
            # Find uniqueName
            unique_name = ""
            for attr in entry[1:]:
                if isinstance(attr, list) and attr[0] == "uniqueName":
                    unique_name = attr[1].strip("'")
                    break
            if not unique_name:
                raise ValueError(f"Entry {entry} lacks a uniqueName attribute.")
            unique_names[unique_name] = None  # Initialize
    # Assign consistent identifiers
    for idx, unique_name in enumerate(sorted(unique_names.keys()), start=1):
        id_map[str(idx)] = unique_name  # Map numeric ID to uniqueName

    # Second pass: Replace IDs in entries
    for entry in entries:
        if entry[0] in {"SOMIX.Grouping", "SOMIX.Code", "SOMIX.Data"}:
            # Replace 'id' with uniqueName
            new_entry = []
            for attr in entry:
                if isinstance(attr, list) and attr[0] == "id":
                    original_id = attr[1]
                    if original_id not in id_map:
                        raise ValueError(f"Unknown id reference: {original_id}")
                    # Replace id with uniqueName
                    # We skip adding 'id' to the new_entry as per requirement
                else:
                    new_entry.append(attr)
            normalized_entries.append(new_entry)
        else:
            # Relations will be processed later
            normalized_entries.append(entry)

    return normalized_entries, id_map

def replace_refs(entries: List[SExpr], id_map: Dict[str, str]) -> List[str]:
    """
    Replace 'ref' IDs in relations with the corresponding uniqueNames and format entries.
    Returns a list of formatted strings.
    """
    formatted_entries = []
    object_names = {}  # Map from original ID to uniqueName

    # First, map original IDs to uniqueNames
    for entry in entries:
        if entry[0] in {"SOMIX.Grouping", "SOMIX.Code", "SOMIX.Data"}:
            unique_name = ""
            for attr in entry[1:]:
                if isinstance(attr, list) and attr[0] == "uniqueName":
                    unique_name = attr[1].strip("'")
                    break
            object_names[unique_name] = unique_name  # Using uniqueName as identifier

    # Now process each entry
    for entry in entries:
        if not isinstance(entry, list) or len(entry) == 0:
            continue
        entry_type = entry[0]
        if entry_type in {"SOMIX.Grouping", "SOMIX.Code", "SOMIX.Data"}:
            # Coding objects
            attrs = {}
            for attr in entry[1:]:
                if isinstance(attr, list) and len(attr) == 2:
                    key = attr[0]
                    value = attr[1].strip("'")
                    attrs[key] = value
            # Remove 'id' as per requirement
            attrs.pop("id", None)
            # Sort attributes alphabetically
            sorted_attrs = sorted(attrs.items())
            # Format as "SOMIX.Type(attr1:value1, attr2:value2, ...)"
            attr_str = ', '.join(f"{k}:{v}" for k, v in sorted_attrs)
            formatted = f"{entry_type}({attr_str})"
            formatted_entries.append(formatted)
        elif entry_type in {"SOMIX.ParentChild", "SOMIX.Call", "SOMIX.Access"}:
            # Relations
            attrs = {}
            for attr in entry[1:]:
                if isinstance(attr, list) and len(attr) >= 2:
                    key = attr[0]
                    if attr[1][0].startswith("(ref:"):
                        ref_id = re.findall(r'\(ref:\s*(\d+)\)', ' '.join(attr[1:]))
                        if ref_id:
                            ref_id = ref_id[0]
                            if ref_id in id_map:
                                ref_name = id_map[ref_id]
                                attrs[key] = ref_name
                            else:
                                raise ValueError(f"Unknown ref id: {ref_id}")
                        else:
                            raise ValueError(f"Invalid ref format in {attr}")
                    else:
                        # Handle boolean or other attributes
                        value = attr[1][1].strip("'")
                        attrs[key] = value
            # Sort attributes alphabetically
            sorted_attrs = sorted(attrs.items())
            # Format as "SOMIX.Type(attr1:value1, attr2:value2, ...)"
            attr_str = ', '.join(f"{k}:{v}" for k, v in sorted_attrs)
            formatted = f"{entry_type}({attr_str})"
            formatted_entries.append(formatted)
        else:
            # Unknown entry type
            continue
    return formatted_entries

def parse_mse_file(filepath: str) -> List[str]:
    """
    Parse an MSE file and return a list of formatted strings based on the specifications.
    """
    with open(filepath, 'r') as file:
        content = file.read()

    # Parse the S-expressions
    sexprs = parse_mse_content(content)

    # Extract SOMIX entries
    entries = extract_entries(sexprs)

    # Normalize IDs
    normalized_entries, id_map = normalize_ids(entries)

    # Replace refs and format entries
    formatted_entries = replace_refs(normalized_entries, id_map)

    # Sort the list to make comparison order-independent
    formatted_entries.sort()

    return formatted_entries

def compare_mse_files(file1: str, file2: str) -> Tuple[bool, List[str], List[str]]:
    """
    Compare two MSE files and return whether they are identical along with differences.
    Returns a tuple:
        (are_identical, differences_in_file1, differences_in_file2)
    """
    list1 = parse_mse_file(file1)
    list2 = parse_mse_file(file2)

    set1 = set(list1)
    set2 = set(list2)

    are_identical = set1 == set2
    differences_in_file1 = list(set1 - set2)
    differences_in_file2 = list(set2 - set1)

    return are_identical, differences_in_file1, differences_in_file2

def main():
    # Prepare test environment
    test_dir = os.path.join(os.getcwd(), 'test')
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir, exist_ok=True)
    os.makedirs(os.path.join(test_dir, 'subfolder'), exist_ok=True)

    try:
        # Create test files
        test1_path = os.path.join(test_dir, 'test1.py')
        test2_path = os.path.join(test_dir, 'subfolder', 'test2.py')

        with open(test1_path, 'w', encoding='utf-8') as f:
            f.write("""\
# test1.py remains unchanged
class ClassOne:
    class_variable = 100

    def __init__(self):
        self.instance_variable = 0
        ClassOne.class_variable += 1  # Fixed class variable increment

    def method_one(self):
        self.instance_variable += 1
        print("ClassOne method_one called")

def function_one():
    print("function_one called")

""")

        with open(test2_path, 'w', encoding='utf-8') as f:
            f.write("""\
# Updated test2.py with type annotations
from test1 import ClassOne, function_one

class ClassTwo:
    def method_two(self):
        obj = ClassOne()
        obj.method_one()
        function_one()
        print("ClassTwo method_two called")

    def method_three(self, my_obj: ClassOne):
        # To check that usage is also found when ClassOne is passed as an argument
        my_obj.method_one()

def function_two():
    obj = ClassOne()
    obj.method_one()
    function_one()
    print("function_two called")

""")

        # Write expected mse file
        expected_mse_path = os.path.join(test_dir, 'expected_output.mse')
        with open(expected_mse_path, 'w', encoding='utf-8') as f:
            f.write("""\
(
(SOMIX.Grouping (id: 1 )
  (name 'test1.py')
  (uniqueName 'test1')
  (technicalType 'PythonFile')
)
(SOMIX.Grouping (id: 2 )
  (name 'ClassOne')
  (uniqueName 'test1.ClassOne')
  (technicalType 'PythonClass')
)
(SOMIX.ParentChild
  (parent (ref: 1))
  (child (ref: 2))
  (isMain true)
)
(SOMIX.Data (id: 3 )
  (name 'class_variable')
  (uniqueName 'test1.ClassOne.class_variable')
  (technicalType 'PythonVariable')
)
(SOMIX.ParentChild
  (parent (ref: 2))
  (child (ref: 3))
  (isMain true)
)
(SOMIX.Code (id: 4 )
  (name '__init__')
  (uniqueName 'test1.ClassOne.__init__')
  (technicalType 'PythonMethod')
)
(SOMIX.ParentChild
  (parent (ref: 2))
  (child (ref: 4))
  (isMain true)
)
(SOMIX.Data (id: 5 )
  (name 'instance_variable')
  (uniqueName 'test1.ClassOne.instance_variable')
  (technicalType 'PythonVariable')
)
(SOMIX.ParentChild
  (parent (ref: 2))
  (child (ref: 5))
  (isMain true)
)
(SOMIX.Access
  (accessor (ref: 4))
  (accessed (ref: 5))
  (isWrite true)
  (isRead false)
  (isDependent true)
)
(SOMIX.Code (id: 6 )
  (name 'method_one')
  (uniqueName 'test1.ClassOne.method_one')
  (technicalType 'PythonMethod')
)
(SOMIX.ParentChild
  (parent (ref: 2))
  (child (ref: 6))
  (isMain true)
)
(SOMIX.Access
  (accessor (ref: 6))
  (accessed (ref: 5))
  (isWrite true)
  (isRead true)
  (isDependent true)
)
(SOMIX.Code (id: 7 )
  (name 'function_one')
  (uniqueName 'test1.function_one')
  (technicalType 'PythonFunction')
)
(SOMIX.ParentChild
  (parent (ref: 1))
  (child (ref: 7))
  (isMain true)
)
(SOMIX.Grouping (id: 8 )
  (name 'test2.py')
  (uniqueName 'subfolder.test2')
  (technicalType 'PythonFile')
)
(SOMIX.Grouping (id: 9 )
  (name 'ClassTwo')
  (uniqueName 'subfolder.test2.ClassTwo')
  (technicalType 'PythonClass')
)
(SOMIX.ParentChild
  (parent (ref: 8))
  (child (ref: 9))
  (isMain true)
)
(SOMIX.Code (id: 10 )
  (name 'method_two')
  (uniqueName 'subfolder.test2.ClassTwo.method_two')
  (technicalType 'PythonMethod')
)
(SOMIX.ParentChild
  (parent (ref: 9))
  (child (ref: 10))
  (isMain true)
)
(SOMIX.Call
  (caller (ref: 10))
  (called (ref: 4))
)
(SOMIX.Call
  (caller (ref: 10))
  (called (ref: 6))
)
(SOMIX.Call
  (caller (ref: 10))
  (called (ref: 7))
)
(SOMIX.Code (id: 11 )
  (name 'function_two')
  (uniqueName 'subfolder.test2.function_two')
  (technicalType 'PythonFunction')
)
(SOMIX.ParentChild
  (parent (ref: 8))
  (child (ref: 11))
  (isMain true)
)
(SOMIX.Call
  (caller (ref: 11))
  (called (ref: 7))
)
)
""")

        # # Run the extraction script
        # extraction_script_path = 'C:\DataEigen\Eigenes\Python2SOMIX\src\python2mse.py'  # Update this path if needed
        # # extraction_script_path = os.path.join('.', 'python2mse.py')
        # if not os.path.isfile(extraction_script_path):
        #     print(f"Extraction script not found at {extraction_script_path}")
        #     sys.exit(1)

        # Get the current script directory
        current_dir = Path(__file__).parent

        # Define the relative path to python2mse.py
        extraction_script_path = current_dir / 'python2mse.py'

        # Check if the extraction script exists
        if not extraction_script_path.is_file():
            print(f"Extraction script not found at {extraction_script_path}")
            sys.exit(1)            

        # Run the extraction script
        cmd = ['python', extraction_script_path]
        process = subprocess.Popen(cmd, cwd=test_dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(input=test_dir)
        if process.returncode != 0:
            print(f"Extraction script failed with return code {process.returncode}")
            print(stderr)
            sys.exit(1)

        # Find the generated mse file
        mse_files = [f for f in os.listdir(test_dir) if f.endswith('.mse')]

        # Exclude 'expected_output.mse' from the list
        mse_files = [f for f in mse_files if f != 'expected_output.mse']

        if not mse_files:
            print("No .mse file generated by extraction script")
            sys.exit(1)
        actual_mse_path = os.path.join(test_dir, mse_files[0])

        # Parse the expected and actual mse files

        # Log the paths
        logging.info(f"Expected MSE file: {expected_mse_path}")
        logging.info(f"Actual MSE file: {actual_mse_path}")

        # expected_elements = parse_mse_file(expected_mse_path)
        # actual_elements = parse_mse_file(actual_mse_path)

        # Compare the files
        identical, diffs1, diffs2 = compare_mse_files(expected_mse_path, actual_mse_path)

        if identical:
            print("The MSE files are identical.")
        else:
            print("The MSE files are different.")
            if diffs1:
                print("\nEntries in file1 but not in file2:")
                for diff in diffs1:
                    print(diff)
            if diffs2:
                print("\nEntries in file2 but not in file1:")
                for diff in diffs2:
                    print(diff)

    finally:
        # Clean up the test directory if you wish
        # Uncomment the following line to remove the test directory after the test
        # shutil.rmtree(test_dir)
        pass

if __name__ == '__main__':
    main()
