import os, pathlib, platform

if __name__ == "__main__":
    project_root = pathlib.Path(__file__).parent.resolve()
    match platform.system():
        case 'Windows':
            os.system(f'{project_root}/venv/Scripts/python.exe {project_root}/bot.py')
        case 'Linux':
            os.system(f'{project_root}/venv/bin/python3 {project_root}/bot.py')
