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
        while tokens and tokens[0] != ')':
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

def build_id_to_object_map(entries: List[SExpr]) -> Dict[str, str]:
    """
    Build a mapping from numeric IDs to formatted object strings (without 'id').
    """
    id_to_object = {}
    temp_objects = {}

    # First pass: Process coding objects and store their attributes
    for entry in entries:
        if entry[0] in {"SOMIX.Grouping", "SOMIX.Code", "SOMIX.Data"}:
            attrs = {}
            obj_id = None
            for attr in entry[1:]:
                if isinstance(attr, list) and len(attr) == 2:
                    key = attr[0]
                    value = attr[1].strip("'")
                    if key == "id:":
                        obj_id = value
                    # elif key == "linkToEditor":
                    #     # Skip 'linkToEditor' attribute
                    #     # This is problematic because the path will be different on different machines
                    #     continue
                    else:
                        attrs[key] = value
            if obj_id is None:
                raise ValueError(f"Entry {entry} lacks an 'id' attribute.")
            # Sort attributes alphabetically
            sorted_attrs = sorted(attrs.items())
            # Format as "SOMIX.Type(attr1:value1, attr2:value2, ...)"
            attr_str = ', '.join(f"{k}:{v}" for k, v in sorted_attrs)
            formatted = f"{entry[0]}({attr_str})"
            id_to_object[obj_id] = formatted
            temp_objects[obj_id] = formatted  # Store for relation replacements

    return id_to_object

def replace_refs_in_relations(entries: List[SExpr], id_to_object: Dict[str, str]) -> List[str]:
    """
    Replace 'ref' IDs in relations with the corresponding full object strings.
    Returns a list of formatted strings.
    """
    formatted_entries = []

    for entry in entries:
        if not isinstance(entry, list) or len(entry) == 0:
            continue
        entry_type = entry[0]
        if entry_type in {"SOMIX.Grouping", "SOMIX.Code", "SOMIX.Data"}:
            # Coding objects already processed in id_to_object
            continue
        elif entry_type in {"SOMIX.ParentChild", "SOMIX.Call", "SOMIX.Access"}:
            # Relations
            attrs = {}
            for attr in entry[1:]:
                if isinstance(attr, list) and len(attr) >= 2:
                    key = attr[0]
                    if any(subattr[0].startswith("ref:") for subattr in attr[1:]):
                        # Extract ref ID
                        # ref_match = re.search(r'\(ref:\s*(\d+)\)', ' '.join(attr[1:]))
                        # Flatten the list and convert all elements to strings
                        flat_attr = [str(item) if not isinstance(item, list) else ' '.join(item) for item in attr[1:]]
                        # Corrected regex to match 'ref: 1' format without parentheses
                        ref_match = re.search(r'ref:\s*(\d+)', ' '.join(flat_attr))
                        if ref_match:
                            ref_id = ref_match.group(1)
                            if ref_id in id_to_object:
                                attrs[key] = id_to_object[ref_id]
                            else:
                                raise ValueError(f"Unknown ref id: {ref_id}")
                        else:
                            raise ValueError(f"Invalid ref format in {attr}")
                    else:
                        # Handle boolean or other attributes
                        # Convert 'true'/'false' to 't'/'f' or as per your requirement
                        value = attr[1].strip("'")
                        # Optionally, handle specific value conversions here
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

