import os
import ast
import datetime
import logging
import argparse
import textwrap
from argparse import HelpFormatter

VERSION = "0.1.2"

def setup_logging(debug):
    if debug:
        logging.basicConfig(
            filename='.python2somix.log',
            filemode='w',
            level=logging.DEBUG, 
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        logging.debug("Debugging mode active")
    else:
        logging.basicConfig(
            filename='.python2somix.log',
            filemode='w',
            level=logging.INFO, 
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

# Define a set of built-in functions to exclude them from being treated as user-defined
BUILT_IN_FUNCTIONS = {
    'len', 'range', 'int', 'str', 'float', 'bool', 'list',
    'dict', 'set', 'tuple', 'open', 'enumerate', 'zip', 'map', 'filter',
    'sum', 'min', 'max', 'abs', 'round', 'sorted', 'reversed', 'any',
    'all', 'type', 'isinstance', 'issubclass', 'getattr', 'setattr',
    'hasattr', 'delattr', 'globals', 'locals', 'dir', 'id', 'eval',
    'exec', 'compile', 'vars', 'globals', 'locals', 'help' #, 'input', 'print',
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
        self.parameters = []  # To store code parameters
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

        # **Map short unique name (base_module.class_name) to the same element**
        base_module_name = self.module_name.split('.')[-1]
        short_unique_name = f"{base_module_name}.{name}"
        self.symbol_table[short_unique_name] = class_element
        logging.debug(f"Mapped short unique name '{short_unique_name}' to '{unique_name}'")

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

        # **Map short unique name (base_module.class_name.function_name or base_module.function_name) to the same element**
        base_module_name = self.module_name.split('.')[-1]
        if self.current_class:
            class_name = self.current_class.name
            short_unique_name = f"{base_module_name}.{class_name}.{name}"
        else:
            short_unique_name = f"{base_module_name}.{name}"
        self.symbol_table[short_unique_name] = code_element
        logging.debug(f"Mapped short unique name '{short_unique_name}' to '{unique_name}'")

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
                        technical_type = 'PythonVariable'
                        link_to_editor = self.get_link(node.lineno, node.col_offset)

                        if unique_attr_name not in self.elements:
                            data_element = Data(None, attr_name, unique_attr_name, technical_type, link_to_editor)
                            self.elements[unique_attr_name] = data_element
                            self.symbol_table[unique_attr_name] = data_element

                            # **Parent is the class, not the method**
                            parent = self.current_class  # Changed from self.scope_stack[-1]
                            self.parent_child_relations.append({'parent': parent.unique_name, 'child': unique_attr_name, 'isMain': True})
                            parent.children.append(data_element)

                            logging.debug(f"Collected class attribute '{unique_attr_name}'")

                            # **Map short unique name (base_module.class_name.attribute) to the same element**
                            base_module_name = self.module_name.split('.')[-1]
                            class_name = self.current_class.name
                            short_unique_name = f"{base_module_name}.{class_name}.{attr_name}"
                            self.symbol_table[short_unique_name] = data_element
                            logging.debug(f"Mapped short unique name '{short_unique_name}' to '{unique_attr_name}'")
        # Handle instance-level attributes (inside a function)
        elif self.current_class and self.current_function:
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    if isinstance(target.value, ast.Name) and target.value.id == 'self':
                        attr_name = target.attr
                        unique_attr_name = f"{self.current_class.unique_name}.{attr_name}"
                        technical_type = 'PythonVariable'
                        link_to_editor = self.get_link(node.lineno, node.col_offset)

                        if unique_attr_name not in self.elements:
                            data_element = Data(None, attr_name, unique_attr_name, technical_type, link_to_editor)
                            self.elements[unique_attr_name] = data_element
                            self.symbol_table[unique_attr_name] = data_element

                            # **Parent is the class, not the method**
                            parent = self.current_class  # Changed from self.scope_stack[-1]
                            self.parent_child_relations.append({'parent': parent.unique_name, 'child': unique_attr_name, 'isMain': True})
                            parent.children.append(data_element)

                            logging.debug(f"Collected instance attribute '{unique_attr_name}'")

                            # **Map short unique name (base_module.class_name.attribute) to the same element**
                            base_module_name = self.module_name.split('.')[-1]
                            class_name = self.current_class.name
                            short_unique_name = f"{base_module_name}.{class_name}.{attr_name}"
                            self.symbol_table[short_unique_name] = data_element
                            logging.debug(f"Mapped short unique name '{short_unique_name}' to '{unique_attr_name}'")
        self.generic_visit(node)

class UsageAnalyzer(ast.NodeVisitor):
    def __init__(self, filename, module_name, base_path, symbol_table, calls, accesses, parameter_type_map=None, add_external_code_callback=None):
        self.filename = filename
        self.module_name = module_name
        self.base_path = base_path
        self.symbol_table = symbol_table  # Shared symbol table
        self.calls = calls
        self.accesses = accesses
        self.parameter_type_map = parameter_type_map or {}

        self.scope_stack = []
        self.current_class = None
        self.current_code = None

        self.local_namespace = {}  # Map local names to fully qualified names
        self.variable_types = {}  # Map variable names to class names (within a function)
        self.class_variable_types = {}  # Map self attributes to types across the class

        # Callback to handle external code additions
        self.add_external_code_callback = add_external_code_callback

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

        logging.debug(f"Visiting code: {unique_name}")

        self.scope_stack.append(unique_name)
        self.current_code = unique_name

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
                        logging.debug(f"Assigned inferred type '{resolved_type.unique_name}' to parameter '{param_name}' in code '{unique_name}'")
                        # **Assign the inferred type to variable_types**
                        self.variable_types[param_name] = resolved_type.unique_name
                        logging.debug(f"Set variable_types['{param_name}'] = '{resolved_type.unique_name}'")
            else:
                # Attempt to infer type from existing parameter_type_map
                inferred_types = self.parameter_type_map.get(unique_name, {}).get(param_name)
                if inferred_types and len(inferred_types) == 1:
                    inferred_type = next(iter(inferred_types))
                    self.variable_types[param_name] = inferred_type
                    logging.debug(f"Inferred type '{inferred_type}' for parameter '{param_name}' in code '{unique_name}'")
                elif inferred_types and len(inferred_types) > 1:
                    inferred_type = next(iter(inferred_types))  # Choose one for simplicity
                    self.variable_types[param_name] = inferred_type
                    logging.warning(f"Parameter '{param_name}' in code '{unique_name}' has multiple inferred types: {inferred_types}. Assigned '{inferred_type}'")
                else:
                    self.variable_types[param_name] = None
                    logging.debug(f"Parameter '{param_name}' has unknown type in code '{unique_name}'")

        self.generic_visit(node)

        # Merge self.variable_types into class_variable_types if applicable
        for var, var_type in self.variable_types.items():
            if var.startswith('self.'):
                self.class_variable_types[var] = var_type
                logging.debug(f"Inferred type for '{var}' in class '{self.current_class}': {var_type}")

        self.variable_types = {}

        self.scope_stack.pop()
        self.current_code = None

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
        if self.current_code:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    var_name = target.id
                    value = node.value
                    var_type = self.infer_type(value)
                    self.variable_types[var_name] = var_type
                    logging.debug(f"Inferred type for variable '{var_name}' in code '{self.current_code}': {var_type}")
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
                init_method_name = class_element.unique_name + '.__init__'
                init_method = self.symbol_table.get(init_method_name)
                if init_method and isinstance(init_method, Code):
                    self.calls.append({'caller': self.current_code, 'called': init_method.unique_name})
                    logging.debug(f"Recorded call from '{self.current_code}' to '__init__' of '{class_element.unique_name}'")
                return class_element.unique_name
            else:
                # Handle external code call
                external_unique_name = self.add_external_code(class_name)
                return external_unique_name
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
        logging.debug(f"Processing call to '{called_name}' in code '{self.current_code}'")
        if called_name:
            called_element = self.resolve_called_name(called_name)
            if called_element and isinstance(called_element, Code):
                if self.current_code:
                    self.calls.append({'caller': self.current_code, 'called': called_element.unique_name})
                    logging.debug(f"Recorded call from '{self.current_code}' to '{called_element.unique_name}'")
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
                logging.debug(f"Inferred type for parameter '{param}' in code '{called_unique_name}': {inferred_type}")
            else:
                logging.debug(f"Could not infer type for parameter '{param}' in code '{called_unique_name}'")

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
                if len(attrs) >= 1:
                    method_name = attrs[0]
                    called_unique_name = f"{self.current_class}.{method_name}"
                    logging.debug(f"Resolved 'self.{method_name}' to '{called_unique_name}'")
                    called_element = self.symbol_table.get(called_unique_name)
                    if isinstance(called_element, Code):
                        return called_element
                    else:
                        logging.warning(f"Called element '{called_unique_name}' is not a Code instance")
                        return None
                else:
                    logging.warning(f"Invalid method call format: '{called_name}'")
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
                    # Handle external code call
                    external_unique_name = self.add_external_code(called_unique_name)
                    return self.symbol_table.get(external_unique_name)
        else:
            if called_name in self.local_namespace:
                called_unique_name = self.local_namespace[called_name]
                logging.debug(f"Resolved global code name '{called_name}' to '{called_unique_name}'")
            else:
                # If called_name is a built-in function, skip
                if called_name in BUILT_IN_FUNCTIONS:
                    logging.debug(f"Identified '{called_name}' as a built-in function. Skipping.")
                    return None
                called_unique_name = self.module_name + '.' + called_name
                logging.debug(f"Resolved global code name '{called_name}' to '{called_unique_name}'")

            called_element = self.symbol_table.get(called_unique_name)
            if isinstance(called_element, Code):
                return called_element
            else:
                # Handle external code call
                external_unique_name = self.add_external_code(called_unique_name)
                return self.symbol_table.get(external_unique_name)

    def add_external_code(self, called_unique_name):
        """
        Adds external code to the model with 'extP2S' in uniqueName and without linkToEditor.
        uniqueName is built as 'extP2S.' + called_unique_name
        """
        if not called_unique_name:
            return None

        if called_unique_name in self.symbol_table:
            return called_unique_name  # Already added

        # Split the called_unique_name to extract all parts
        parts = called_unique_name.split('.')
        if len(parts) > 1:
            external_unique_name = 'extP2S.' + '.'.join(parts)
        else:
            external_unique_name = 'extP2S.' + parts[0]

        # Avoid duplicates
        if external_unique_name in self.symbol_table:
            return external_unique_name

        # Create a new Code element for external code
        external_code = Code(None, '.'.join(parts), external_unique_name, 'ExternalPythonFunction', link_to_editor=None)
        self.symbol_table[external_unique_name] = external_code
        self.calls.append({'caller': self.current_code, 'called': external_unique_name})
        logging.debug(f"Added external code '{external_unique_name}' called by '{self.current_code}'")

        # Add to elements via callback
        if self.add_external_code_callback:
            self.add_external_code_callback(external_code)

        return external_unique_name

    def visit_Attribute(self, node):
        if self.current_code:
            if isinstance(node.value, ast.Name):
                var_name = node.value.id
                attr_name = var_name + '.' + node.attr

                if var_name == 'self':
                    full_attr_name = 'self.' + node.attr
                    data_element = self.symbol_table.get(self.current_class + '.' + node.attr)
                    if data_element and isinstance(data_element, Data):
                        self.accesses.append({
                            'accessor': self.current_code,
                            'accessed': data_element.unique_name,
                            'isWrite': False,
                            'isRead': True,
                            'isDependent': True
                        })
                        logging.debug(f"Recorded access to '{data_element.unique_name}' by '{self.current_code}'")
                else:
                    # Check if var_name is a parameter with inferred type
                    current_func_params = self.parameter_type_map.get(self.current_code, {})
                    if var_name in current_func_params:
                        inferred_types = current_func_params[var_name]
                        if len(inferred_types) == 1:
                            var_type = next(iter(inferred_types))
                            full_attr_name = var_type + '.' + node.attr
                            data_element = self.symbol_table.get(full_attr_name)
                            if data_element and isinstance(data_element, Data):
                                self.accesses.append({
                                    'accessor': self.current_code,
                                    'accessed': data_element.unique_name,
                                    'isWrite': False,
                                    'isRead': True,
                                    'isDependent': True
                                })
                                logging.debug(f"Recorded access to '{data_element.unique_name}' by '{self.current_code}'")
                        elif len(inferred_types) > 1:
                            var_type = next(iter(inferred_types))  # Choose one for simplicity
                            full_attr_name = var_type + '.' + node.attr
                            data_element = self.symbol_table.get(full_attr_name)
                            if data_element and isinstance(data_element, Data):
                                self.accesses.append({
                                    'accessor': self.current_code,
                                    'accessed': data_element.unique_name,
                                    'isWrite': False,
                                    'isRead': True,
                                    'isDependent': True
                                })
                                logging.debug(f"Recorded access to '{data_element.unique_name}' by '{self.current_code}'")
                            logging.warning(f"Parameter '{var_name}' in code '{self.current_code}' has multiple inferred types. Assigned '{var_type}'")
                    else:
                        var_type = self.variable_types.get(var_name) or self.class_variable_types.get(var_name)
                        if var_type:
                            full_attr_name = var_type + '.' + node.attr
                            data_element = self.symbol_table.get(full_attr_name)
                            if data_element and isinstance(data_element, Data):
                                self.accesses.append({
                                    'accessor': self.current_code,
                                    'accessed': data_element.unique_name,
                                    'isWrite': False,
                                    'isRead': True,
                                    'isDependent': True
                                })
                                logging.debug(f"Recorded access to '{data_element.unique_name}' by '{self.current_code}'")
        self.generic_visit(node)

    def visit_Name(self, node):
        if self.current_code:
            name = node.id
            unique_name = self.module_name + '.' + name
            data_element = self.symbol_table.get(unique_name)
            if data_element and isinstance(data_element, Data):
                self.accesses.append({
                    'accessor': self.current_code,
                    'accessed': data_element.unique_name,
                    'isWrite': False,
                    'isRead': True,
                    'isDependent': True
                })
                logging.debug(f"Recorded access to '{data_element.unique_name}' by '{self.current_code}'")
        self.generic_visit(node)

def load_config(config_file='config_python2somix.txt'):
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

    class RawFormatter(HelpFormatter):
        def _fill_text(self, text, width, indent):
            return "\n".join([textwrap.fill(line, width) for line in textwrap.indent(textwrap.dedent(text), indent).splitlines()])

    program_descripton = """Extract Python code structure and usages to SOMIX format.
                                        
Enter path to the base folder containing Python source code files when prompted.    
The output .mse file will be saved in the same folder as the script by default.
Place a 'config_python2somix.txt' file in the same folder as the script to specify custom paths for base folder and output file.
The config file should contain the following lines: 
base_path = /path/to/base/folder
output_path = /path/to/output/folder
Use Moose2Model to visualize the .mse file.                                   
"""

    parser = argparse.ArgumentParser(description=program_descripton, formatter_class=RawFormatter)	
    parser.add_argument('-v', '--version', action='store_true', help='show the version and exit')
    parser.add_argument('--debug', action='store_true', help='enable debugging information in logs')
    
    args = parser.parse_args()

    if args.version:
        print(f"python2somix.py Version {VERSION}")
        return

    setup_logging(args.debug)

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

    # Callback function to add external code elements to 'all_elements'
    def add_external_code_element(external_code):
        all_elements[external_code.unique_name] = external_code
        logging.debug(f"External code '{external_code.unique_name}' added to all_elements")

    # First pass: Collect definitions
    logging.info(f"First pass: Collecting definitions from Python files in '{base_path}'")
    elements = {}
    parent_child_relations = []
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        source = f.read()
                    rel_path = os.path.relpath(filepath, base_path).replace(os.sep, '.')
                    module_name = base_repo_name + '.' + rel_path[:-3]  # Remove '.py'
                    tree = ast.parse(source, filename=filepath)
                    collector = DefinitionCollector(filepath, module_name, base_path, symbol_table, elements, parent_child_relations)
                    collector.visit(tree)
                except Exception as e:
                    logging.error(f"Error processing file {filepath}: {e}")

    # Second pass: Analyze usages to build parameter_type_map
    logging.info(f"Second pass: Analyzing usages to build parameter_type_map")
    calls_pass1 = []
    accesses_pass1 = []
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        source = f.read()
                    rel_path = os.path.relpath(filepath, base_path).replace(os.sep, '.')
                    module_name = base_repo_name + '.' + rel_path[:-3]  # Remove '.py'
                    tree = ast.parse(source, filename=filepath)
                    analyzer = UsageAnalyzer(filepath, module_name, base_path, symbol_table, calls_pass1, accesses_pass1, parameter_type_map, add_external_code_element)
                    analyzer.visit(tree)
                except Exception as e:
                    logging.error(f"Error processing file {filepath}: {e}")

    # Assign inferred types to Code elements based on parameter_type_map
    logging.info("Assigning inferred types to Code elements based on parameter_type_map")
    for func_name, params in parameter_type_map.items():
        for param, types in params.items():
            if len(types) == 1:
                inferred_type = next(iter(types))
                function_element = symbol_table.get(func_name)
                if function_element and isinstance(function_element, Code):
                    function_element.inferred_parameter_types[param] = inferred_type
                    logging.debug(f"Assigned inferred type '{inferred_type}' to parameter '{param}' in code '{func_name}'")
            elif len(types) > 1:
                inferred_type = next(iter(types))  # Choose one for simplicity
                function_element = symbol_table.get(func_name)
                if function_element and isinstance(function_element, Code):
                    function_element.inferred_parameter_types[param] = inferred_type
                    logging.warning(f"Parameter '{param}' in code '{func_name}' has multiple inferred types: {types}. Assigned '{inferred_type}'")
            else:
                logging.warning(f"Parameter '{param}' in code '{func_name}' has no inferred type")

    # Third pass: Analyze usages again with parameter_type_map to resolve parameter types
    logging.info("Third pass: Analyzing usages to resolve parameter types")
    calls_pass2 = []
    accesses_pass2 = []
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        source = f.read()
                    rel_path = os.path.relpath(filepath, base_path).replace(os.sep, '.')
                    module_name = base_repo_name + '.' + rel_path[:-3]  # Remove '.py'
                    tree = ast.parse(source, filename=filepath)
                    analyzer = UsageAnalyzer(filepath, module_name, base_path, symbol_table, calls_pass2, accesses_pass2, parameter_type_map, add_external_code_element)
                    analyzer.visit(tree)
                except Exception as e:
                    logging.error(f"Error processing file {filepath}: {e}")

    logging.info(f"Post-processing: Combining results from all three passes")

    # Combine calls and accesses from both passes
    all_calls = calls_pass1 + calls_pass2
    all_accesses = accesses_pass1 + accesses_pass2

    # Assign IDs
    id_counter = 1
    id_mapping = {}
    for unique_name, elem in elements.items():
        elem.id = id_counter
        id_mapping[unique_name] = id_counter
        all_elements[unique_name] = elem
        id_counter += 1

    # Include external codes in ID assignment
    for unique_name, elem in all_elements.items():
        if unique_name not in id_mapping:
            elem.id = id_counter
            id_mapping[unique_name] = id_counter
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
    logging.info(f"Writing output to '{output_file}'")
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
    logging.info("Finished processing Python code.")

if __name__ == '__main__':
    main()
