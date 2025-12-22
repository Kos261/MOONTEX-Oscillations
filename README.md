### How to use this program

1. Install uv from https://docs.astral.sh/uv/

2. Enter project directory

3. Use ```uv sync``` to setup virtual enviroment and download required python version and libraries

4. Use either command line interface (CLI) or graphical interface (GUI)

5. To convert to exe use 
```powershell
uv run python -m PyInstaller --onefile --name Oscillator --add-binary "drivers\libusb-1.0.dll;." "<Project_path>\Oscylacje\Oscillator_CLI.py"```