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
