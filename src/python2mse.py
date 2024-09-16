import os
import ast
import datetime
import logging

# Configure logging
logging.basicConfig(
    filename='python2mse.log',
    filemode='w',
    level=logging.DEBUG,  # Set to DEBUG to capture all levels of logs
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Define a set of built-in functions to exclude them from being treated as user-defined
BUILT_IN_FUNCTIONS = {
    'print', 'len', 'range', 'int', 'str', 'float', 'bool', 'list',
    'dict', 'set', 'tuple', 'open', 'enumerate', 'zip', 'map', 'filter',
    'sum', 'min', 'max', 'abs', 'round', 'sorted', 'reversed', 'any',
    'all', 'type', 'isinstance', 'issubclass', 'getattr', 'setattr',
    'hasattr', 'delattr', 'globals', 'locals', 'dir', 'id', 'eval',
    'exec', 'compile', 'vars', 'globals', 'locals', 'help', 'input'
}

class Element:
    def __init__(self, id, name, unique_name, technical_type, link_to_editor=None):
        self.id = id
        self.name = name
        self.unique_name = unique_name
        self.technical_type = technical_type
        self.link_to_editor = link_to_editor

class Grouping(Element):
    def __init__(self, id, name, unique_name, technical_type, link_to_editor=None):
        super().__init__(id, name, unique_name, technical_type, link_to_editor)
        self.children = []
        self.is_main = False

class Code(Element):
    def __init__(self, id, name, unique_name, technical_type, link_to_editor=None):
        super().__init__(id, name, unique_name, technical_type, link_to_editor)
        self.children = []
        self.calls = []
        self.accesses = []
        self.parameters = []  # To store function/method parameters
        self.inferred_parameter_types = {}  # To store inferred types for parameters

class Data(Element):
    def __init__(self, id, name, unique_name, technical_type, link_to_editor=None):
        super().__init__(id, name, unique_name, technical_type, link_to_editor)
        self.accessed_by = []

class DefinitionCollector(ast.NodeVisitor):
    def __init__(self, filename, module_name, base_path, symbol_table, elements, parent_child_relations):
        self.filename = filename
        self.module_name = module_name
        self.base_path = base_path
        self.symbol_table = symbol_table  # Shared symbol table
        self.elements = elements  # Shared elements dictionary
        self.parent_child_relations = parent_child_relations  # Shared relations list

        self.scope_stack = []
        self.current_class = None
        self.current_function = None

        self.local_namespace = {}  # Map local names to fully qualified names

    def get_link(self, lineno, col_offset):
        col = col_offset + 1
        filepath = os.path.abspath(self.filename).replace('\\', '/')
        return f'vscode://file/{filepath}/:{lineno}:{col}'

    def visit_Module(self, node):
        name = os.path.basename(self.filename)
        unique_name = self.module_name
        technical_type = 'PythonFile'
        link_to_editor = self.get_link(getattr(node, 'lineno', 1), 0)

        module_element = Grouping(None, name, unique_name, technical_type, link_to_editor)
        self.elements[unique_name] = module_element
        module_element.is_main = True
        self.scope_stack.append(module_element)

        self.generic_visit(node)

        self.scope_stack.pop()

    def visit_ClassDef(self, node):
        name = node.name
        unique_name = self.module_name + '.' + name
        technical_type = 'PythonClass'
        link_to_editor = self.get_link(node.lineno, node.col_offset)

        class_element = Grouping(None, name, unique_name, technical_type, link_to_editor)
        self.elements[unique_name] = class_element

        # Add to symbol table
        self.symbol_table[unique_name] = class_element

        parent = self.scope_stack[-1]
        self.parent_child_relations.append({'parent': parent.unique_name, 'child': unique_name, 'isMain': True})
        parent.children.append(class_element)

        self.scope_stack.append(class_element)
        self.current_class = class_element

        self.generic_visit(node)

        self.scope_stack.pop()
        self.current_class = None

    def visit_FunctionDef(self, node):
        name = node.name
        if self.current_class:
            unique_name = self.current_class.unique_name + '.' + name
            technical_type = 'PythonMethod'
        else:
            unique_name = self.module_name + '.' + name
            technical_type = 'PythonFunction'
        link_to_editor = self.get_link(node.lineno, node.col_offset)

        code_element = Code(None, name, unique_name, technical_type, link_to_editor)
        self.elements[unique_name] = code_element

        # Add to symbol table
        self.symbol_table[unique_name] = code_element

        parent = self.scope_stack[-1]
        self.parent_child_relations.append({'parent': parent.unique_name, 'child': unique_name, 'isMain': True})
        parent.children.append(code_element)

        self.scope_stack.append(code_element)
        self.current_function = code_element

        # Collect parameter names for potential type inference
        parameter_names = [arg.arg for arg in node.args.args]
        code_element.parameters = parameter_names  # Store function parameters
        logging.debug(f"Collected parameters for function '{unique_name}': {parameter_names}")

        self.generic_visit(node)

        self.scope_stack.pop()
        self.current_function = None

    def visit_Assign(self, node):
        # Handle class-level attributes (outside any function)
        if self.current_class and not self.current_function:
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    if isinstance(target.value, ast.Name) and target.value.id == 'self':
                        attr_name = target.attr
                        unique_attr_name = f"{self.current_class.unique_name}.{attr_name}"
                        technical_type = 'PythonVariable'  # Changed to 'PythonVariable' to match previous MSE
                        link_to_editor = self.get_link(node.lineno, node.col_offset)

                        if unique_attr_name not in self.elements:
                            data_element = Data(None, attr_name, unique_attr_name, technical_type, link_to_editor)
                            self.elements[unique_attr_name] = data_element
                            self.symbol_table[unique_attr_name] = data_element

                            parent = self.scope_stack[-1]
                            self.parent_child_relations.append({'parent': parent.unique_name, 'child': unique_attr_name, 'isMain': False})
                            parent.children.append(data_element)

                            logging.debug(f"Collected class attribute '{unique_attr_name}'")
        # Handle instance-level attributes (inside a function)
        elif self.current_class and self.current_function:
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    if isinstance(target.value, ast.Name) and target.value.id == 'self':
                        attr_name = target.attr
                        unique_attr_name = f"{self.current_class.unique_name}.{attr_name}"
                        technical_type = 'PythonVariable'  # Changed to 'PythonVariable' to match previous MSE
                        link_to_editor = self.get_link(node.lineno, node.col_offset)

                        if unique_attr_name not in self.elements:
                            data_element = Data(None, attr_name, unique_attr_name, technical_type, link_to_editor)
                            self.elements[unique_attr_name] = data_element
                            self.symbol_table[unique_attr_name] = data_element

                            parent = self.scope_stack[-1]
                            self.parent_child_relations.append({'parent': parent.unique_name, 'child': unique_attr_name, 'isMain': False})
                            parent.children.append(data_element)

                            logging.debug(f"Collected instance attribute '{unique_attr_name}'")
        self.generic_visit(node)



class UsageAnalyzer(ast.NodeVisitor):
    def __init__(self, filename, module_name, base_path, symbol_table, calls, accesses, parameter_type_map=None):
        self.filename = filename
        self.module_name = module_name
        self.base_path = base_path
        self.symbol_table = symbol_table  # Shared symbol table
        self.calls = calls
        self.accesses = accesses
        self.parameter_type_map = parameter_type_map or {}

        self.scope_stack = []
        self.current_class = None
        self.current_function = None

        self.local_namespace = {}  # Map local names to fully qualified names
        self.variable_types = {}  # Map variable names to class names (within a function)
        self.class_variable_types = {}  # Map self attributes to types across the class




    def visit_Module(self, node):
        logging.debug(f"Visiting module: {self.module_name}")
        self.scope_stack.append(self.module_name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_Import(self, node):
        logging.debug(f"Processing import in module: {self.module_name}")
        for alias in node.names:
            name = alias.name
            asname = alias.asname if alias.asname else name
            self.local_namespace[asname] = name
            logging.debug(f"Imported {name} as {asname}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        logging.debug(f"Processing from-import in module: {self.module_name}")
        module = node.module
        for alias in node.names:
            name = alias.name
            asname = alias.asname if alias.asname else name
            full_name = module + '.' + name if module else name
            self.local_namespace[asname] = full_name
            logging.debug(f"Imported {name} from {module} as {asname}")
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        name = node.name
        unique_name = self.module_name + '.' + name
        logging.debug(f"Visiting class: {unique_name}")

        self.scope_stack.append(unique_name)
        self.current_class = unique_name

        # Initialize class variable types
        self.class_variable_types = {}

        self.generic_visit(node)

        self.scope_stack.pop()
        self.current_class = None

    def visit_FunctionDef(self, node):
        name = node.name
        if self.current_class:
            unique_name = self.current_class + '.' + name
        else:
            unique_name = self.module_name + '.' + name

        logging.debug(f"Visiting function/method: {unique_name}")

        self.scope_stack.append(unique_name)
        self.current_function = unique_name

        # Initialize variable types for this function
        self.variable_types = {}

        # Collect parameter names and assign inferred types from annotations
        for arg in node.args.args:
            param_name = arg.arg
            if arg.annotation:
                inferred_type = self.get_annotation_type(arg.annotation)
                if inferred_type:
                    # Resolve the inferred type to its unique name
                    resolved_type = self.resolve_class_name(inferred_type)
                    if resolved_type:
                        if unique_name not in self.parameter_type_map:
                            self.parameter_type_map[unique_name] = {}
                        self.parameter_type_map[unique_name][param_name] = set([resolved_type.unique_name])
                        logging.debug(f"Assigned inferred type '{resolved_type.unique_name}' to parameter '{param_name}' in function '{unique_name}'")
                        # **Assign the inferred type to variable_types**
                        self.variable_types[param_name] = resolved_type.unique_name
                        logging.debug(f"Set variable_types['{param_name}'] = '{resolved_type.unique_name}'")
            else:
                # Attempt to infer type from existing parameter_type_map
                inferred_types = self.parameter_type_map.get(unique_name, {}).get(param_name)
                if inferred_types and len(inferred_types) == 1:
                    inferred_type = next(iter(inferred_types))
                    self.variable_types[param_name] = inferred_type
                    logging.debug(f"Inferred type '{inferred_type}' for parameter '{param_name}' in function '{unique_name}'")
                elif inferred_types and len(inferred_types) > 1:
                    inferred_type = next(iter(inferred_types))  # Choose one for simplicity
                    self.variable_types[param_name] = inferred_type
                    logging.warning(f"Parameter '{param_name}' in function '{unique_name}' has multiple inferred types: {inferred_types}. Assigned '{inferred_type}'")
                else:
                    self.variable_types[param_name] = None
                    logging.debug(f"Parameter '{param_name}' in function '{unique_name}' has unknown type")

        self.generic_visit(node)

        # Merge self.variable_types into class_variable_types if applicable
        for var, var_type in self.variable_types.items():
            if var.startswith('self.'):
                self.class_variable_types[var] = var_type
                logging.debug(f"Inferred type for '{var}' in class '{self.current_class}': {var_type}")

        self.variable_types = {}

        self.scope_stack.pop()
        self.current_function = None

    def get_annotation_type(self, annotation):
        """
        Extract the type name from the annotation node.
        """
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Attribute):
            parts = []
            while isinstance(annotation, ast.Attribute):
                parts.append(annotation.attr)
                annotation = annotation.value
            if isinstance(annotation, ast.Name):
                parts.append(annotation.id)
                parts.reverse()
                return '.'.join(parts)
        elif isinstance(annotation, ast.Subscript):
            return self.get_annotation_type(annotation.value)
        return None
    
    def visit_Assign(self, node):
        if self.current_function:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    var_name = target.id
                    value = node.value
                    var_type = self.infer_type(value)
                    self.variable_types[var_name] = var_type
                    logging.debug(f"Inferred type for variable '{var_name}' in function '{self.current_function}': {var_type}")
                elif isinstance(target, ast.Attribute):
                    if isinstance(target.value, ast.Name) and target.value.id == 'self':
                        attr_name = 'self.' + target.attr
                        value = node.value
                        var_type = self.infer_type(value)
                        self.variable_types[attr_name] = var_type
                        self.class_variable_types[attr_name] = var_type
                        logging.debug(f"Inferred type for attribute '{attr_name}' in class '{self.current_class}': {var_type}")
        self.generic_visit(node)

    def infer_type(self, value):
        if isinstance(value, ast.Call):
            class_name = self.get_called_name(value.func)
            class_element = self.resolve_class_name(class_name)
            if class_element:
                full_class_name = class_element.unique_name
                init_method_name = full_class_name + '.__init__'
                init_method = self.symbol_table.get(init_method_name)
                if init_method and isinstance(init_method, Code):
                    self.calls.append({'caller': self.current_function, 'called': init_method.unique_name})
                    logging.debug(f"Recorded call from '{self.current_function}' to '__init__' of '{full_class_name}'")
                return full_class_name
        elif isinstance(value, ast.Name):
            var_name = value.id
            var_type = self.variable_types.get(var_name) or self.class_variable_types.get(var_name)
            logging.debug(f"Inferred type for variable '{var_name}': {var_type}")
            return var_type
        elif isinstance(value, ast.Attribute):
            # Handle cases like self.attribute
            var_name = value.attr
            var_type = self.variable_types.get(var_name) or self.class_variable_types.get(var_name)
            logging.debug(f"Inferred type for attribute '{var_name}': {var_type}")
            return var_type
        elif isinstance(value, ast.Constant):
            # For literals, return None or a generic type
            logging.debug(f"Encountered constant value: {value.value}")
            return None
        # Could not infer type
        logging.warning(f"Could not infer type for value: {ast.dump(value)}")
        return None

    def resolve_class_name(self, class_name):
        if not class_name:
            return None
        if class_name in self.local_namespace:
            class_unique_name = self.local_namespace[class_name]
        else:
            class_unique_name = self.module_name + '.' + class_name
        class_element = self.symbol_table.get(class_unique_name)
        if isinstance(class_element, Grouping):
            logging.debug(f"Resolved class name '{class_name}' to '{class_unique_name}'")
            return class_element
        else:
            logging.warning(f"Could not resolve class name '{class_name}'")
            return None

    def visit_Call(self, node):
        called_name = self.get_called_name(node.func)
        logging.debug(f"Processing call to '{called_name}' in function '{self.current_function}'")
        if called_name:
            called_element = self.resolve_called_name(called_name)
            if called_element and isinstance(called_element, Code):
                if self.current_function:
                    self.calls.append({'caller': self.current_function, 'called': called_element.unique_name})
                    logging.debug(f"Recorded call from '{self.current_function}' to '{called_element.unique_name}'")
                self.infer_parameter_types(called_element.unique_name, node)
        self.generic_visit(node)

    def infer_parameter_types(self, called_unique_name, call_node):
        if not self.parameter_type_map:
            return
        called_function = self.symbol_table.get(called_unique_name)
        if not called_function or not isinstance(called_function, Code):
            logging.warning(f"Called function '{called_unique_name}' not found in symbol table")
            return

        parameter_names = getattr(called_function, 'parameters', [])
        if not parameter_names:
            logging.warning(f"No parameter names found for function '{called_unique_name}'")
            return

        if called_unique_name not in self.parameter_type_map:
            self.parameter_type_map[called_unique_name] = {param: set() for param in parameter_names}

        for arg, param in zip(call_node.args, parameter_names):
            inferred_type = self.infer_type(arg)
            if inferred_type:
                self.parameter_type_map[called_unique_name][param].add(inferred_type)
                logging.debug(f"Inferred type for parameter '{param}' in function '{called_unique_name}': {inferred_type}")
            else:
                logging.debug(f"Could not infer type for parameter '{param}' in function '{called_unique_name}'")


    def get_called_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            attr_chain = []
            while isinstance(node, ast.Attribute):
                attr_chain.append(node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                attr_chain.append(node.id)
                attr_chain.reverse()
                full_name = '.'.join(attr_chain)
                logging.debug(f"Resolved attribute chain to '{full_name}'")
                return full_name
        elif isinstance(node, ast.Call):
            return self.get_called_name(node.func)
        return None

    def resolve_called_name(self, called_name):
        if '.' in called_name:
            parts = called_name.split('.')
            base = parts[0]
            attrs = parts[1:]

            if base == 'self':
                # Handle self.method
                attr_name = 'self.' + attrs[0]
                var_type = self.class_variable_types.get(attr_name)
                if var_type:
                    called_unique_name = var_type + '.' + '.'.join(attrs[1:])
                    logging.debug(f"Resolved 'self.{attrs[0]}' to '{var_type}' for call '{called_unique_name}'")
                else:
                    logging.warning(f"Could not resolve type for 'self.{attrs[0]}'")
                    return None
            else:
                var_type = self.variable_types.get(base) or self.class_variable_types.get(base)
                if var_type:
                    called_unique_name = var_type + '.' + '.'.join(attrs)
                    logging.debug(f"Resolved '{base}' to '{var_type}' for call '{called_unique_name}'")
                else:
                    if base in self.local_namespace:
                        base_unique_name = self.local_namespace[base]
                        called_unique_name = base_unique_name + '.' + '.'.join(attrs)
                        logging.debug(f"Resolved '{base}' via local namespace to '{called_unique_name}'")
                    else:
                        # If base is not in local_namespace, check if it's a built-in
                        if base in BUILT_IN_FUNCTIONS:
                            logging.debug(f"Identified '{base}' as a built-in function. Skipping.")
                            return None
                        called_unique_name = self.module_name + '.' + called_name
                        logging.debug(f"Resolved '{called_name}' via module context to '{called_unique_name}'")

            called_element = self.symbol_table.get(called_unique_name)
            if isinstance(called_element, Code):
                return called_element
            else:
                logging.warning(f"Called element '{called_unique_name}' is not a Code instance")
                return None
        else:
            if called_name in self.local_namespace:
                called_unique_name = self.local_namespace[called_name]
                logging.debug(f"Resolved global function '{called_name}' to '{called_unique_name}'")
            else:
                # If called_name is a built-in function, skip
                if called_name in BUILT_IN_FUNCTIONS:
                    logging.debug(f"Identified '{called_name}' as a built-in function. Skipping.")
                    return None
                called_unique_name = self.module_name + '.' + called_name
                logging.debug(f"Resolved global function '{called_name}' to '{called_unique_name}'")

            called_element = self.symbol_table.get(called_unique_name)
            if isinstance(called_element, Code):
                return called_element
            else:
                logging.warning(f"Called element '{called_unique_name}' is not a Code instance")
                return None


    def visit_Attribute(self, node):
        if self.current_function:
            if isinstance(node.value, ast.Name):
                var_name = node.value.id
                attr_name = var_name + '.' + node.attr

                if var_name == 'self':
                    full_attr_name = 'self.' + node.attr
                    data_element = self.symbol_table.get(self.current_class + '.' + node.attr)
                    if data_element and isinstance(data_element, Data):
                        self.accesses.append({
                            'accessor': self.current_function,
                            'accessed': data_element.unique_name,
                            'isWrite': False,
                            'isRead': True,
                            'isDependent': True
                        })
                        logging.debug(f"Recorded access to '{data_element.unique_name}' by '{self.current_function}'")
                else:
                    # Check if var_name is a parameter with inferred type
                    current_func_params = self.parameter_type_map.get(self.current_function, {})
                    if var_name in current_func_params:
                        inferred_types = current_func_params[var_name]
                        if len(inferred_types) == 1:
                            var_type = next(iter(inferred_types))
                            full_attr_name = var_type + '.' + node.attr
                            data_element = self.symbol_table.get(full_attr_name)
                            if data_element and isinstance(data_element, Data):
                                self.accesses.append({
                                    'accessor': self.current_function,
                                    'accessed': data_element.unique_name,
                                    'isWrite': False,
                                    'isRead': True,
                                    'isDependent': True
                                })
                                logging.debug(f"Recorded access to '{data_element.unique_name}' by '{self.current_function}'")
                        elif len(inferred_types) > 1:
                            # Choose one for simplicity
                            var_type = next(iter(inferred_types))
                            full_attr_name = var_type + '.' + node.attr
                            data_element = self.symbol_table.get(full_attr_name)
                            if data_element and isinstance(data_element, Data):
                                self.accesses.append({
                                    'accessor': self.current_function,
                                    'accessed': data_element.unique_name,
                                    'isWrite': False,
                                    'isRead': True,
                                    'isDependent': True
                                })
                                logging.debug(f"Recorded access to '{data_element.unique_name}' by '{self.current_function}'")
                            logging.warning(f"Parameter '{var_name}' in function '{self.current_function}' has multiple inferred types. Assigned '{var_type}'")
                    else:
                        var_type = self.variable_types.get(var_name) or self.class_variable_types.get(var_name)
                        if var_type:
                            full_attr_name = var_type + '.' + node.attr
                            data_element = self.symbol_table.get(full_attr_name)
                            if data_element and isinstance(data_element, Data):
                                self.accesses.append({
                                    'accessor': self.current_function,
                                    'accessed': data_element.unique_name,
                                    'isWrite': False,
                                    'isRead': True,
                                    'isDependent': True
                                })
                                logging.debug(f"Recorded access to '{data_element.unique_name}' by '{self.current_function}'")
        self.generic_visit(node)

    def visit_Name(self, node):
        if self.current_function:
            name = node.id
            unique_name = self.module_name + '.' + name
            data_element = self.symbol_table.get(unique_name)
            if data_element and isinstance(data_element, Data):
                self.accesses.append({
                    'accessor': self.current_function,
                    'accessed': data_element.unique_name,
                    'isWrite': False,
                    'isRead': True,
                    'isDependent': True
                })
                logging.debug(f"Recorded access to '{data_element.unique_name}' by '{self.current_function}'")
        self.generic_visit(node)

def load_config(config_file='config_python2mse.txt'):
    config = {}
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    return config

def main():
    config = load_config()

    if 'base_path' in config:
        base_path = config['base_path']
    else:
        base_path = input("Enter the base folder path: ")

    base_repo_name = os.path.basename(os.path.normpath(base_path))
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{base_repo_name}_{timestamp}.mse"

    if 'output_path' in config:
        output_path = config['output_path']
        output_file = os.path.join(output_path, output_filename)
    else:
        output_file = output_filename

    all_elements = {}
    all_parent_child_relations = []
    all_calls = []
    all_accesses = []

    symbol_table = {}

    # Initialize parameter_type_map
    parameter_type_map = {}

    # First pass: Collect definitions
    elements = {}
    parent_child_relations = []
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        source = f.read()
                    module_name = os.path.relpath(filepath, base_path).replace(os.sep, '.')
                    module_name = module_name[:-3]  # Remove '.py'
                    tree = ast.parse(source, filename=filepath)
                    collector = DefinitionCollector(filepath, module_name, base_path, symbol_table, elements, parent_child_relations)
                    collector.visit(tree)
                except Exception as e:
                    logging.error(f"Error processing file {filepath}: {e}")

    # Second pass: Analyze usages to build parameter_type_map
    calls_pass1 = []
    accesses_pass1 = []
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        source = f.read()
                    module_name = os.path.relpath(filepath, base_path).replace(os.sep, '.')
                    module_name = module_name[:-3]  # Remove '.py'
                    tree = ast.parse(source, filename=filepath)
                    analyzer = UsageAnalyzer(filepath, module_name, base_path, symbol_table, calls_pass1, accesses_pass1, parameter_type_map)
                    analyzer.visit(tree)
                except Exception as e:
                    logging.error(f"Error processing file {filepath}: {e}")

    # Assign inferred types to Code elements based on parameter_type_map
    for func_name, params in parameter_type_map.items():
        for param, types in params.items():
            if len(types) == 1:
                inferred_type = next(iter(types))
                function_element = symbol_table.get(func_name)
                if function_element and isinstance(function_element, Code):
                    function_element.inferred_parameter_types[param] = inferred_type
                    logging.debug(f"Assigned inferred type '{inferred_type}' to parameter '{param}' in function '{func_name}'")
            elif len(types) > 1:
                inferred_type = next(iter(types))  # Choose one for simplicity
                function_element = symbol_table.get(func_name)
                if function_element and isinstance(function_element, Code):
                    function_element.inferred_parameter_types[param] = inferred_type
                    logging.warning(f"Parameter '{param}' in function '{func_name}' has multiple inferred types: {types}. Assigned '{inferred_type}'")
            else:
                logging.warning(f"Parameter '{param}' in function '{func_name}' has no inferred type")

    # Third pass: Analyze usages again with parameter_type_map to resolve parameter types
    calls_pass2 = []
    accesses_pass2 = []
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        source = f.read()
                    module_name = os.path.relpath(filepath, base_path).replace(os.sep, '.')
                    module_name = module_name[:-3]  # Remove '.py'
                    tree = ast.parse(source, filename=filepath)
                    analyzer = UsageAnalyzer(filepath, module_name, base_path, symbol_table, calls_pass2, accesses_pass2, parameter_type_map)
                    analyzer.visit(tree)
                except Exception as e:
                    logging.error(f"Error processing file {filepath}: {e}")

    # Combine calls and accesses from both passes
    all_calls = calls_pass1 + calls_pass2
    all_accesses = accesses_pass1 + accesses_pass2

    # Assign IDs
    id_counter = 1
    id_mapping = {}
    for unique_name, elem in elements.items():
        elem.id = id_counter
        id_mapping[unique_name] = id_counter
        all_elements[id_counter] = elem
        id_counter += 1

    # Map parent-child relations
    for relation in parent_child_relations:
        parent_id = id_mapping.get(relation['parent'])
        child_id = id_mapping.get(relation['child'])
        if parent_id and child_id:
            all_parent_child_relations.append({'parent': parent_id, 'child': child_id, 'isMain': relation['isMain']})

    # Map calls correctly without modifying the list during iteration
    mapped_calls = []
    for call in all_calls:
        caller_id = id_mapping.get(call['caller'])
        called_id = id_mapping.get(call['called'])
        if caller_id and called_id:
            mapped_calls.append({'caller': caller_id, 'called': called_id})

    # Map accesses correctly without modifying the list during iteration
    mapped_accesses = []
    for access in all_accesses:
        accessor_id = id_mapping.get(access['accessor'])
        accessed_id = id_mapping.get(access['accessed'])
        if accessor_id and accessed_id:
            mapped_accesses.append({
                'accessor': accessor_id,
                'accessed': accessed_id,
                'isWrite': access['isWrite'],
                'isRead': access['isRead'],
                'isDependent': access['isDependent']
            })

    # Write output to .mse file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('(\n')
        for elem in all_elements.values():
            if isinstance(elem, Grouping):
                f.write(f'(SOMIX.Grouping (id: {elem.id} )\n')
                f.write(f'  (name \'{elem.name}\')\n')
                f.write(f'  (uniqueName \'{elem.unique_name}\')\n')
                f.write(f'  (technicalType \'{elem.technical_type}\')\n')
                if elem.link_to_editor:
                    f.write(f'  (linkToEditor \'{elem.link_to_editor}\')\n')
                f.write(')\n')
            elif isinstance(elem, Code):
                f.write(f'(SOMIX.Code (id: {elem.id} )\n')
                f.write(f'  (name \'{elem.name}\')\n')
                f.write(f'  (technicalType \'{elem.technical_type}\')\n')
                f.write(f'  (uniqueName \'{elem.unique_name}\')\n')
                if elem.link_to_editor:
                    f.write(f'  (linkToEditor \'{elem.link_to_editor}\')\n')
                f.write(')\n')
            elif isinstance(elem, Data):
                f.write(f'(SOMIX.Data (id: {elem.id} )\n')
                f.write(f'  (name \'{elem.name}\')\n')
                f.write(f'  (technicalType \'{elem.technical_type}\')\n')
                f.write(f'  (uniqueName \'{elem.unique_name}\')\n')
                if elem.link_to_editor:
                    f.write(f'  (linkToEditor \'{elem.link_to_editor}\')\n')
                f.write(')\n')

        for relation in all_parent_child_relations:
            f.write('(SOMIX.ParentChild\n')
            f.write(f'  (parent (ref: {relation["parent"]}))\n')
            f.write(f'  (child (ref: {relation["child"]}))\n')
            f.write(f'  (isMain {"true" if relation["isMain"] else "false"})\n')
            f.write(')\n')

        for call in mapped_calls:
            f.write('(SOMIX.Call\n')
            f.write(f'  (caller (ref: {call["caller"]}))\n')
            f.write(f'  (called (ref: {call["called"]}))\n')
            f.write(')\n')

        for access in mapped_accesses:
            f.write('(SOMIX.Access\n')
            f.write(f'  (accessor (ref: {access["accessor"]}))\n')
            f.write(f'  (accessed (ref: {access["accessed"]}))\n')
            f.write(f'  (isWrite {"true" if access["isWrite"] else "false"})\n')
            f.write(f'  (isRead {"true" if access["isRead"] else "false"})\n')
            f.write(f'  (isDependent {"true" if access["isDependent"] else "false"})\n')
            f.write(')\n')

        f.write(')\n')



if __name__ == '__main__':
    main()