def process_coding_objects(entries: List[SExpr], id_to_object: Dict[str, str]) -> List[str]:
    """
    Process coding objects to create formatted strings without 'id'.
    Returns a list of formatted strings.
    """
    formatted_entries = []
    for entry in entries:
        if entry[0] in {"SOMIX.Grouping", "SOMIX.Code", "SOMIX.Data"}:
            attrs = {}
            for attr in entry[1:]:
                if isinstance(attr, list) and len(attr) == 2:
                    key = attr[0]
                    if key == "id":
                        continue  # Skip 'id'
                    value = attr[1].strip("'")
                    attrs[key] = value
            # Sort attributes alphabetically
            sorted_attrs = sorted(attrs.items())
            # Format as "SOMIX.Type(attr1:value1, attr2:value2, ...)"
            attr_str = ', '.join(f"{k}:{v}" for k, v in sorted_attrs)
            formatted = f"{entry[0]}({attr_str})"
            formatted_entries.append(formatted)
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

    # Build ID to Object mapping
    id_to_object = build_id_to_object_map(entries)

    # Process coding objects
    # coding_objects = process_coding_objects(entries, id_to_object)
    coding_objects = list(id_to_object.values())

    # Replace in id_to_oject values the strings that starts with 'linkToEditor:' or 'name:' and ends with ', ' with an empty string
    # This makes the compact strings describing relations more readable
    for key in id_to_object:
        id_to_object[key] = re.sub(r'linkToEditor:.*?, ', '', id_to_object[key])    
        id_to_object[key] = re.sub(r'name:.*?, ', '', id_to_object[key])   


    # Process relations by replacing refs with full object strings
    relations = replace_refs_in_relations(entries, id_to_object)

    # Combine all formatted entries
    all_formatted = coding_objects + relations

    # Sort the list to make comparison order-independent
    all_formatted.sort()

    return all_formatted

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
    # os.makedirs(os.path.join(test_dir, 'subfolder1'), exist_ok=True)
    # os.makedirs(os.path.join(test_dir, 'subfolder2'), exist_ok=True)

    try:
        # Create test files
        # test1_path = os.path.join(test_dir, 'subfolder1','test1.py')
        # test2_path = os.path.join(test_dir, 'subfolder2', 'test2.py')
        test1_path = os.path.join(test_dir, 'test1.py')
        test2_path = os.path.join(test_dir, 'test2.py')

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
    classOne = ClassOne()
    classOne.method_one( 'test' )
    function_one()
    print("function_two called")

""")
            

        # Get the current script directory
        current_dir = Path(__file__).parent    

        #Fill current_dir2 and replace the backslashes with forward slashes
        current_dir2 = str(current_dir).replace('\\', '/')        

        # Write expected mse file
        expected_mse_path = os.path.join(test_dir, 'expected_output.mse')
        with open(expected_mse_path, 'w', encoding='utf-8') as f:
            f.write(f"""\
