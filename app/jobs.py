import os
import subprocess
from datetime import datetime

from app.settings import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

DUMPS_DIR = "/app/dumps"

def dump_db():
    os.makedirs(DUMPS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(DUMPS_DIR, f"dump_{ts}.sql.gz")

    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD


    cmd = (
        f"pg_dump -h {DB_HOST} -p {DB_PORT} -U {DB_USER} -d {DB_NAME} | gzip > {out_file}"
    )
    subprocess.run(cmd, shell=True, check=True, env=env)

    print(f"[dump_db] OK -> {out_file}")