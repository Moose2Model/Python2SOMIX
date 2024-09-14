import os
import ast
import datetime

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
        self.children = []  # Added to store variables within functions if needed
        self.calls = []
        self.accesses = []

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

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.name
            asname = alias.asname if alias.asname else name
            self.local_namespace[asname] = name
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module
        for alias in node.names:
            name = alias.name
            asname = alias.asname if alias.asname else name
            full_name = module + '.' + name if module else name
            self.local_namespace[asname] = full_name
        self.generic_visit(node)

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

        self.generic_visit(node)

        self.scope_stack.pop()
        self.current_function = None

    def visit_Assign(self, node):
        parent = self.scope_stack[-1]
        for target in node.targets:
            if isinstance(target, ast.Name):
                # Variable assignment
                name = target.id
                if self.current_function:
                    # Local variable within a function
                    unique_name = self.current_function.unique_name + '.' + name
                    technical_type = 'PythonVariable'
                    link_to_editor = self.get_link(node.lineno, node.col_offset)

                    data_element = Data(None, name, unique_name, technical_type, link_to_editor)
                    self.elements[unique_name] = data_element

                    # Optionally add to symbol table
                    # self.symbol_table[unique_name] = data_element

                    self.parent_child_relations.append({'parent': self.current_function.unique_name, 'child': unique_name, 'isMain': True})
                    self.current_function.children.append(data_element)
                elif self.current_class:
                    # Class variable
                    unique_name = self.current_class.unique_name + '.' + name
                    technical_type = 'PythonVariable'
                    link_to_editor = self.get_link(node.lineno, node.col_offset)

                    data_element = Data(None, name, unique_name, technical_type, link_to_editor)
                    self.elements[unique_name] = data_element

                    # Add to symbol table
                    self.symbol_table[unique_name] = data_element

                    self.parent_child_relations.append({'parent': self.current_class.unique_name, 'child': unique_name, 'isMain': True})
                    self.current_class.children.append(data_element)
                else:
                    # Global variable
                    unique_name = self.module_name + '.' + name
                    technical_type = 'PythonVariable'
                    link_to_editor = self.get_link(node.lineno, node.col_offset)

                    data_element = Data(None, name, unique_name, technical_type, link_to_editor)
                    self.elements[unique_name] = data_element

                    # Add to symbol table
                    self.symbol_table[unique_name] = data_element

                    self.parent_child_relations.append({'parent': parent.unique_name, 'child': unique_name, 'isMain': True})
                    parent.children.append(data_element)

            elif isinstance(target, ast.Attribute):
                if isinstance(target.value, ast.Name) and target.value.id == 'self':
                    # Instance attribute (e.g., self.attribute)
                    name = target.attr
                    unique_name = self.current_class.unique_name + '.' + name
                    technical_type = 'PythonVariable'
                    link_to_editor = self.get_link(node.lineno, node.col_offset)

                    data_element = Data(None, name, unique_name, technical_type, link_to_editor)
                    self.elements[unique_name] = data_element

                    # Add to symbol table
                    self.symbol_table[unique_name] = data_element

                    self.parent_child_relations.append({'parent': self.current_class.unique_name, 'child': unique_name, 'isMain': True})
                    self.current_class.children.append(data_element)
        self.generic_visit(node)