(
(SOMIX.Grouping (id: 1 )
  (name 'test1.py')
  (uniqueName 'test1')
  (technicalType 'PythonFile')
  (linkToEditor 'vscode://file/{current_dir2}/test/test1.py/:1:1')
)
(SOMIX.Grouping (id: 2 )
  (name 'ClassOne')
  (uniqueName 'test1.ClassOne')
  (technicalType 'PythonClass')
  (linkToEditor 'vscode://file/{current_dir2}/test/test1.py/:2:1')
)
(SOMIX.Code (id: 3 )
  (name '__init__')
  (technicalType 'PythonMethod')
  (uniqueName 'test1.ClassOne.__init__')
  (linkToEditor 'vscode://file/{current_dir2}/test/test1.py/:5:5')
)
(SOMIX.Data (id: 4 )
  (name 'instance_variable')
  (technicalType 'PythonVariable')
  (uniqueName 'test1.ClassOne.instance_variable')
  (linkToEditor 'vscode://file/{current_dir2}/test/test1.py/:6:9')
)
(SOMIX.Code (id: 5 )
  (name 'method_one')
  (technicalType 'PythonMethod')
  (uniqueName 'test1.ClassOne.method_one')
  (linkToEditor 'vscode://file/{current_dir2}/test/test1.py/:9:5')
)
(SOMIX.Code (id: 6 )
  (name 'function_one')
  (technicalType 'PythonFunction')
  (uniqueName 'test1.function_one')
  (linkToEditor 'vscode://file/{current_dir2}/test/test1.py/:13:1')
)
(SOMIX.Grouping (id: 7 )
  (name 'test2.py')
  (uniqueName 'subfolder.test2')
  (technicalType 'PythonFile')
  (linkToEditor 'vscode://file/{current_dir2}/test/subfolder/test2.py/:1:1')
)
(SOMIX.Grouping (id: 8 )
  (name 'ClassTwo')
  (uniqueName 'subfolder.test2.ClassTwo')
  (technicalType 'PythonClass')
  (linkToEditor 'vscode://file/{current_dir2}/test/subfolder/test2.py/:4:1')
)
(SOMIX.Code (id: 9 )
  (name 'method_two')
  (technicalType 'PythonMethod')
  (uniqueName 'subfolder.test2.ClassTwo.method_two')
  (linkToEditor 'vscode://file/{current_dir2}/test/subfolder/test2.py/:5:5')
)
(SOMIX.Code (id: 11 )
  (name 'method_three')
  (technicalType 'PythonMethod')
  (uniqueName 'subfolder.test2.ClassTwo.method_three')
  (linkToEditor 'vscode://file/{current_dir2}/test/subfolder/test2.py/:11:5')
)
(SOMIX.Code (id: 10 )
  (name 'function_two')
  (technicalType 'PythonFunction')
  (uniqueName 'subfolder.test2.function_two')
  (linkToEditor 'vscode://file/{current_dir2}/test/subfolder/test2.py/:15:1')
)
(SOMIX.ParentChild
  (parent (ref: 1))
  (child (ref: 2))
  (isMain true)
)
(SOMIX.ParentChild
  (parent (ref: 2))
  (child (ref: 3))
  (isMain true)
)
(SOMIX.ParentChild
  (parent (ref: 3))
  (child (ref: 4))
  (isMain true)
)
(SOMIX.ParentChild
  (parent (ref: 2))
  (child (ref: 5))
  (isMain true)
)
(SOMIX.ParentChild
  (parent (ref: 1))
  (child (ref: 6))
  (isMain true)
)
(SOMIX.ParentChild
  (parent (ref: 7))
  (child (ref: 8))
  (isMain true)
)
(SOMIX.ParentChild
  (parent (ref: 8))
  (child (ref: 9))
  (isMain true)
)
(SOMIX.ParentChild
  (parent (ref: 8))
  (child (ref: 11))
  (isMain true)
)
(SOMIX.ParentChild
  (parent (ref: 7))
  (child (ref: 10))
  (isMain true)
)
(SOMIX.Call
  (caller (ref: 9))
  (called (ref: 3))
)
(SOMIX.Call
  (caller (ref: 9))
  (called (ref: 5))
)
(SOMIX.Call
  (caller (ref: 9))
  (called (ref: 6))
)
(SOMIX.Call
  (caller (ref: 11))
  (called (ref: 5))
)
(SOMIX.Call
  (caller (ref: 10))
  (called (ref: 3))
)
(SOMIX.Call
  (caller (ref: 10))
  (called (ref: 5))
)
(SOMIX.Call
  (caller (ref: 10))
  (called (ref: 6))
)
(SOMIX.Call
  (caller (ref: 9))
  (called (ref: 3))
)
(SOMIX.Call
  (caller (ref: 9))
  (called (ref: 5))
)
(SOMIX.Call
  (caller (ref: 9))
  (called (ref: 6))
)
(SOMIX.Call
  (caller (ref: 11))
  (called (ref: 5))
)
(SOMIX.Call
  (caller (ref: 10))
  (called (ref: 3))
)
(SOMIX.Call
  (caller (ref: 10))
  (called (ref: 5))
)
(SOMIX.Call
  (caller (ref: 10))
  (called (ref: 6))
)
(SOMIX.Access
  (accessor (ref: 3))
  (accessed (ref: 4))
  (isWrite false)
  (isRead true)
  (isDependent true)
)
(SOMIX.Access
  (accessor (ref: 5))
  (accessed (ref: 4))
  (isWrite false)
  (isRead true)
  (isDependent true)
)
(SOMIX.Access
  (accessor (ref: 3))
  (accessed (ref: 4))
  (isWrite false)
  (isRead true)
  (isDependent true)
)
(SOMIX.Access
  (accessor (ref: 5))
  (accessed (ref: 4))
  (isWrite false)
  (isRead true)
  (isDependent true)
)
)
""")

        # # Run the extraction script
        # extraction_script_path = 'C:\DataEigen\Eigenes\Python2SOMIX\src\python2mse.py'  # Update this path if needed
        # # extraction_script_path = os.path.join('.', 'python2mse.py')
        # if not os.path.isfile(extraction_script_path):
        #     print(f"Extraction script not found at {extraction_script_path}")
        #     sys.exit(1)


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
            print("OK")
        else:
            print("The MSE files are different.")
            if diffs1:
                print("\nEntries in expected but not in actual:")
                for diff in diffs1:
                    print(diff)
            if diffs2:
                print("\nEntries in actual but not in expected:")
                for diff in diffs2:
                    print(diff)

    finally:
        # Clean up the test directory if you wish
        # Uncomment the following line to remove the test directory after the test
        # shutil.rmtree(test_dir)
        pass

if __name__ == '__main__':
    main()
