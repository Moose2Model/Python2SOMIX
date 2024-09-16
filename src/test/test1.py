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

