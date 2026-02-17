"""
Script d'installation pour VocalGuard
"""

from setuptools import setup, find_packages
from pathlib import Path

# Lire le README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="vocalguard",
    version="1.0.0",
    description="Système moderne de gestion d'appels avec interface vocale",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="VocalGuard Team",
    author_email="",
    url="https://github.com/yourusername/vocalguard",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.104.1",
        "uvicorn[standard]>=0.24.0",
        "pydantic>=2.5.0",
        "pydantic-settings>=2.1.0",
        "sqlalchemy>=2.0.23",
        "alembic>=1.12.1",
        "aiosqlite>=0.21.0",
        "openai-whisper>=20231117",
        "vosk>=0.3.45",
        "pyttsx3>=2.90",
        "gtts>=2.4.0",
        "pyaudio>=0.2.14",
        "soundfile>=0.12.1",
        "librosa>=0.10.1",
        "numpy>=1.26.0",
        "pyserial>=3.5",
        "httpx>=0.25.1",
        "aiohttp>=3.9.1",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0.1",
        "loguru>=0.7.2",
        "jinja2>=3.1.2",
    ],
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    entry_points={
        "console_scripts": [
            "vocalguard=vocalguard.main:main",
        ],
    },
)

