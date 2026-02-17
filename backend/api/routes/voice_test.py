"""
Routes API pour tester l'interface vocale
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pathlib import Path
from loguru import logger

from backend.api.dependencies import get_config
from backend.core.config import Config
from backend.core.response_patterns import ResponsePatternManager
from backend.voice.recognition import VoiceRecognition
from backend.voice.synthesis import VoiceSynthesis

router = APIRouter()

# Instance globale du gestionnaire de patterns
_pattern_manager: ResponsePatternManager = None


def get_pattern_manager(config: Config) -> ResponsePatternManager:
    """
    Récupère ou crée l'instance du gestionnaire de patterns
    
    Args:
        config: Configuration de l'application
        
    Returns:
        Instance du gestionnaire de patterns
    """
    global _pattern_manager
    if _pattern_manager is None:
        # Utiliser le chemin de configuration si disponible
        config_path = None
        if config.config_path:
            config_path = config.config_path.parent / "responses.yaml"
        elif config.base_path:
            config_path = config.base_path / "responses.yaml"
        
        _pattern_manager = ResponsePatternManager(config_path)
    return _pattern_manager


@router.post("/voice/test/synthesis")
async def test_synthesis(
    text: str = Form(...),
    config: Config = Depends(get_config)
):
    """
    Teste la synthèse vocale (text-to-speech)
    
    Args:
        text: Texte à synthétiser
        config: Configuration de l'application
        
    Returns:
        Fichier audio généré
    """
    try:
        synthesis = VoiceSynthesis(config)
        await synthesis.initialize()
        
        # Générer l'audio
        audio_file = await synthesis.speak(text)
        
        if not audio_file or not audio_file.exists():
            raise HTTPException(status_code=500, detail="Erreur lors de la génération de l'audio")
        
        # Déterminer le type MIME
        mime_type = "audio/wav" if audio_file.suffix == ".wav" else "audio/mpeg"
        
        return FileResponse(
            str(audio_file),
            media_type=mime_type,
            filename=f"synthesis_{hash(text)}.{audio_file.suffix[1:]}"
        )
    except Exception as e:
        logger.exception(f"Erreur lors du test de synthèse vocale: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voice/test/recognition")
async def test_recognition(
    audio_file: UploadFile = File(...),
    config: Config = Depends(get_config)
):
    """
    Teste la reconnaissance vocale (speech-to-text)
    
    Args:
        audio_file: Fichier audio à transcrire
        config: Configuration de l'application
        
    Returns:
        Transcription du texte
    """
    try:
        recognition = VoiceRecognition(config)
        await recognition.initialize()
        
        # Lire le fichier audio
        audio_data = await audio_file.read()
        
        # Transcrire
        transcription = await recognition.transcribe(audio_data)
        
        return {
            "transcription": transcription,
            "original_filename": audio_file.filename,
            "audio_size": len(audio_data)
        }
    except Exception as e:
        logger.exception(f"Erreur lors du test de reconnaissance vocale: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voice/test/conversation")
async def test_conversation(
    audio_file: UploadFile = File(...),
    config: Config = Depends(get_config)
):
    """
    Teste une conversation complète : reconnaissance + réponse + synthèse
    
    Args:
        audio_file: Fichier audio de l'utilisateur
        config: Configuration de l'application
        
    Returns:
        Transcription, réponse générée et fichier audio de la réponse
    """
    try:
        recognition = VoiceRecognition(config)
        synthesis = VoiceSynthesis(config)
        
        await recognition.initialize()
        await synthesis.initialize()
        
        # Transcrire l'audio de l'utilisateur
        audio_data = await audio_file.read()
        user_text = await recognition.transcribe(audio_data)
        
        if not user_text:
            user_text = "Je n'ai pas compris ce que vous avez dit."
        
        # Générer une réponse à partir des patterns
        pattern_manager = get_pattern_manager(config)
        response_text = pattern_manager.generate_response(user_text)
        
        # Synthétiser la réponse
        response_audio = await synthesis.speak(response_text)
        
        result = {
            "user_text": user_text,
            "response_text": response_text,
            "original_filename": audio_file.filename
        }
        
        if response_audio and response_audio.exists():
            # Utiliser le nom du fichier comme identifiant
            audio_filename = response_audio.name
            result["response_audio_url"] = f"/api/v1/voice/test/conversation/audio/{audio_filename}"
            result["response_audio_file"] = str(response_audio)
        
        return result
    except Exception as e:
        logger.exception(f"Erreur lors du test de conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/voice/test/conversation/audio/{audio_filename}")
async def get_conversation_audio(
    audio_filename: str,
    config: Config = Depends(get_config)
):
    """
    Récupère le fichier audio d'une réponse de conversation
    
    Args:
        audio_filename: Nom du fichier audio
        config: Configuration de l'application
    """
    cache_dir = Path(config.base_path) / "audio_cache"
    audio_file = cache_dir / audio_filename
    
    if not audio_file.exists():
        raise HTTPException(status_code=404, detail="Fichier audio non trouvé")
    
    mime_type = "audio/wav" if audio_file.suffix == ".wav" else "audio/mpeg"
    return FileResponse(str(audio_file), media_type=mime_type)


@router.post("/voice/test/reload-patterns")
async def reload_patterns(
    config: Config = Depends(get_config)
):
    """
    Recharge les patterns de réponses depuis le fichier de configuration
    
    Args:
        config: Configuration de l'application
        
    Returns:
        Confirmation du rechargement
    """
    try:
        pattern_manager = get_pattern_manager(config)
        pattern_manager.reload()
        return {
            "status": "success",
            "message": f"Patterns rechargés ({len(pattern_manager.patterns)} patterns chargés)"
        }
    except Exception as e:
        logger.exception(f"Erreur lors du rechargement des patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))