class UsageAnalyzer(ast.NodeVisitor):
    def __init__(self, filename, module_name, base_path, symbol_table, calls, accesses):
        self.filename = filename
        self.module_name = module_name
        self.base_path = base_path
        self.symbol_table = symbol_table  # Shared symbol table
        self.calls = calls
        self.accesses = accesses

        self.scope_stack = []
        self.current_class = None
        self.current_function = None

        self.local_namespace = {}  # Map local names to fully qualified names
        self.variable_types = {}  # Map variable names to class names (within a function)

    def visit_Module(self, node):
        self.scope_stack.append(self.module_name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.name
            asname = alias.asname if alias.asname else name
            self.local_namespace[asname] = name
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module
        for alias in node.names:
            name = alias.name
            asname = alias.asname if alias.asname else name
            full_name = module + '.' + name if module else name
            self.local_namespace[asname] = full_name
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        name = node.name
        unique_name = self.module_name + '.' + name

        self.scope_stack.append(unique_name)
        self.current_class = unique_name

        self.generic_visit(node)

        self.scope_stack.pop()
        self.current_class = None

    def visit_FunctionDef(self, node):
        name = node.name
        if self.current_class:
            unique_name = self.current_class + '.' + name
        else:
            unique_name = self.module_name + '.' + name

        self.scope_stack.append(unique_name)
        self.current_function = unique_name

        # Initialize variable types for this function
        self.variable_types = {}

        # Collect parameter types if type annotations are available
        args = node.args
        if args.args:
            for arg in args.args:
                if arg.annotation:
                    param_name = arg.arg
                    param_type = self.get_annotation_name(arg.annotation)
                    if param_type:
                        class_element = self.resolve_class_name(param_type)
                        if class_element:
                            self.variable_types[param_name] = class_element.unique_name

        self.generic_visit(node)

        # Clear variable types when exiting the function
        self.variable_types = {}

        self.scope_stack.pop()
        self.current_function = None

    def get_annotation_name(self, annotation):
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Attribute):
            return self.get_called_name(annotation)
        return None

    def visit_Assign(self, node):
        if self.current_function:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    # Variable assignment
                    value = node.value
                    if isinstance(value, ast.Call):
                        # Handle class instantiation
                        class_name = self.get_called_name(value.func)
                        class_element = self.resolve_class_name(class_name)
                        if class_element:
                            full_class_name = class_element.unique_name
                            # Record variable type
                            self.variable_types[target.id] = full_class_name
                            # Record the call to __init__
                            init_method_name = full_class_name + '.__init__'
                            init_method = self.symbol_table.get(init_method_name)
                            if init_method and isinstance(init_method, Code):
                                self.calls.append({'caller': self.current_function, 'called': init_method.unique_name})
                    else:
                        # Handle other assignments
                        pass
                elif isinstance(target, ast.Attribute):
                    if isinstance(target.value, ast.Name) and target.value.id == 'self':
                        # Instance attribute assignment
                        name = target.attr
                        value = node.value
                        if isinstance(value, ast.Call):
                            class_name = self.get_called_name(value.func)
                            class_element = self.resolve_class_name(class_name)
                            if class_element:
                                full_class_name = class_element.unique_name
                                # Record variable type
                                self.variable_types['self.' + name] = full_class_name
                                # Record the call to __init__
                                init_method_name = full_class_name + '.__init__'
                                init_method = self.symbol_table.get(init_method_name)
                                if init_method and isinstance(init_method, Code):
                                    self.calls.append({'caller': self.current_function, 'called': init_method.unique_name})
        self.generic_visit(node)

    def resolve_class_name(self, class_name):
        if class_name in self.local_namespace:
            class_unique_name = self.local_namespace[class_name]
        else:
            class_unique_name = self.module_name + '.' + class_name
        class_element = self.symbol_table.get(class_unique_name)
        if isinstance(class_element, Grouping):
            return class_element
        else:
            return None

    def visit_Call(self, node):
        # Get the fully qualified name of the called function/method
        called_name = self.get_called_name(node.func)
        if called_name:
            # Try to resolve the called function/method in the symbol table
            called_element = self.resolve_called_name(called_name)
            if called_element and isinstance(called_element, Code):
                if self.current_function:
                    # Record the call with unique names
                    self.calls.append({'caller': self.current_function, 'called': called_element.unique_name})
        self.generic_visit(node)

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
                return '.'.join(attr_chain)
            elif isinstance(node, ast.Call):
                # Handle chained calls
                return self.get_called_name(node)
            elif isinstance(node, ast.Attribute):
                # Handle nested attributes
                return self.get_called_name(node)
        elif isinstance(node, ast.Call):
            # For cases like method chaining
            return self.get_called_name(node.func)
        return None

    def resolve_called_name(self, called_name):
        if '.' in called_name:
            parts = called_name.split('.')
            base = parts[0]
            attrs = parts[1:]
            if base == 'self':
                if self.current_class:
                    # Check if 'self.attribute' has a known type
                    attr_name = 'self.' + attrs[0]
                    if attr_name in self.variable_types:
                        class_unique_name = self.variable_types[attr_name]
                        called_unique_name = class_unique_name + '.' + '.'.join(attrs[1:])
                    else:
                        # Try to find method in the current class
                        called_unique_name = self.current_class + '.' + '.'.join(attrs)
                else:
                    return None
            elif base in self.variable_types:
                # Variable is an instance of a known class
                class_unique_name = self.variable_types[base]
                called_unique_name = class_unique_name + '.' + '.'.join(attrs)
            else:
                # Try to resolve base from local namespace
                if base in self.local_namespace:
                    base_unique_name = self.local_namespace[base]
                else:
                    base_unique_name = self.module_name + '.' + base
                called_unique_name = base_unique_name + '.' + '.'.join(attrs)
        else:
            # Check if called_name is in local namespace
            if called_name in self.local_namespace:
                called_unique_name = self.local_namespace[called_name]
            else:
                # Attempt to resolve global names
                called_unique_name = self.module_name + '.' + called_name

        # Check if the called_unique_name is in the symbol table and is a Code element
        called_element = self.symbol_table.get(called_unique_name)
        if isinstance(called_element, Code):
            return called_element
        else:
            return None  # Ignore if it's not a Code element

    def visit_Attribute(self, node):
        if self.current_function:
            if isinstance(node.value, ast.Name) and node.value.id == 'self':
                # Accessing an instance attribute
                name = node.attr
                unique_name = self.current_class + '.' + name
                # Try to find the data element
                data_element = self.symbol_table.get(unique_name)
                if data_element and isinstance(data_element, Data):
                    # Record the access
                    self.accesses.append({'accessor': self.current_function, 'accessed': data_element.unique_name, 'isWrite': False, 'isRead': True, 'isDependent': True})
            elif isinstance(node.value, ast.Name):
                var_name = node.value.id
                if var_name in self.variable_types:
                    class_unique_name = self.variable_types[var_name]
                    attr_name = class_unique_name + '.' + node.attr
                    data_element = self.symbol_table.get(attr_name)
                    if data_element and isinstance(data_element, Data):
                        self.accesses.append({'accessor': self.current_function, 'accessed': data_element.unique_name, 'isWrite': False, 'isRead': True, 'isDependent': True})
        self.generic_visit(node)

    def visit_Name(self, node):
        if self.current_function:
            # Check if the name refers to a global variable
            name = node.id
            unique_name = self.module_name + '.' + name
            data_element = self.symbol_table.get(unique_name)
            if data_element and isinstance(data_element, Data):
                # Record the access
                self.accesses.append({'accessor': self.current_function, 'accessed': data_element.unique_name, 'isWrite': False, 'isRead': True, 'isDependent': True})
        self.generic_visit(node)

