"""
Configuration centrale de Celery pour VocalGuard.

Ce module expose une instance `celery_app` configuree a partir
de la classe `Config` existante. Il pourra etre utilise par
les workers et par le code applicatif pour planifier des taches.
"""

from pathlib import Path

from celery import Celery
from celery.schedules import crontab

from backend.core.config import Config


def create_celery_app() -> Celery:
    """
    Cree et configure l'application Celery.
    
    Returns:
        Instance Celery configuree.
    """
    config = Config()
    
    broker_url = config.celery_broker_url or "redis://localhost:6379/0"
    result_backend = config.celery_result_backend or None
    
    app = Celery("vocalguard", broker=broker_url, backend=result_backend)
    
    beat_schedule_path = config.base_path / "data" / "celerybeat-schedule"
    beat_schedule_path.parent.mkdir(parents=True, exist_ok=True)

    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="Europe/Paris",
        enable_utc=True,
        beat_schedule_filename=str(beat_schedule_path),
        imports=(
            "backend.workers.osint_tasks",
            "backend.workers.maintenance_tasks",
        ),
        beat_schedule={
            "log-maintenance-daily": {
                "task": "backend.workers.maintenance_tasks.run_log_maintenance",
                "schedule": crontab(hour=3, minute=15),
            },
        },
    )

    return app


# Instance partagee par defaut
celery_app = create_celery_app()

