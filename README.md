# Python2SOMIX
Extract SOMIX model from Python code

## How to run
start the script in the terminal with 
```batch
python .\python2mse.py
```
The script will ask for the path to the folder where the python code is saved.

You may place a configuration file in the same folder as python2mse.py to specify which folder is to be read and where the output file is to be placed:

Exact name of the file: config_python2mse.txt

```batch
# Configuration file
base_path=/path/to/your/base/folder
output_path=/path/to/output/directory
```
To find usages of methods when the instance is passed to a parameter, you have to annotate the import parameter (Here that is belongs to ClassOne):

```python
    def method_three(self, my_obj: ClassOne):
        # To check that usage is also found when ClassOne is passed as an argument
        my_obj.method_one()
```
## Automatic test

Do an automatic test with 

```batch
...\Python2SOMIX\src> python .\test_extraction.py
```

This test generates the subfolder test with test coding and compares the expected mse file expected_output.mse with the extracted file test(date_time).mse.
Adapt this coding when the logic is changed. The test ignores the exact order of entries and the exact value of the id.

## Documentation

See [/src/documentation.md](https://github.com/Moose2Model/Python2SOMIX/blob/main/src/documentation.md).
