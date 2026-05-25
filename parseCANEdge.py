import os
import argparse
from pathlib import Path
from asammdf import MDF

# === HELPERS ===

def safe_stem(path: Path) -> str:
    # Keep filename without extension; handle weird names safely
    return path.stem

def normalize_to_bus_logging(mf4_path: Path) -> MDF:
    """Try to normalize to CAN bus logging; if that yields 0 groups, fall back to raw conversion."""
    m = MDF(str(mf4_path))

    # First try: bus-logging (raw). Some MF4s won't map to CAN here (0 groups).
    try:
        n = m.extract_bus_logging(
            database_files={},           # required in your asammdf
            version='4.00',
            ignore_value2text_conversion=True,
        )
        if getattr(n, "groups", None) and len(n.groups) > 0:
            return n
        else:
            print(f"ℹ️  {mf4_path.name}: bus-logging yielded 0 groups; falling back to raw.")
    except Exception as e:
        print(f"ℹ️  {mf4_path.name}: bus-logging failed ({e}); falling back to raw.")

    # Fallback: keep original content but normalize MDF version (helps concatenation)
    try:
        return m.convert("4.10")   # or "4.00" – 4.10 tends to be safest for mixed sources
    except Exception:
        # If convert isn't available in your version, just return as-is
        return m


def decode_mf4_file(mf4_file, dbc_map, decoded_file_path):
    """Decode a single MF4 file using DBCs and save it."""
    try:
        print(f"\n📥 Decoding {mf4_file} ...")
        mdf = MDF(mf4_file)
        mdf = mdf.extract_bus_logging(
            database_files={"CAN": dbc_map},
            version='4.00',
            ignore_value2text_conversion=True,
        )
        MDF.save(mdf, decoded_file_path)
        print(f"✅ Decoded file saved as: {decoded_file_path}")
        return mdf 
    except Exception as e:
        print(f"❌ Failed to decode {mf4_file}: {e}")
        return None

# === CLI ARGUMENTS ===

parser = argparse.ArgumentParser(description="Merge, decode, and export MF4 files using DBCs")
parser.add_argument("--mf4-folder", dest="mf4_folder", default="./mf4", help="Folder containing MF4 files")
parser.add_argument("--dbc-folder", dest="dbc_folder", default="./dbc", help="Folder containing DBC files")
parser.add_argument("--merged-output", dest="merged_output", default=None, help="Filename for merged output MF4 (no extension)")
parser.add_argument("--decoded-output", dest="decoded_output", default=None, help="Filename for decoded output MF4 (no extension)")

args = parser.parse_args()

# Resolve paths
mf4_folder = Path(args.mf4_folder).resolve()
dbc_folder = Path(args.dbc_folder).resolve()

# Determine base directory (parent of raw mf4 folder)
base_dir = mf4_folder.parent

# Output dirs (create if needed)
merged_dir = base_dir / "merged"
decoded_dir = base_dir / "decoded"

merged_dir.mkdir(parents=True, exist_ok=True)
decoded_dir.mkdir(parents=True, exist_ok=True)

# Output file paths
if args.merged_output:
    merged_output_file = (merged_dir / args.merged_output).with_suffix(".mf4")
else:
    merged_output_file = merged_dir / "merged.mf4"

if args.decoded_output:
    decoded_output_file = (decoded_dir / args.decoded_output).with_suffix(".mf4")
else:
    decoded_output_file = decoded_dir / f"{merged_output_file.stem}_decoded.mf4"


# === DBC MAP ===

dbc_files = sorted(dbc_folder.glob("*.dbc"))
if not dbc_files:
    raise FileNotFoundError(f"No .dbc files found in {dbc_folder}")

dbc_map = [(str(dbc), 0) for dbc in dbc_files]
print(f"📚 Using {len(dbc_map)} DBCs for decoding:")
for dbc_path, _ in dbc_map:
    print(f"  • {dbc_path}")

# === FIND MF4 FILES ===

# Find MF4s, skip ones that look like outputs
mf4_files = [p for p in mf4_folder.rglob("*.mf4")
             if "decoded" not in p.stem.lower() and "merged" not in p.stem.lower()]

if not mf4_files:
    raise FileNotFoundError(f"No .mf4 files found in {mf4_folder} or its subfolders")

combined_mdf = MDF.concatenate([MDF(f) for f in mf4_files], sync=False, version='4.0.0')

print("\n🔗 Concatenating normalized MF4 files...")

saved_merged_path = combined_mdf.save(str(merged_output_file))

# asammdf may auto-rename if merged.mf4 already exists:
# merged.mf4 -> merged.0.mf4 -> merged.1.mf4, etc.
if saved_merged_path is None:
    saved_merged_path = merged_output_file
else:
    saved_merged_path = Path(saved_merged_path)

print(f"✅ Merged file saved as: {saved_merged_path}")


# === DECODE MERGED ===

if args.decoded_output:
    decoded_output_file = (decoded_dir / args.decoded_output).with_suffix(".mf4")
else:
    decoded_output_file = decoded_dir / f"{saved_merged_path.stem}_decoded.mf4"

decoded_mdf = decode_mf4_file(
    str(saved_merged_path),
    dbc_map,
    str(decoded_output_file),
)


