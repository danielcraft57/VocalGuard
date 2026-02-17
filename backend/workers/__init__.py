"""
Package `workers` contenant les taches Celery.

Les taches longues (OSINT, envoi d'emails, generation de PDF, etc.)
seront definies ici afin de ne pas bloquer le traitement des appels.
"""

