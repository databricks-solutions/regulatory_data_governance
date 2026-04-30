# Databricks notebook source
# MAGIC %md
# MAGIC # Load Sample XMLs into the Landing Volume
# MAGIC
# MAGIC Copies the canonical Doc 3040 / Doc 3050 sample XMLs from the deployed
# MAGIC bundle's workspace files into `${catalog}.${landing_schema}.scr_xml`
# MAGIC under `3040/` and `3050/` subdirectories. The bronze pipelines pick them
# MAGIC up via Auto Loader (`pathGlobFilter Doc3040_*.xml` and `Doc3050_*.xml`).
# MAGIC
# MAGIC Idempotent — overwrites the destination files on every run, so the
# MAGIC schema/checkpoint state in `_checkpoints/` won't double-ingest existing
# MAGIC files (Auto Loader dedupes by path+modificationTime).
# MAGIC
# MAGIC Inputs (job parameters):
# MAGIC   - `catalog`          : Unity Catalog name (e.g. `rc18_catalog`)
# MAGIC   - `landing_schema`   : Landing schema name (resolved from the bundle)
# MAGIC   - `source_dir`       : Workspace files path containing the XMLs
# MAGIC                          (typically `${workspace.file_path}/sample`)

# COMMAND ----------

import os
import shutil

dbutils.widgets.text("catalog", "rc18_catalog", "Unity Catalog")
dbutils.widgets.text("landing_schema", "landing", "Landing Schema")
dbutils.widgets.text("source_dir", "", "Source directory (workspace files path with the sample XMLs)")

CATALOG = dbutils.widgets.get("catalog")
LANDING = dbutils.widgets.get("landing_schema")
SOURCE_DIR = dbutils.widgets.get("source_dir")

if not SOURCE_DIR:
    raise ValueError("source_dir is required — pass ${workspace.file_path}/sample from the bundle.")

VOLUME_ROOT = f"/Volumes/{CATALOG}/{LANDING}/scr_xml"
DEST_3040 = f"{VOLUME_ROOT}/3040"
DEST_3050 = f"{VOLUME_ROOT}/3050"

print(f"Catalog:        {CATALOG}")
print(f"Landing schema: {LANDING}")
print(f"Source dir:     {SOURCE_DIR}")
print(f"Dest 3040:      {DEST_3040}")
print(f"Dest 3050:      {DEST_3050}")

# COMMAND ----------

# Volume already declared by the bundle (resources/uc_assets.yml -> volumes.scr_xml),
# but the 3040/ and 3050/ subdirectories are runtime artifacts. Create them via FUSE.
os.makedirs(DEST_3040, exist_ok=True)
os.makedirs(DEST_3050, exist_ok=True)

# COMMAND ----------

def copy_one(src_name: str, dest_dir: str) -> str:
    src = os.path.join(SOURCE_DIR, src_name)
    dest = os.path.join(dest_dir, src_name)
    if not os.path.isfile(src):
        raise FileNotFoundError(f"Sample file not found: {src}")
    shutil.copyfile(src, dest)
    size = os.path.getsize(dest)
    print(f"  copied {src_name} -> {dest} ({size:,} bytes)")
    return dest


print("Copying Doc 3040 sample…")
copy_one("Doc3040_99999999_2026-03_R1_P1.xml", DEST_3040)

print("Copying Doc 3050 sample…")
copy_one("Doc3050_99999999_2026-03_R1_P1.xml", DEST_3050)

# COMMAND ----------

print("Sample XMLs ready under:")
for sub, label in ((DEST_3040, "3040"), (DEST_3050, "3050")):
    print(f"  {label}: {sub}")
    for f in sorted(os.listdir(sub)):
        print(f"    - {f}")
