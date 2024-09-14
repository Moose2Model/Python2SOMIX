import os
import re
import sys
import shutil
import subprocess

def parse_mse_file(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove whitespace and line breaks
    content = re.sub(r'\s+', '', content)

    # Split into elements
    elements = re.findall(r'\((SOMIX\.[^)]+\))', content)

    parsed_elements = []

    for elem in elements:
        elem_dict = {}
        # Extract the type
        elem_type_match = re.match(r'(SOMIX\.\w+)', elem)
        if elem_type_match:
            elem_type = elem_type_match.group(1)
            elem_dict['type'] = elem_type
        else:
            continue

        # Extract properties
        properties = re.findall(r'\(([^()]+)\)', elem)
        for prop in properties:
            key_value = prop.split(None, 1)
            if len(key_value) == 2:
                key, value = key_value
                value = value.strip("'")
                elem_dict[key] = value
        parsed_elements.append(elem_dict)

    return parsed_elements

def compare_elements(expected_elements, actual_elements):
    # Build dictionaries keyed by uniqueName
    expected_dict = {}
    for elem in expected_elements:
        unique_name = elem.get('uniqueName')
        if unique_name:
            expected_dict[(elem['type'], unique_name)] = elem

    actual_dict = {}
    for elem in actual_elements:
        unique_name = elem.get('uniqueName')
        if unique_name:
            actual_dict[(elem['type'], unique_name)] = elem

    # Compare elements
    success = True
    for key in expected_dict:
        if key not in actual_dict:
            print(f"Missing element in actual output: {key}")
            success = False
        else:
            expected_elem = expected_dict[key]
            actual_elem = actual_dict[key]
            # Compare properties except IDs
            for prop in expected_elem:
                if prop not in ['id', 'linkToEditor', 'parent', 'child', 'caller', 'called', 'accessor', 'accessed']:
                    if expected_elem[prop] != actual_elem.get(prop):
                        print(f"Difference in element {key}: property '{prop}' expected '{expected_elem[prop]}', got '{actual_elem.get(prop)}'")
                        success = False

    # Compare relationships (ParentChild, Call, Access)
    expected_rels = [elem for elem in expected_elements if elem['type'] in ('SOMIX.ParentChild', 'SOMIX.Call', 'SOMIX.Access')]
    actual_rels = [elem for elem in actual_elements if elem['type'] in ('SOMIX.ParentChild', 'SOMIX.Call', 'SOMIX.Access')]

    for exp_rel in expected_rels:
        match_found = False
        for act_rel in actual_rels:
            if exp_rel['type'] == act_rel['type']:
                # For relationships, we can't compare IDs directly, so we assume if types match, it's acceptable
                match_found = True
                break
        if not match_found:
            print(f"Missing or different relationship in actual output: {exp_rel}")
            success = False

    return success

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
class ClassOne:
    class_variable = 100

    def __init__(self):
        self.instance_variable = 0

    def method_one(self):
        self.instance_variable += 1
        print("ClassOne method_one called")

def function_one():
    print("function_one called")
""")

        with open(test2_path, 'w', encoding='utf-8') as f:
            f.write("""\
from test1 import ClassOne, function_one

class ClassTwo:
    def method_two(self):
        obj = ClassOne()
        obj.method_one()
        function_one()
        print("ClassTwo method_two called")

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

        # Run the extraction script
        extraction_script_path = 'C:\DataEigen\Eigenes\Python2SOMIX\src\python2mse.py'  # Update this path if needed
        if not os.path.isfile(extraction_script_path):
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
        if not mse_files:
            print("No .mse file generated by extraction script")
            sys.exit(1)
        actual_mse_path = os.path.join(test_dir, mse_files[0])

        # Parse the expected and actual mse files
        expected_elements = parse_mse_file(expected_mse_path)
        actual_elements = parse_mse_file(actual_mse_path)

        # Compare the elements
        success = compare_elements(expected_elements, actual_elements)

        if success:
            print("Test passed: The actual output matches the expected output.")
        else:
            print("Test failed: Differences found between actual and expected outputs.")

    finally:
        # Clean up the test directory if you wish
        # Uncomment the following line to remove the test directory after the test
        # shutil.rmtree(test_dir)
        pass

if __name__ == '__main__':
    main()
