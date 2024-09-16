import logging
import os
import ast
import datetime

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s:%(message)s'
)

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
        self.parameters = {}  # param_name: type

class Data(Element):
    def __init__(self, id, name, unique_name, technical_type, link_to_editor=None):
        super().__init__(id, name, unique_name, technical_type, link_to_editor)
        self.accessed_by = []

class DefinitionCollector(ast.NodeVisitor):
    def __init__(self, filepath, module_name, base_path, symbol_table, elements, parent_child_relations):
        self.filepath = filepath
        self.module_name = module_name
        self.base_path = base_path
        self.symbol_table = symbol_table
        self.elements = elements
        self.parent_child_relations = parent_child_relations
        self.current_class = None
        self.current_function = None
        self.local_namespace = {}  # Map local names to fully qualified names

    def get_link(self, lineno, col_offset):
        col = col_offset + 1
        filepath = os.path.abspath(self.filepath).replace('\\', '/')
        return f'vscode://file/{filepath}/:{lineno}:{col}'

    def visit_Module(self, node):
        name = os.path.basename(self.filepath)
        unique_name = self.module_name
        technical_type = 'PythonFile'
        link_to_editor = self.get_link(getattr(node, 'lineno', 1), 0)

        module_element = Grouping(None, name, unique_name, technical_type, link_to_editor)
        self.symbol_table[unique_name] = module_element
        self.elements[unique_name] = module_element
        module_element.is_main = True
        self.parent_child_relations.append({
            'parent': None,  # Modules may not have a parent
            'child': unique_name,
            'isMain': True
        })
        self.current_class = None
        self.current_function = None
        self.generic_visit(node)

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
        class_name = node.name
        unique_name = self.module_name + '.' + class_name
        grouping = Grouping(
            name=class_name,
            technical_type='class',
            unique_name=unique_name,
            link_to_editor=None
        )
        self.symbol_table[unique_name] = grouping
        self.elements[unique_name] = grouping

        self.parent_child_relations.append({
            'parent': self.module_name,
            'child': unique_name,
            'isMain': False
        })

        self.current_class = unique_name
        self.current_function = None  # Reset current_function when entering a class
        self.generic_visit(node)
        self.current_class = None

    def visit_FunctionDef(self, node):
        func_name = node.name
        if self.current_class:
            unique_name = self.current_class + '.' + func_name
        else:
            unique_name = self.module_name + '.' + func_name

        code = Code(
            name=func_name,
            technical_type='method' if self.current_class else 'function',
            unique_name=unique_name,
            link_to_editor=None
        )
        code.parameters = {arg.arg: None for arg in node.args.args}
        self.symbol_table[unique_name] = code
        self.elements[unique_name] = code

        parent = self.current_class if self.current_class else self.module_name
        self.parent_child_relations.append({
            'parent': parent,
            'child': unique_name,
            'isMain': False
        })

        self.current_function = unique_name

        self.generic_visit(node)

        self.current_function = None

    def visit_Assign(self, node):
        parent = self.current_class if self.current_class else self.module_name
        for target in node.targets:
            if isinstance(target, ast.Name):
                name = target.id
                if self.current_function:
                    unique_name = self.current_function + '.' + name
                elif self.current_class:
                    unique_name = self.current_class + '.' + name
                else:
                    unique_name = self.module_name + '.' + name
                technical_type = 'PythonVariable'
                link_to_editor = self.get_link(getattr(node, 'lineno', 1), target.col_offset)

                data_element = Data(None, name, unique_name, technical_type, link_to_editor)
                self.elements[unique_name] = data_element

                if not self.current_function:
                    self.symbol_table[unique_name] = data_element

                self.parent_child_relations.append({
                    'parent': parent,
                    'child': unique_name,
                    'isMain': True
                })

            elif isinstance(target, ast.Attribute):
                if isinstance(target.value, ast.Name) and target.value.id == 'self':
                    name = target.attr
                    unique_name = self.current_class + '.' + name
                    technical_type = 'PythonVariable'
                    link_to_editor = self.get_link(getattr(node, 'lineno', 1), target.col_offset)

                    data_element = Data(None, name, unique_name, technical_type, link_to_editor)
                    self.elements[unique_name] = data_element

                    self.symbol_table[unique_name] = data_element

                    self.parent_child_relations.append({
                        'parent': self.current_class,
                        'child': unique_name,
                        'isMain': True
                    })
        self.generic_visit(node)

