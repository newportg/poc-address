import os
import shutil
import subprocess


if os.path.isfile("/run/host-ca/ca.crt"):
    shutil.copyfile("/run/host-ca/ca.crt", "/usr/local/share/ca-certificates/host-ca.crt")
    subprocess.run(["update-ca-certificates"], check=True, stdout=subprocess.DEVNULL)
    os.environ["LOQATE_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"

os.execvp(
    "uvicorn",
    [
        "uvicorn",
        "main:app",
        "--host",
        "0.0.0.0",
        "--port",
        os.getenv("PORT", "8001"),
    ],
)
