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
