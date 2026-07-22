"""Test root verification scripts (`test_dossier.py` and `test_fracture.py`)."""
import subprocess
import sys
import os

def test_root_dossier_script():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    res = subprocess.run([sys.executable, "test_dossier.py"], cwd=repo_root, capture_output=True, text=True)
    assert res.returncode == 0, f"test_dossier.py failed:\n{res.stderr}\n{res.stdout}"
    assert "Aboyeur approved" in res.stdout
    assert "GENERATED DOSSIER" in res.stdout

def test_root_fracture_script():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    res = subprocess.run([sys.executable, "test_fracture.py"], cwd=repo_root, capture_output=True, text=True)
    assert res.returncode == 0, f"test_fracture.py failed:\n{res.stderr}\n{res.stdout}"
    assert "Spawned 2 shards" in res.stdout
    assert "Shards stitched successfully" in res.stdout
