from __future__ import annotations

import os
import sys
from pathlib import Path


APP_URL = os.getenv("DESKTOP_APP_URL", "http://127.0.0.1:8000/")
WINDOW_TITLE = os.getenv("DESKTOP_APP_TITLE", "RFID Local MVP")


def _inject_system_python_paths() -> None:
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    candidates = [
        Path("/usr/lib/python3/dist-packages"),
        Path(f"/usr/lib/python{version}/dist-packages"),
        Path("/usr/lib64/python3/dist-packages"),
        Path(f"/usr/lib64/python{version}/dist-packages"),
    ]
    for candidate in candidates:
        candidate_str = str(candidate)
        if candidate.exists() and candidate_str not in sys.path:
            sys.path.append(candidate_str)


def main() -> None:
    _inject_system_python_paths()
    try:
        import webview
    except Exception as exc:
        raise SystemExit(
            "pywebview backend is unavailable. Install python3-gi, "
            "gir1.2-webkit2-4.1 and pip install -r requirements.txt."
        ) from exc

    window = webview.create_window(
        title=WINDOW_TITLE,
        url=APP_URL,
        width=1280,
        height=900,
        min_size=(960, 720),
        text_select=False,
        background_color="#081420",
    )
    if window is None:
        raise SystemExit("Failed to create desktop window.")
    webview.start(gui="gtk", debug=False, private_mode=False)


if __name__ == "__main__":
    main()
