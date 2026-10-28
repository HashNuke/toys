Import("env")
from pathlib import Path
project = Path(env.subst("$PROJECT_DIR"))
root = project.parent
identity = root / "firmware/identity"
if not (identity / "BoardIdentity.h").is_file():
    raise RuntimeError("Enroll the board first: uv run python -m board_runtime init")
env.Append(CPPPATH=[str(identity)])
source = (project / "src/main.cpp").read_text()
if '#include <BoardApp.h>' not in source or 'void appSetup(' not in source or 'void appLoop(' not in source:
    raise RuntimeError("Every board app must use BoardApp.h with appSetup/appLoop to retain serial updates and Bluetooth provisioning")
