# Databricks notebook source
# MAGIC %md
# MAGIC # Load Sample XMLs into the Landing Volume
# MAGIC
# MAGIC Copies the canonical sample files from the deployed bundle's workspace
# MAGIC files into `${catalog}.${landing_schema}.scr_xml`, one subdirectory per
# MAGIC CADOC (`3040/`, `3050/`, `4010/`, `4016/`, `2011/`). The bronze pipelines
# MAGIC pick them up via Auto Loader (`pathGlobFilter Doc<cadoc>_*.xml`).
# MAGIC
# MAGIC | CADOC | Documento | Formato | Datas-base do sample |
# MAGIC |---|---|---|---|
# MAGIC | 3040 | Operações de crédito individualizadas | XML | 2026-03, 2026-04 |
# MAGIC | 3050 | Estoque mensal agregado (TXB V11) | XML | 2026-03 |
# MAGIC | 4010 | Balancete Patrimonial Analítico (mensal) | XML + posicional legado | 2026-03, 2026-04 (+ 2024-12 `.txt`) |
# MAGIC | 4016 | Balanço Patrimonial Analítico (semestral) | XML | 2025-06, 2025-12 |
# MAGIC | 2011 | DDR — parcelas de requerimento de capital e limites operacionais (**diário**) | XML | 2026-03-27/30/31, 2026-04-01/02 |
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
# CADOC 4010 (Balancete Patrimonial Analítico, mensal) e 4016 (Balanço
# Patrimonial Analítico, semestral) compartilham o MESMO leiaute XML oficial
# (IN BCB 469/2024, obrigatório a partir da data-base jan/2025). Uma subpasta por
# documento — cada um tem seu bronze próprio (`raw_4010.py` / `raw_4016.py`)
# com checkpoint independente.
# Os `.txt` posicionais legados (data-base < jan/2025) também vivem aqui.
DEST_4010 = f"{VOLUME_ROOT}/4010"
DEST_4016 = f"{VOLUME_ROOT}/4016"
# CADOC 2011 (DDR) — o único documento DIÁRIO do acelerador, por isso o sample
# tem vários arquivos por mês (`Doc2011_<cnpj>_<AAAA-MM-DD>.xml`).
DEST_2011 = f"{VOLUME_ROOT}/2011"

print(f"Catalog:        {CATALOG}")
print(f"Landing schema: {LANDING}")
print(f"Source dir:     {SOURCE_DIR}")
for _label, _dest in (("3040", DEST_3040), ("3050", DEST_3050),
                      ("4010", DEST_4010), ("4016", DEST_4016),
                      ("2011", DEST_2011)):
    print(f"Dest {_label}:      {_dest}")

# COMMAND ----------

# Volume already declared by the bundle (resources/uc_assets.yml -> volumes.scr_xml),
# but the 3040/ 3050/ 4010/ 4016/ 2011/ subdirectories are runtime artifacts. Create via FUSE.
for _dest in (DEST_3040, DEST_3050, DEST_4010, DEST_4016, DEST_2011):
    os.makedirs(_dest, exist_ok=True)

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

# COSIF — leiaute XML oficial (data-base ≥ jan/2025) …
print("Copying Doc 4010 samples (Doc4010_*.xml)…")
copy_pattern("Doc4010_*.xml", DEST_4010, "4010")

print("Copying Doc 4016 samples (Doc4016_*.xml)…")
copy_pattern("Doc4016_*.xml", DEST_4016, "4016")

# CADOC 2011 (DDR) — diário, um arquivo por data-base.
print("Copying Doc 2011 samples (Doc2011_*.xml)…")
copy_pattern("Doc2011_*.xml", DEST_2011, "2011")

# … e o posicional legado (data-base < jan/2025), quando houver.
print("Copying legacy positional COSIF samples (Doc4010_*.txt / Doc4016_*.txt)…")
copy_pattern("Doc4010_*.txt", DEST_4010, "4010-legado")
copy_pattern("Doc4016_*.txt", DEST_4016, "4016-legado")

# COMMAND ----------

print("Sample files ready under:")
for sub, label in ((DEST_3040, "3040"), (DEST_3050, "3050"),
                   (DEST_4010, "4010"), (DEST_4016, "4016"),
                   (DEST_2011, "2011")):
    print(f"  {label}: {sub}")
    for f in sorted(os.listdir(sub)):
        print(f"    - {f}")