def main():
    base_path = input("Enter the base folder path: ")
    base_repo_name = os.path.basename(os.path.normpath(base_path))
    output_filename = datetime.datetime.now().strftime(f"%Y-%m-%d_%H-%M_{base_repo_name}.mse")

    all_elements = {}
    all_parent_child_relations = []
    all_calls = []
    all_accesses = []

    # Global symbol table
    symbol_table = {}

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
                    print(f"Error processing file {filepath}: {e}")

    # Second pass: Analyze usages
    calls = []
    accesses = []
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
                    analyzer = UsageAnalyzer(filepath, module_name, base_path, symbol_table, calls, accesses)
                    analyzer.visit(tree)
                except Exception as e:
                    print(f"Error processing file {filepath}: {e}")

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

    # Map calls and accesses
    for call in calls:
        caller_id = id_mapping.get(call['caller'])
        called_id = id_mapping.get(call['called'])
        if caller_id and called_id:
            all_calls.append({'caller': caller_id, 'called': called_id})

    for access in accesses:
        accessor_id = id_mapping.get(access['accessor'])
        accessed_id = id_mapping.get(access['accessed'])
        if accessor_id and accessed_id:
            all_accesses.append({
                'accessor': accessor_id,
                'accessed': accessed_id,
                'isWrite': access['isWrite'],
                'isRead': access['isRead'],
                'isDependent': access['isDependent']
            })

    # Write output to .mse file
    with open(output_filename, 'w', encoding='utf-8') as f:
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

        for call in all_calls:
            f.write('(SOMIX.Call\n')
            f.write(f'  (caller (ref: {call["caller"]}))\n')
            f.write(f'  (called (ref: {call["called"]}))\n')
            f.write(')\n')

        for access in all_accesses:
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
