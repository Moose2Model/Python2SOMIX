# Python Code Extraction Script Documentation

*Author: OpenAI's Assistant*

*Author for adaptions: Rainer Winkler*

---

## Table of Contents

- [a) Overview of the Script](#a-overview-of-the-script)
- [b) Input Code Processing](#b-input-code-processing)
- [c) Testing Methodology](#c-testing-methodology)
- [d) Output Relations and SOMIX Format](#d-output-relations-and-somix-format)
- [e) Main Classes](#e-main-classes)
- [f) Core Functions and Logic](#f-core-functions-and-logic)
- [g) Data Storage Structures](#g-data-storage-structures)
- [h) Debugging Strategies](#h-debugging-strategies)
- [i) Challenges Faced](#i-challenges-faced)
- [j) Recommended Next Steps](#j-recommended-next-steps)
- [k) Recommendations for Future Development](#k-recommendations-for-future-development)
- [l) Author Statement](#l-author-statement)
- [m) Attachment - mse Example file](#m-attachment---mse-example-file)

---

## a) Overview of the Script

The Python code extraction script is designed to analyze a Python codebase and extract structural and relational information about its components. It parses Python files to identify classes, functions, methods, variables, and their relationships, and outputs this information in the SOMIX format encapsulated within an MSE (Moose Smalltalk Exporter) file.

The primary purpose of the script is to generate a model that represents the static structure and some dynamic interactions (like method calls and variable accesses) within the codebase, facilitating further analysis or visualization using tools that support the SOMIX format.

---

## b) Input Code Processing

The script processes Python source code files (`.py` files) within a specified directory and its subdirectories. It uses Python's built-in `ast` (Abstract Syntax Tree) module to parse the code, allowing it to analyze the code's structure without executing it.

### Code Elements Extracted:

- **Modules**: Each Python file is considered a module.
- **Classes**: Definitions of classes within the code.
- **Functions**: Standalone functions not associated with a class.
- **Methods**: Functions defined within a class.
- **Variables**: Variables at the module, class, and function levels, including instance variables (`self` attributes).
- **Calls**: Method and function calls within the code.
- **Accesses**: Read and write accesses to variables.

---

## c) Testing Methodology

Testing the script involves verifying that it correctly extracts the expected elements and relationships from a given set of Python files.

### Steps for Testing:

1. **Create Test Code**: Develop small Python scripts (`test1.py`, `test2.py`, etc.) that include various code structures and interactions.
2. **Run the Extraction Script**: Execute the extraction script with the directory containing the test code as input.
3. **Verify Output**: Examine the generated `.mse` file to ensure that it contains the correct SOMIX elements and relationships.
4. **Automated Testing**: Implement a test script (`test_extraction.py`) that compares the actual output with an expected output file (`expected_output.mse`) to automate the verification process.

---

## d) Output Relations and SOMIX Format

### SOMIX Overview

SOMIX (System Object Model Interchange for XML) is a format used to represent software models, particularly focusing on the structure and interactions within code. It categorizes elements into groupings, code, and data, and defines relationships like parent-child, calls, and accesses.

See for the specification [Paper SOMIX.pdf](https://github.com/Moose2Model/SOMIX/tree/main/SOMIX%201).
 The background and motivation is described in [A Software Metamodel Restricted to Key Aspects of a Software System for Developers and a Method to Keep Manually Drawn Diagrams Up-to-Date and Correct](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4049604).

### MSE Format

The MSE (Moose Smalltalk Exporter) format is a textual representation used to serialize software models. It organizes data in a nested, Lisp-like syntax, which is suitable for importing into analysis tools like Moose or other software visualization tools.

### Extracted Relations

The script extracts the following relations:

- **ParentChild**: Represents the hierarchical structure, where elements are nested within modules, classes, or functions.
- **Call**: Represents a call from one code element (function or method) to another.
- **Access**: Represents read or write access to a data element (variable) by a code element.

### Understanding of SOMIX and MSE

- **SOMIX Elements**:
  - `SOMIX.Grouping`: Represents structural groupings like modules and classes.
  - `SOMIX.Code`: Represents executable code elements like functions and methods.
  - `SOMIX.Data`: Represents data elements like variables.
- **MSE Structure**:
  - Uses parentheses to denote elements and their attributes.
  - Each element includes an `id`, `name`, `uniqueName`, `technicalType`, and optionally a `linkToEditor`.
  - Relationships reference elements by their `id`.

---

## e) Main Classes

The script is structured with several key classes:

1. **Element**: The base class representing a generic element in the model.
2. **Grouping**: Inherits from `Element` to represent modules and classes.
3. **Code**: Inherits from `Element` to represent functions and methods.
4. **Data**: Inherits from `Element` to represent variables.
5. **DefinitionCollector**: An `ast.NodeVisitor` subclass that collects definitions of classes, functions, methods, and variables.
6. **UsageAnalyzer**: An `ast.NodeVisitor` subclass that analyzes usages, such as calls and variable accesses.

---

## f) Core Functions and Logic

### DefinitionCollector Methods:

- **`visit_Module`**: Processes a module (Python file) and creates a `Grouping` element.
- **`visit_ClassDef`**: Processes class definitions and creates `Grouping` elements for classes.
- **`visit_FunctionDef`**: Processes function and method definitions and creates `Code` elements.
- **`visit_Assign`**: Processes variable assignments to collect variables at the module, class, and function levels.

### UsageAnalyzer Methods:

- **`visit_Module`**: Initializes scope for the module.
- **`visit_ClassDef`**: Sets up the current class context.
- **`visit_FunctionDef`**: Sets up the current function context and initializes variable type tracking.
- **`visit_Assign`**: Infers variable types through assignments and updates type mappings.
- **`visit_Call`**: Records calls to functions and methods using inferred types.
- **`resolve_called_name`**: Resolves the fully qualified name of a called function or method.
- **`visit_Attribute`**: Records accesses to attributes, inferring types where possible.
- **`visit_Name`**: Records accesses to variables.

### Logic Implementation:

- **Type Inference**: The script attempts to infer types by tracking assignments and using known class definitions.
- **Scope Management**: Maintains the current scope (module, class, function) to accurately resolve names.
- **Symbol Table**: Uses a symbol table to keep track of defined elements and their unique names for resolution.

---

## g) Data Storage Structures

- **`elements` Dictionary**: Stores all elements (`Grouping`, `Code`, `Data`) by their unique names.
- **`symbol_table` Dictionary**: A shared symbol table that maps unique names to their corresponding elements for quick lookup.
- **`parent_child_relations` List**: Collects parent-child relationships between elements.
- **`calls` List**: Collects call relationships between code elements.
- **`accesses` List**: Collects access relationships where code elements read or write data elements.
- **`variable_types` Dictionary**: Tracks the inferred types of variables within the current function scope.
- **`class_variable_types` Dictionary**: Tracks the inferred types of instance variables (`self` attributes) across the class.

---

## h) Debugging Strategies

- **Logging and Print Statements**: Insert print statements or use the `logging` module to output the internal state at various points in the script.
- **AST Visualization**: Use tools like `ast.dump()` to visualize the abstract syntax tree of the code being analyzed.
- **Step-by-Step Execution**: Use a debugger (e.g., `pdb`) to step through the code and inspect variables and flow.
- **Test Cases**: Create small, isolated test cases that cover specific scenarios to pinpoint issues.
- **Error Handling**: Add try-except blocks around critical sections to catch and report exceptions without halting execution.
- **Verbose Output**: Optionally add a verbosity flag to control the level of detail in the output during execution.

---

## i) Challenges Faced

- **Dynamic Typing in Python**: Python's dynamic nature makes static analysis and type inference difficult, especially without type annotations.
- **Lack of Type Annotations**: Without explicit type hints, inferring variable types and resolving method calls is limited.
- **Complex Control Flows**: Handling complex code structures, such as dynamic attribute creation or reflection, is challenging.
- **Recursive and Indirect Assignments**: Tracking types through multiple layers of variable assignments increases complexity.
- **Balancing Accuracy and Complexity**: Enhancing type inference without significantly increasing the script's complexity or processing time.

---

## j) Recommended Next Steps

- **Incremental Type Annotations**: Gradually add type annotations to the codebase where possible to improve analysis accuracy.
- **Integration with Static Analysis Tools**: Consider integrating with tools like `mypy` for more advanced type inference.
- **Enhanced Error Reporting**: Improve error messages and logging to assist in identifying and resolving issues.
- **Performance Optimization**: Profile the script to identify bottlenecks and optimize for larger codebases.
- **Support for More Language Features**: Extend the script to handle more Python features (e.g., decorators, context managers).
- **User Documentation**: Develop user-friendly documentation and usage examples to facilitate adoption.

---

## k) Recommendations for Future Development

- **Collaborate with Type Checkers**: Utilize existing static analysis tools to supplement the script's capabilities.
- **Modular Design**: Refactor the script into smaller, reusable components to improve maintainability and extensibility.
- **Testing Framework**: Implement a comprehensive testing framework with a variety of test cases covering different code patterns.
- **Code Comments and Documentation**: Add detailed comments and docstrings to the code for better understanding and maintenance.
- **Community Feedback**: Engage with other developers to gather feedback and identify common challenges or feature requests.
- **Version Control**: Use a version control system (e.g., Git) to track changes and collaborate effectively.

---

## l) Author Statement

This documentation and the associated script were developed by me, OpenAI's Assistant, to assist in analyzing Python codebases and extracting structural and relational information. I hope this tool proves valuable in your development efforts, and I encourage you to build upon it to suit your specific needs.

---

## m) Attachment - mse Example file

The following file was given prior to implementation to specify the format and content of the output file.

Example_SOMIX_File_Python.mse
```mse
( (SOMIX.Grouping (id: 1 )
  (name 'myfile.py')
  (uniqueName 'myrepo.myfile')
  (technicalType 'PythonFile'))
(SOMIX.Grouping (id: 2 )
  (name 'MyClass')
  (uniqueName 'myrepo.myfile.MyClass')
  (technicalType 'PythonClass'))
(SOMIX.ParentChild
  (parent (ref: 1))
  (child (ref: 2))
  (isMain true))
(SOMIX.Code (id: 3 )
  (name 'MyMethod')
  (technicalType PythonMethod')
  (uniqueName 'myrepo.myfile.MyClass.MyMethod')
  (linkToEditor 'vscode://file/C:/DataEigen/Eigenes/Python2SOMIX/work/src/myfile.py/:12:1'))
(SOMIX.ParentChild
  (parent (ref: 2))
  (child (ref: 3))
  (isMain true))
(SOMIX.Data (id: 4 )
  (name 'myVariable')
  (technicalType 'PythonVariable')
  (uniqueName 'myrepo.myfile.MyClass.myVariable')
  (linkToEditor 'vscode://file/C:/DataEigen/Eigenes/Python2SOMIX/work/src/myfile.py/:25:1'))
(SOMIX.ParentChild
  (parent (ref: 2))
  (child (ref: 4))
  (isMain true))
(SOMIX.Grouping (id: 5 )
  (name 'MyClass2')
  (uniqueName 'myrepo.myfile.MyClass2')
  (technicalType 'PythonClass'))
(SOMIX.ParentChild
  (parent (ref: 1))
  (child (ref: 5))
  (isMain true))
(SOMIX.Code (id: 6 )
  (name 'MyMethod2')
  (technicalType PythonMethod')
  (uniqueName 'myrepo.myfile.MyClass.MyMethod2')
  (linkToEditor 'vscode://file/C:/DataEigen/Eigenes/Python2SOMIX/work/src/myfile.py/:112:1'))
(SOMIX.ParentChild
  (parent (ref: 5))
  (child (ref: 6))
  (isMain true))
(SOMIX.Data (id: 7 )
  (name 'myVariable2')
  (technicalType 'PythonVariable')
  (uniqueName 'myrepo.myfile.MyClass.myVariable2')
  (linkToEditor 'vscode://file/C:/DataEigen/Eigenes/Python2SOMIX/work/src/myfile.py/:125:1'))
(SOMIX.ParentChild
  (parent (ref: 5))
  (child (ref: 7))
  (isMain true))
(SOMIX.Access
  (accessor (ref: 3))
  (accessed (ref: 7))
  (isWrite true)
  (isRead false)
  (isDependent true))  
(SOMIX.Call
  (caller (ref: 3))
  (called (ref: 6))))  
```
