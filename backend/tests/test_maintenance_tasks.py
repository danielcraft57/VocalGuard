"""
Tests de la tache Celery de maintenance logs.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.workers import maintenance_tasks


def test_run_log_maintenance_ok() -> None:
    """Verifie que la tache delegue au script shell et remonte un succes."""
    tmp_path = Path(__file__).resolve().parents[2] / ".pytest_tmp" / "maintenance_tasks_ok"
    tmp_path.mkdir(parents=True, exist_ok=True)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "prod_log_maintenance.sh"
    script.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")

    fake_completed = MagicMock()
    fake_completed.returncode = 0
    fake_completed.stdout = "log maintenance done"
    fake_completed.stderr = ""

    with patch.object(maintenance_tasks, "_config") as mock_cfg:
        mock_cfg.base_path = tmp_path
        with patch("backend.workers.maintenance_tasks.subprocess.run", return_value=fake_completed) as run_mock:
            result = maintenance_tasks.run_log_maintenance()

    assert result["ok"] is True
    assert result["returncode"] == 0
    run_mock.assert_called_once()
    call_args = run_mock.call_args
    assert call_args[0][0] == ["bash", str(script)]


def test_run_log_maintenance_missing_script() -> None:
    """Echec explicite si le script prod est absent."""
    tmp_path = Path(__file__).resolve().parents[2] / ".pytest_tmp" / "maintenance_tasks_missing"
    tmp_path.mkdir(parents=True, exist_ok=True)
    with patch.object(maintenance_tasks, "_config") as mock_cfg:
        mock_cfg.base_path = tmp_path
        try:
            maintenance_tasks.run_log_maintenance()
            assert False, "FileNotFoundError attendue"
        except FileNotFoundError:
            pass
