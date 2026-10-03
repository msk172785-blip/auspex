import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def demo_documents():
    """Régénère les documents simulés s'ils sont absents."""
    if not (ROOT / "data" / "simulated" / "case_A" / "CCAP_SIM_A_nettoyage.pdf").exists():
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "generate_demo_pdfs.py")])
    return ROOT
