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

import glob
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
# CADOC 4010 (Balancete COSIF) chega como CSV (tabular), não XML. Mesmo volume,
# subpasta própria — o bronze 4010 lê via Auto Loader CSV.
DEST_4010 = f"{VOLUME_ROOT}/4010"

print(f"Catalog:        {CATALOG}")
print(f"Landing schema: {LANDING}")
print(f"Source dir:     {SOURCE_DIR}")
print(f"Dest 3040:      {DEST_3040}")
print(f"Dest 3050:      {DEST_3050}")
print(f"Dest 4010:      {DEST_4010}")

# COMMAND ----------

# Volume already declared by the bundle (resources/uc_assets.yml -> volumes.scr_xml),
# but the 3040/ 3050/ 4010/ subdirectories are runtime artifacts. Create them via FUSE.
os.makedirs(DEST_3040, exist_ok=True)
os.makedirs(DEST_3050, exist_ok=True)
os.makedirs(DEST_4010, exist_ok=True)

# COMMAND ----------

def copy_pattern(pattern: str, dest_dir: str, label: str) -> list[str]:
    """Copia todos os arquivos do `SOURCE_DIR` que casam com `pattern` (glob)
    para `dest_dir`. Permite adicionar samples didáticos novos (e.g.
    `Doc3040_*_2026-04_R1_P1.xml`) sem editar este notebook."""
    matches = sorted(glob.glob(os.path.join(SOURCE_DIR, pattern)))
    if not matches:
        print(f"  [{label}] nenhum match para {pattern!r} — pulando.")
        return []
    copied = []
    for src in matches:
        name = os.path.basename(src)
        dest = os.path.join(dest_dir, name)
        shutil.copyfile(src, dest)
        size = os.path.getsize(dest)
        print(f"  [{label}] copied {name} -> {dest} ({size:,} bytes)")
        copied.append(dest)
    return copied


print("Copying Doc 3040 samples (Doc3040_*.xml)…")
copy_pattern("Doc3040_*.xml", DEST_3040, "3040")

print("Copying Doc 3050 samples (Doc3050_*.xml)…")
copy_pattern("Doc3050_*.xml", DEST_3050, "3050")

print("Copying Doc 4010 samples (Doc4010_*.txt)…")
copy_pattern("Doc4010_*.txt", DEST_4010, "4010")

# COMMAND ----------

print("Sample files ready under:")
for sub, label in ((DEST_3040, "3040"), (DEST_3050, "3050"), (DEST_4010, "4010")):
    print(f"  {label}: {sub}")
    for f in sorted(os.listdir(sub)):
        print(f"    - {f}")
