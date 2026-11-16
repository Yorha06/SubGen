import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = (
    "https://github.com/jerryshell/whisper.cpp-windows-vulkan-bin/"
    "releases/download/v1.0.0/whisper.cpp-windows-vulkan.zip"
)
INSTALL_DIR = Path(__file__).resolve().parent / "tools" / "whisper.cpp"
ARCHIVE_PATH = INSTALL_DIR / "whisper.cpp-windows-vulkan.zip"


def main() -> int:
    print("Mengunduh whisper.cpp Windows Vulkan...", flush=True)
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(
        URL, headers={"User-Agent": "SubGen"}
    )
    downloaded = 0
    download_complete = False
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length", "0"))
            with ARCHIVE_PATH.open("wb") as archive_file:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    archive_file.write(chunk)
                    downloaded += len(chunk)
                    if downloaded % (10 * 1024 * 1024) < len(chunk):
                        if total:
                            print(
                                f"Terunduh {downloaded // (1024 * 1024)} MB"
                                f" dari {total // (1024 * 1024)} MB...",
                                flush=True,
                            )
                        else:
                            print(
                                f"Terunduh {downloaded // (1024 * 1024)} MB...",
                                flush=True,
                            )
        download_complete = True
    finally:
        if not download_complete:
            ARCHIVE_PATH.unlink(missing_ok=True)
    if downloaded == 0:
        raise OSError("Server mengirim arsip kosong.")

    with zipfile.ZipFile(ARCHIVE_PATH) as archive:
        root = INSTALL_DIR.resolve()
        for member in archive.infolist():
            destination = (INSTALL_DIR / member.filename).resolve()
            if not destination.is_relative_to(root):
                raise ValueError(f"Path arsip tidak aman: {member.filename}")
        archive.extractall(INSTALL_DIR)

    executables = list(INSTALL_DIR.rglob("whisper-cli.exe"))
    if not executables:
        raise FileNotFoundError(
            "Arsip berhasil diekstrak, tetapi whisper-cli.exe tidak ditemukan."
        )

    executable = executables[0]
    if executable.parent != INSTALL_DIR:
        for item in executable.parent.iterdir():
            destination = INSTALL_DIR / item.name
            if item.is_file():
                shutil.copy2(item, destination)
        shutil.copy2(executable, INSTALL_DIR / executable.name)

    print(f"whisper.cpp siap: {INSTALL_DIR / 'whisper-cli.exe'}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"Gagal memasang whisper.cpp: {error}", file=sys.stderr)
        sys.exit(1)