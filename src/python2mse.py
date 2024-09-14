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
        self.calls = []
        self.accesses = []

class Data(Element):
    def __init__(self, id, name, unique_name, technical_type, link_to_editor=None):
        super().__init__(id, name, unique_name, technical_type, link_to_editor)
        self.accessed_by = []

class PythonExtractor(ast.NodeVisitor):
    def __init__(self, filename, module_name, base_path, symbol_table):
        self.filename = filename
        self.module_name = module_name
        self.base_path = base_path
        self.symbol_table = symbol_table  # Shared symbol table

        self.scope_stack = []
        self.current_class = None
        self.current_function = None

        self.elements = {}
        self.id_counter = 1
        self.parent_child_relations = []
        self.calls = []
        self.accesses = []

    def new_id(self):
        id = self.id_counter
        self.id_counter += 1
        return id

    def get_link(self, lineno, col_offset):
        col = col_offset + 1
        filepath = os.path.abspath(self.filename).replace('\\', '/')
        return f'vscode://file/{filepath}/:{lineno}:{col}'

    def visit_Module(self, node):
        id = self.new_id()
        name = os.path.basename(self.filename)
        unique_name = self.module_name
        technical_type = 'PythonFile'
        link_to_editor = self.get_link(getattr(node, 'lineno', 1), 0)

        module_element = Grouping(id, name, unique_name, technical_type, link_to_editor)
        self.elements[id] = module_element
        module_element.is_main = True
        self.scope_stack.append(module_element)

        self.generic_visit(node)

        self.scope_stack.pop()

    def visit_ClassDef(self, node):
        id = self.new_id()
        name = node.name
        unique_name = self.module_name + '.' + name
        technical_type = 'PythonClass'
        link_to_editor = self.get_link(node.lineno, node.col_offset)

        class_element = Grouping(id, name, unique_name, technical_type, link_to_editor)
        self.elements[id] = class_element

        # Add to symbol table
        self.symbol_table[unique_name] = class_element

        parent = self.scope_stack[-1]
        self.parent_child_relations.append({'parent': parent.id, 'child': id, 'isMain': True})
        parent.children.append(class_element)

        self.scope_stack.append(class_element)
        self.current_class = class_element

        self.generic_visit(node)

        self.scope_stack.pop()
        self.current_class = None

    def visit_FunctionDef(self, node):
        id = self.new_id()
        name = node.name
        if self.current_class:
            unique_name = self.module_name + '.' + self.current_class.name + '.' + name
            technical_type = 'PythonMethod'
        else:
            unique_name = self.module_name + '.' + name
            technical_type = 'PythonFunction'
        link_to_editor = self.get_link(node.lineno, node.col_offset)

        code_element = Code(id, name, unique_name, technical_type, link_to_editor)
        self.elements[id] = code_element

        # Add to symbol table
        self.symbol_table[unique_name] = code_element

        parent = self.scope_stack[-1]
        self.parent_child_relations.append({'parent': parent.id, 'child': id, 'isMain': True})
        parent.children.append(code_element)

        self.scope_stack.append(code_element)
        self.current_function = code_element

        self.generic_visit(node)

        self.scope_stack.pop()
        self.current_function = None

    def visit_Assign(self, node):
        if isinstance(self.scope_stack[-1], Grouping):
            # At the module or class level
            if self.current_class:
                # Class attribute
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        id = self.new_id()
                        name = target.id
                        unique_name = self.module_name + '.' + self.current_class.name + '.' + name
                        technical_type = 'PythonVariable'
                        link_to_editor = self.get_link(node.lineno, node.col_offset)

                        data_element = Data(id, name, unique_name, technical_type, link_to_editor)
                        self.elements[id] = data_element

                        # Add to symbol table
                        self.symbol_table[unique_name] = data_element

                        parent = self.current_class
                        self.parent_child_relations.append({'parent': parent.id, 'child': id, 'isMain': True})
                        parent.children.append(data_element)
            else:
                # Global variable
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        id = self.new_id()
                        name = target.id
                        unique_name = self.module_name + '.' + name
                        technical_type = 'PythonVariable'
                        link_to_editor = self.get_link(node.lineno, node.col_offset)

                        data_element = Data(id, name, unique_name, technical_type, link_to_editor)
                        self.elements[id] = data_element

                        # Add to symbol table
                        self.symbol_table[unique_name] = data_element

                        parent = self.scope_stack[-1]
                        self.parent_child_relations.append({'parent': parent.id, 'child': id, 'isMain': True})
                        parent.children.append(data_element)
            # Do not record accesses at the module or class level
        elif isinstance(self.scope_stack[-1], Code):
            # Inside a function/method
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    if isinstance(target.value, ast.Name) and target.value.id == 'self':
                        # Instance attribute
                        name = target.attr
                        unique_name = self.module_name + '.' + self.current_class.name + '.' + name
                        technical_type = 'PythonVariable'
                        link_to_editor = self.get_link(node.lineno, node.col_offset)

                        # Check if the variable already exists
                        data_element = None
                        for child in self.current_class.children:
                            if isinstance(child, Data) and child.name == name:
                                data_element = child
                                break
                        if data_element is None:
                            id = self.new_id()
                            data_element = Data(id, name, unique_name, technical_type, link_to_editor)
                            self.elements[id] = data_element
                            # Add to symbol table
                            self.symbol_table[unique_name] = data_element

                            parent = self.current_class
                            self.parent_child_relations.append({'parent': parent.id, 'child': id, 'isMain': True})
                            parent.children.append(data_element)
                        # Record the access with accessor being a Code element
                        self.accesses.append({'accessor': self.current_function.unique_name, 'accessed': data_element.unique_name, 'isWrite': True, 'isRead': False, 'isDependent': True})

        self.generic_visit(node)

    def visit_Call(self, node):
        # Get the fully qualified name of the called function/method
        called_name = self.get_called_name(node.func)
        if called_name:
            # Try to resolve the called function/method in the symbol table
            called_element = self.resolve_called_name(called_name)
            if called_element and isinstance(called_element, Code):
                if self.current_function:
                    # Record the call with unique names
                    self.calls.append({'caller': self.current_function.unique_name, 'called': called_element.unique_name})
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
            # For cases like method chaining
            return self.get_called_name(node.func)
        return None

    def resolve_called_name(self, called_name):
        # Handle 'self' references
        if called_name.startswith('self.'):
            if self.current_class:
                called_unique_name = self.module_name + '.' + self.current_class.name + '.' + called_name[len('self.'):]
            else:
                return None
        else:
            # Attempt to resolve global names
            called_unique_name = called_name
            if '.' not in called_unique_name:
                # Prepend module name if necessary
                called_unique_name = self.module_name + '.' + called_unique_name

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
                unique_name = self.module_name + '.' + self.current_class.name + '.' + name
                # Try to find the data element
                data_element = self.symbol_table.get(unique_name)
                if data_element and isinstance(data_element, Data):
                    # Record the access
                    self.accesses.append({'accessor': self.current_function.unique_name, 'accessed': data_element.unique_name, 'isWrite': False, 'isRead': True, 'isDependent': True})
        self.generic_visit(node)

    def visit_Name(self, node):
        if self.current_function:
            # Check if the name refers to a global variable
            name = node.id
            unique_name = self.module_name + '.' + name
            data_element = self.symbol_table.get(unique_name)
            if data_element and isinstance(data_element, Data):
                # Record the access
                self.accesses.append({'accessor': self.current_function.unique_name, 'accessed': data_element.unique_name, 'isWrite': False, 'isRead': True, 'isDependent': True})
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

    # First pass to collect all elements and build the symbol table
    extractors = []
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
                    extractor = PythonExtractor(filepath, module_name, base_path, symbol_table)
                    extractor.visit(tree)
                    extractors.append(extractor)
                except Exception as e:
                    print(f"Error processing file {filepath}: {e}")

    # Second pass to assign unique IDs and collect relations
    id_counter = 1
    id_mapping_global = {}
    for extractor in extractors:
        id_mapping = {}
        for id, elem in extractor.elements.items():
            new_id = id_counter
            id_counter += 1
            elem.id = new_id
            all_elements[new_id] = elem
            id_mapping[id] = new_id
            id_mapping_global[elem.unique_name] = new_id

        # Update parent-child relations
        for relation in extractor.parent_child_relations:
            relation['parent'] = id_mapping[relation['parent']]
            relation['child'] = id_mapping[relation['child']]
            all_parent_child_relations.append(relation)

    # Now process calls and accesses
    for extractor in extractors:
        for call in extractor.calls:
            caller_id = id_mapping_global.get(call['caller'])
            called_id = id_mapping_global.get(call['called'])
            if caller_id and called_id:
                all_calls.append({'caller': caller_id, 'called': called_id})

        for access in extractor.accesses:
            accessor_id = id_mapping_global.get(access['accessor'])
            accessed_id = id_mapping_global.get(access['accessed'])
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
