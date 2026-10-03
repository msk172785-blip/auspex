from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_loads_and_shows_simulated_case_a():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    at.sidebar.radio[0].set_value("Exemples simulés").run()
    at.button(key="sim_case_A").click().run()
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "EXEMPLE SIMULÉ" in md and "15/11/2026" in md and "6 600" in md
    at.button(key="proof_0").click().run()
    assert not at.exception
    assert at.session_state.page == "4 · Preuves"
    for page in ("2 · Vue d'ensemble", "Évaluation", "1 · Analyser un marché"):
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception
