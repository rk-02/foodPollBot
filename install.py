import os, pathlib, platform

if __name__ == "__main__":
    project_root = pathlib.Path(__file__).parent.resolve()
    os.system('python3.13 -m venv ./venv')
    match platform.system():
        case 'Windows':
            os.system(f'{project_root}/venv/Scripts/pip.exe install -r requirements.txt')
        case 'Linux':
            os.system(f'{project_root}/venv/bin/pip install -r requirements.txt')
