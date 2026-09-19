@echo off
rem Build FancyAnalyzer.exe.  If FancyAnalyzer.ico is present it becomes the exe's icon;
rem otherwise the build proceeds with the default icon.
rem
rem Deliberately NOT --windowed -- this is a console build.  --windowed would drop the console
rem (losing the taskbar entry that carries the icon during the long run) and can leave sys.stdout
rem as None.  FancyAnalyzer now also opens its own live log window, but the console build is kept
rem so there is a taskbar icon and a working stdout.
if exist FancyAnalyzer.ico (
    .venv\Scripts\pyinstaller.exe --onefile --log-level=DEBUG --icon=FancyAnalyzer.ico FancyAnalyzer.py
) else (
    echo No FancyAnalyzer.ico found -- building with the default icon.
    .venv\Scripts\pyinstaller.exe --onefile --log-level=DEBUG FancyAnalyzer.py
)