class UsageAnalyzer(ast.NodeVisitor):
    def __init__(self, filename, module_name, base_path, symbol_table, calls, accesses, param_type_assignments):
        self.filename = filename
        self.module_name = module_name
        self.base_path = base_path
        self.symbol_table = symbol_table
        self.calls = calls
        self.accesses = accesses
        self.param_type_assignments = param_type_assignments

        self.scope_stack = []
        self.current_class = None
        self.current_function = None

        self.local_namespace = {}  
        self.variable_types = {}  
        self.class_variable_types = {}  

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

        self.scope_stack.append(unique_name)
        self.current_function = unique_name

        self.variable_types = {}

        code_element = self.symbol_table.get(unique_name)
        if code_element and isinstance(code_element, Code):
            for param_name, param_type in code_element.parameters.items():
                self.variable_types[param_name] = param_type

        self.generic_visit(node)

        for var, var_type in self.variable_types.items():
            if var.startswith('self.'):
                self.class_variable_types[var] = var_type

        self.variable_types = {}

        self.scope_stack.pop()
        self.current_function = None

    def visit_Assign(self, node):
        if self.current_function:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    var_type = self.infer_type(node.value)
                    if var_type:
                        self.variable_types[name] = var_type
                elif isinstance(target, ast.Attribute):
                    if isinstance(target.value, ast.Name) and target.value.id == 'self':
                        name = 'self.' + target.attr
                        var_type = self.infer_type(node.value)
                        if var_type:
                            self.class_variable_types[name] = var_type
        self.generic_visit(node)

    def visit_Call(self, node):
        called_name = self.get_called_name(node.func)
        logging.info(f"visit_Call - Called name: {called_name}")

        built_in_functions = {'print', 'len', 'range', 'str', 'int', 'float', 'list', 'dict', 'set', 'tuple', 'open'}
        
        if called_name in built_in_functions:
            logging.debug(f"Ignoring built-in function call: {called_name}")
            self.generic_visit(node)
            return

        called_element = self.resolve_called_name(called_name)
        logging.info(f"Resolved called element: {called_element}")
        if called_element and isinstance(called_element, Code):
            if self.current_function:
                self.calls.append({'caller': self.current_function, 'called': called_element.unique_name})
        
            args = node.args
            param_names = list(called_element.parameters.keys())
            for i, arg in enumerate(args):
                if i < len(param_names):
                    param_name = param_names[i]
                    arg_type = self.infer_argument_type(arg)
                    if arg_type and self.param_type_assignments[called_element.unique_name].get(param_name) != arg_type:
                        self.param_type_assignments[called_element.unique_name][param_name] = arg_type
                        logging.debug(f"Assigned type '{arg_type}' to parameter '{param_name}' in '{called_element.unique_name}'")
        
        self.generic_visit(node)

    def infer_argument_type(self, arg):
        if isinstance(arg, ast.Name):
            var_name = arg.id
            var_type = self.variable_types.get(var_name)
            if var_type:
                return var_type
            var_type = self.class_variable_types.get(var_name)
            if var_type:
                return var_type
        elif isinstance(arg, ast.Call):
            return self.infer_type(arg)
        elif isinstance(arg, ast.Attribute):
            if isinstance(arg.value, ast.Name):
                base_name = arg.value.id
                if base_name == 'self':
                    attr_name = 'self.' + arg.attr
                    var_type = self.class_variable_types.get(attr_name)
                    if var_type:
                        return var_type
        return None

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
                return full_class_name
        elif isinstance(value, ast.Name):
            var_name = value.id
            if var_name in self.variable_types:
                return self.variable_types[var_name]
            if var_name in self.class_variable_types:
                return self.class_variable_types[var_name]
        return None

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
            return self.get_called_name(node.func)
        return None

    def resolve_called_name(self, called_name):
        if '.' in called_name:
            parts = called_name.split('.')
            base = parts[0]
            attrs = parts[1:]
        else:
            base = called_name
            attrs = []

        if base == 'self':
            if not attrs:
                logging.warning(f"No attribute specified after 'self' in called name '{called_name}'.")
                return None
            attr_name = 'self.' + attrs[0]
            var_type = self.class_variable_types.get(attr_name)
            if var_type:
                called_unique_name = var_type + '.' + '.'.join(attrs[1:]) if len(attrs) > 1 else var_type + '.' + attrs[0]
            else:
                return None
        else:
            var_type = self.variable_types.get(base) or self.class_variable_types.get(base)
            if var_type:
                called_unique_name = var_type + '.' + '.'.join(attrs) if attrs else var_type
            else:
                if base in self.local_namespace:
                    base_unique_name = self.local_namespace[base]
                else:
                    base_unique_name = self.module_name + '.' + base
                called_unique_name = base_unique_name + '.' + '.'.join(attrs) if attrs else base_unique_name

        called_element = self.symbol_table.get(called_unique_name)
        if isinstance(called_element, Code):
            logging.debug(f"Resolved '{called_name}' to '{called_element.unique_name}'")
            return called_element
        else:
            if isinstance(called_element, Grouping) and attrs:
                method_name = attrs[-1]
                method_unique_name = called_element.unique_name + '.' + method_name
                method_element = self.symbol_table.get(method_unique_name)
                if isinstance(method_element, Code):
                    logging.debug(f"Resolved '{called_name}' to '{method_element.unique_name}'")
                    return method_element
            logging.warning(f"Called element '{called_unique_name}' not found in symbol table or is not a Code element.")
            return None

    def resolve_class_name(self, class_name):
        if not class_name:
            return None

        if class_name in self.symbol_table:
            class_element = self.symbol_table.get(class_name)
            if isinstance(class_element, Grouping):
                return class_element

        if class_name in self.local_namespace:
            resolved_name = self.local_namespace[class_name]
            class_element = self.symbol_table.get(resolved_name)
            if isinstance(class_element, Grouping):
                return class_element

        current_module_prefix = self.module_name + '.' + class_name
        class_element = self.symbol_table.get(current_module_prefix)
        if isinstance(class_element, Grouping):
            return class_element

        logging.warning(f"Class '{class_name}' could not be resolved in symbol table.")
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
                    module_name = module_name[:-3]
                    tree = ast.parse(source, filename=filepath)
                    collector = DefinitionCollector(filepath, module_name, base_path, symbol_table, elements, parent_child_relations)
                    collector.visit(tree)
                except Exception as e:
                    logging.error(f"Error processing file {filepath}: {e}")

    param_type_assignments = {unique_name: {} for unique_name, elem in elements.items() if isinstance(elem, Code)}

    max_iterations = 5
    iteration = 0
    changed = True

    while changed and iteration < max_iterations:
        logging.info(f"Starting usage analysis iteration {iteration + 1}")
        changed = False
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
                        module_name = module_name[:-3]
                        tree = ast.parse(source, filename=filepath)
                        analyzer = UsageAnalyzer(
                            filepath,
                            module_name,
                            base_path,
                            symbol_table,
                            calls,
                            accesses,
                            param_type_assignments
                        )
                        analyzer.visit(tree)
                    except Exception as e:
                        logging.error(f"Error processing file {filepath}: {e}")

        for func_unique_name, params in param_type_assignments.items():
            func_element = symbol_table.get(func_unique_name)
            if func_element and isinstance(func_element, Code):
                for param_name, param_type in params.items():
                    if func_element.parameters.get(param_name) != param_type:
                        func_element.parameters[param_name] = param_type
                        changed = True
                        logging.debug(f"Updated parameter '{param_name}' in '{func_unique_name}' to type '{param_type}'")

        iteration += 1

    all_calls.extend(calls)
    all_accesses.extend(accesses)

    id_counter = 1
    id_mapping = {}
    for unique_name, elem in elements.items():
        elem.id = id_counter
        id_mapping[unique_name] = id_counter
        all_elements[id_counter] = elem
        id_counter += 1

    for relation in parent_child_relations:
        parent_id = id_mapping.get(relation['parent'])
        child_id = id_mapping.get(relation['child'])
        if parent_id and child_id:
            all_parent_child_relations.append({'parent': parent_id, 'child': child_id, 'isMain': relation['isMain']})

    mapped_calls = []
    for call in all_calls:
        caller_id = id_mapping.get(call['caller'])
        called_id = id_mapping.get(call['called'])
        if caller_id and called_id:
            mapped_calls.append({'caller': caller_id, 'called': called_id})

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

    logging.info(f"Extraction completed. Output written to {output_file}")


if __name__ == '__main__':
    main()
