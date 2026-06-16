"""
archive_manager.py
Compresses processed data older than N days into zip archives.
"""

import os
import shutil
from datetime import datetime, timedelta

from config import PROCESSED_DIR, ARCHIVE_DIR


def archive_old_data(days=3):
    if not os.path.exists(PROCESSED_DIR):
        return

    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    now = datetime.utcnow()

    for folder in os.listdir(PROCESSED_DIR):
        folder_path = os.path.join(PROCESSED_DIR, folder)

        if not os.path.isdir(folder_path):
            continue

        try:
            folder_date = datetime.strptime(folder, "%Y-%m-%d")
        except ValueError:
            continue

        if (now - folder_date).days >= days:
            archive_path = os.path.join(ARCHIVE_DIR, folder)
            print(f"[ARCHIVE] Compressing {folder} → {archive_path}.zip")

            shutil.make_archive(archive_path, "zip", folder_path)
            shutil.rmtree(folder_path)

            print(f"[ARCHIVE] Done: {archive_path}.zip")


if __name__ == "__main__":
    archive_old_data()
