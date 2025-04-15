import os, pathlib

if __name__ == "__main__":
    project_root = pathlib.Path(__file__).parent.resolve()
    os.system(f'{project_root}/venv/Scripts/python.exe {project_root}/bot.py')
