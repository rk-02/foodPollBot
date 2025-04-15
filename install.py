import os, pathlib

if __name__ == "__main__":
    project_root = pathlib.Path(__file__).parent.resolve()
    os.system('py -3.13 -m venv ./venv')
    os.system(f'{project_root}/venv/Scripts/pip.exe install -r requirements.txt')
