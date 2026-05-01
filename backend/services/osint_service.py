"""
Service OSINT pour l'enrichissement d'informations sur les numéros de téléphone
Intègre des outils Linux d'OSINT comme phoneinfoga, truecaller-scraper, etc.
"""

import asyncio
import subprocess
import json
import re
import os
from typing import Optional, Dict, Any, List
from pathlib import Path
from loguru import logger

import httpx

from backend.core.config import Config
from backend.services.commercial_detector import CommercialDetector
from backend.services.external_api_metrics import external_api_metrics
from backend.services.french_phone_detector import FrenchPhoneDetector
from backend.services.person_lookup import PersonLookupService
from backend.services.reputation_providers import check_nomorobo, check_shouldianswer


class OSINTService:
    """Service pour l'enrichissement OSINT des numéros de téléphone"""
    
    def __init__(self, config: Config):
        """
        Initialise le service OSINT
        
        Args:
            config: Configuration de l'application
        """
        self.config = config
        self.osint_tools_path = Path(config.base_path) / "osint_tools"
        self.osint_tools_path.mkdir(parents=True, exist_ok=True)
        
        # Clés API optionnelles pour les services externes
        self.numlookup_api_key = os.getenv('NUMLOOKUP_API_KEY')
        self.opencnam_api_key = os.getenv('OPENCNAM_API_KEY')
        self.numverify_api_key = os.getenv('NUMVERIFY_API_KEY')
        self.hlr_api_key = os.getenv('HLR_API_KEY')
        # Services de reputation type callattendant (NOMOROBO USA, SHOULDIANSWER hors USA)
        self.block_service = (getattr(config, 'block_service', None) or '').strip().upper()
        self.nomorobo_api_key = getattr(config, 'nomorobo_api_key', None) or os.getenv('NOMOROBO_API_KEY')
        self.shouldianswer_api_key = getattr(config, 'shouldianswer_api_key', None) or os.getenv('SHOULDIANSWER_API_KEY')
        
        # Détecter si on est sur WSL/Kali Linux
        self.is_wsl = self._detect_wsl()
        self.available_tools = self._detect_available_tools()
        
        # Initialiser le détecteur commercial
        commercial_config = getattr(config, 'commercial_detection', {})
        self.commercial_detector = CommercialDetector(commercial_config)
        
        # Initialiser le détecteur français avec le chemin de données
        # Note: la session DB sera passée lors de l'utilisation si disponible
        french_data_path = Path(config.base_path) / "french_phone_data"
        self.french_detector = FrenchPhoneDetector(french_data_path, db=None)
        
        # Initialiser le service de recherche de personnes/entreprises
        self.person_lookup = PersonLookupService()
    
    def _detect_wsl(self) -> bool:
        """
        Détecte si on est sur WSL
        
        Returns:
            True si WSL détecté
        """
        try:
            with open("/proc/version", "r") as f:
                version = f.read().lower()
                return "microsoft" in version or "wsl" in version
        except:
            return False
    
    def _detect_available_tools(self) -> Dict[str, bool]:
        """
        Détecte les outils OSINT disponibles
        
        Returns:
            Dictionnaire des outils disponibles
        """
        tools = {
            "phoneinfoga": False,
            "truecaller": False,
            "osintgram": False,
            "theharvester": False,
            "recon-ng": False,
            "numlookup": bool(self.numlookup_api_key),
            "opencnam": bool(self.opencnam_api_key),
            "numverify": bool(self.numverify_api_key),
            "hlr_lookup": bool(self.hlr_api_key),
            "commercial_detector": True,  # Toujours disponible
            "nomorobo": self.block_service == "NOMOROBO" and bool(self.nomorobo_api_key),
            "shouldianswer": self.block_service == "SHOULDIANSWER" and bool(self.shouldianswer_api_key),
        }
        
        # Vérifier phoneinfoga
        try:
            result = subprocess.run(
                ["which", "phoneinfoga"],
                capture_output=True,
                text=True,
                timeout=2
            )
            tools["phoneinfoga"] = result.returncode == 0
        except:
            pass
        
        # Vérifier truecaller-scraper (via Python)
        try:
            import truecallerpy
            tools["truecaller"] = True
        except ImportError:
            pass
        
        # Vérifier theHarvester
        try:
            result = subprocess.run(
                ["which", "theHarvester"],
                capture_output=True,
                text=True,
                timeout=2
            )
            tools["theharvester"] = result.returncode == 0
        except:
            pass
        
        logger.info(f"Outils OSINT disponibles: {[k for k, v in tools.items() if v]}")
        return tools
    
    async def enrich_phone_number(self, phone_number: str, caller_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Enrichit les informations sur un numéro de téléphone
        
        Args:
            phone_number: Numéro de téléphone à analyser
            caller_name: Nom de l'appelant (optionnel)
            
        Returns:
            Dictionnaire avec les informations enrichies
        """
        logger.info(f"Enrichissement OSINT pour {phone_number}")
        
        result = {
            "phone_number": phone_number,
            "sources": [],
            "carrier": None,
            "operator": None,
            "operator_description": None,
            "operator_full_name": None,
            "operator_type": None,
            "operator_website": None,
            "country": None,
            "region": None,
            "city": None,
            "department": None,
            "postal_code": None,
            "line_type": None,
            "name": None,
            "first_name": None,
            "last_name": None,
            "full_name": None,
            "address": None,
            "is_company": False,
            "company_name": None,
            "company_siret": None,
            "company_siren": None,
            "company_address": None,
            "company_activity": None,
            "social_media": {},
            "reputation": None,
            "is_spam": False,
            "is_scam": False,
            "is_commercial": False,
            "is_telemarketer": False,
            "confidence": 0.0,
        }
        
        # Nettoyer le numéro
        try:
            clean_number = self._clean_phone_number(phone_number)
        except Exception as e:
            logger.warning(f"Erreur lors du nettoyage du numéro {phone_number}: {e}")
            clean_number = phone_number  # Utiliser le numéro original en cas d'erreur
        
        # Détection française (opérateur, ville, région) - PRIORITAIRE pour les numéros français
        try:
            french_info = self.french_detector.detect(clean_number)
            logger.info(f"Résultat détection française pour {clean_number}: operator={french_info.get('operator')}, city={french_info.get('city')}, region={french_info.get('region')}")
            
            # Fusionner toutes les informations françaises (même si partielles)
            if french_info.get('operator'):
                result['operator'] = french_info['operator']
                result['operator_description'] = french_info.get('operator_description')
                result['operator_full_name'] = french_info.get('operator_full_name')
                result['operator_type'] = french_info.get('operator_type')
                result['operator_website'] = french_info.get('operator_website')
                if 'french_detector' not in result['sources']:
                    result['sources'].append('french_detector')
            
            if french_info.get('region'):
                result['region'] = french_info['region']
            if french_info.get('city'):
                result['city'] = french_info['city']
            if french_info.get('department'):
                result['department'] = french_info['department']
            if french_info.get('postal_code'):
                result['postal_code'] = french_info['postal_code']
            if french_info.get('line_type'):
                result['line_type'] = french_info['line_type']
            
            # Utiliser l'opérateur comme carrier si pas déjà défini
            if not result.get('carrier') and french_info.get('operator'):
                result['carrier'] = french_info['operator']
            
            # Augmenter la confiance si on a des infos françaises
            if french_info.get('confidence', 0) > 0:
                result['confidence'] = max(result['confidence'], french_info['confidence'])
        except Exception as e:
            logger.warning(f"Erreur lors de la détection française pour {clean_number}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            # Continuer même si la détection française échoue
        
        # Détection commerciale (toujours disponible)
        try:
            commercial_result = self.commercial_detector.detect_commercial(clean_number, caller_name)
            if commercial_result and isinstance(commercial_result, dict) and commercial_result.get('is_commercial'):
                result['is_commercial'] = True
                result['is_telemarketer'] = commercial_result.get('is_telemarketer', False)
                result['sources'].append('commercial_detector')
                if commercial_result.get('description'):
                    result['name'] = commercial_result.get('description')
                result['confidence'] = max(result['confidence'], commercial_result.get('confidence', 0.0))
                # Marquer comme spam si télémarketeur
                if commercial_result.get('is_telemarketer'):
                    result['is_spam'] = True
                    result['reputation'] = 'low'
        except Exception as e:
            logger.warning(f"Erreur lors de la détection commerciale pour {clean_number}: {e}")
            # Continuer même si la détection commerciale échoue
        
        # Utiliser plusieurs sources
        tasks = []
        
        if self.available_tools.get("phoneinfoga"):
            tasks.append(self._query_phoneinfoga(clean_number))
        
        if self.available_tools.get("truecaller"):
            tasks.append(self._query_truecaller(clean_number))
        
        if self.available_tools.get("numlookup"):
            tasks.append(self._query_numlookup(clean_number))
        
        if self.available_tools.get("opencnam"):
            tasks.append(self._query_opencnam(clean_number))
        
        if self.available_tools.get("numverify"):
            tasks.append(self._query_numverify(clean_number))
        
        if self.available_tools.get("hlr_lookup"):
            tasks.append(self._query_hlr_lookup(clean_number))

        if self.available_tools.get("nomorobo"):
            tasks.append(self._query_nomorobo_reputation(clean_number))
        if self.available_tools.get("shouldianswer"):
            tasks.append(self._query_shouldianswer_reputation(clean_number))
        
        # Exécuter les requêtes en parallèle
        if tasks:
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for res in results:
                    if isinstance(res, dict):
                        result = self._merge_results(result, res)
                    elif isinstance(res, Exception):
                        logger.warning(f"Erreur dans une tâche OSINT: {res}")
            except Exception as e:
                logger.warning(f"Erreur lors de l'exécution des tâches OSINT: {e}")
                # Continuer même si certaines tâches échouent
        
        # Recherche de personne/entreprise (en parallèle)
        try:
            person_result = await self.person_lookup.lookup_person(clean_number)
            if person_result.get('full_name'):
                result['full_name'] = person_result['full_name']
                result['first_name'] = person_result.get('first_name')
                result['last_name'] = person_result.get('last_name')
                result['name'] = person_result.get('full_name')  # Compatibilité
                result['sources'].extend(person_result.get('sources', []))
            
            if person_result.get('address'):
                result['address'] = person_result['address']
            
            if person_result.get('is_company'):
                result['is_company'] = True
                result['company_name'] = person_result.get('company_name')
                result['company_siret'] = person_result.get('company_siret')
                
                # Si c'est une entreprise, chercher plus d'infos
                company_result = await self.person_lookup.lookup_company(clean_number)
                if company_result.get('company_name'):
                    result['company_name'] = company_result.get('company_name')
                    result['company_siret'] = company_result.get('company_siret')
                    result['company_siren'] = company_result.get('company_siren')
                    result['company_address'] = company_result.get('company_address')
                    result['company_activity'] = company_result.get('company_activity')
                    result['sources'].extend(company_result.get('sources', []))
        except Exception as e:
            logger.warning(f"Erreur lors de la recherche personne/entreprise: {e}")
        
        # Enrichissement basique si aucun outil disponible ou peu de sources
        try:
            if not result["sources"] or len(result["sources"]) == 1:
                result = await self._basic_enrichment(clean_number, result)
        except Exception as e:
            logger.warning(f"Erreur lors de l'enrichissement basique: {e}")
        
        # S'assurer que le résultat est toujours valide
        if not isinstance(result, dict):
            logger.error(f"Le résultat OSINT n'est pas un dictionnaire: {type(result)}")
            result = {
                "phone_number": phone_number,
                "sources": [],
                "error": "Erreur lors de l'enrichissement OSINT"
            }

        # Si on a au moins lieu ou opérateur (détection FR) mais aucune réputation des APIs externes,
        # poser "neutral" pour que la migration / le profil persiste une réputation (affichée "Non évaluée").
        if result.get("reputation") is None and (
            result.get("region") or result.get("city") or result.get("operator")
        ):
            result["reputation"] = "neutral"

        logger.debug(f"Résultat OSINT: {result}")
        return result
    
    def _clean_phone_number(self, phone_number: str) -> str:
        """
        Nettoie et normalise un numéro de téléphone
        
        Args:
            phone_number: Numéro à nettoyer
            
        Returns:
            Numéro nettoyé
        """
        # Retirer tous les caractères non numériques sauf +
        cleaned = re.sub(r'[^\d+]', '', phone_number)
        
        # Si le numéro commence par 0, le convertir en +33 (format français)
        if cleaned.startswith('0') and not cleaned.startswith('+33'):
            cleaned = '+33' + cleaned[1:]
        # Si le numéro n'a pas de + et fait plus de 10 chiffres, ajouter +
        elif not cleaned.startswith('+') and len(cleaned) > 10:
            cleaned = '+' + cleaned
        # Si le numéro fait 10 chiffres et commence par 0, supposer français
        elif len(cleaned) == 10 and cleaned.startswith('0'):
            cleaned = '+33' + cleaned[1:]
        
        return cleaned
    
    async def _query_phoneinfoga(self, phone_number: str) -> Dict[str, Any]:
        """
        Interroge phoneinfoga pour obtenir des informations
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Informations depuis phoneinfoga
        """
        try:
            # Exécuter phoneinfoga via subprocess
            # Note: phoneinfoga peut être utilisé via API ou CLI
            cmd = ["phoneinfoga", "scan", "-n", phone_number, "-o", "json"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.osint_tools_path)
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                external_api_metrics.record("phoneinfoga", True)
                try:
                    data = json.loads(stdout.decode())
                    return {
                        "sources": ["phoneinfoga"],
                        "carrier": data.get("carrier"),
                        "country": data.get("country"),
                        "line_type": data.get("line_type"),
                        "reputation": data.get("reputation"),
                    }
                except json.JSONDecodeError:
                    logger.warning("Impossible de parser la réponse phoneinfoga")
            else:
                external_api_metrics.record("phoneinfoga", False)
            
        except FileNotFoundError:
            logger.warning("phoneinfoga non trouvé")
        except Exception as e:
            logger.exception(f"Erreur lors de l'interrogation phoneinfoga: {e}")
        
        return {}
    
    async def _query_truecaller(self, phone_number: str) -> Dict[str, Any]:
        """
        Interroge Truecaller pour obtenir des informations
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Informations depuis Truecaller
        """
        try:
            # Utiliser truecallerpy si disponible
            try:
                import truecallerpy
                
                # Note: Truecaller nécessite une authentification
                # Ici on montre la structure, à adapter selon l'API
                result = {
                    "sources": ["truecaller"],
                    "name": None,  # À remplir avec l'API
                    "address": None,
                }
                external_api_metrics.record("truecaller", True)
                return result
                
            except ImportError:
                logger.warning("truecallerpy non installé")
                external_api_metrics.record("truecaller", False)
        
        except Exception as e:
            logger.exception(f"Erreur lors de l'interrogation Truecaller: {e}")
            external_api_metrics.record("truecaller", False)
        
        return {}
    
    async def _basic_enrichment(self, phone_number: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrichissement basique sans outils externes
        
        Args:
            phone_number: Numéro de téléphone
            result: Résultat à enrichir
            
        Returns:
            Résultat enrichi
        """
        # Détection basique du pays
        if phone_number.startswith('+33'):
            result["country"] = "France"
            result["sources"].append("basic_detection")
            
            # Essayer la détection française si pas déjà fait
            if 'french_detector' not in result.get("sources", []):
                try:
                    french_info = self.french_detector.detect(phone_number)
                    if french_info.get('operator'):
                        result['operator'] = french_info['operator']
                        result['operator_description'] = french_info.get('operator_description')
                    if french_info.get('region'):
                        result['region'] = french_info['region']
                    if french_info.get('city'):
                        result['city'] = french_info['city']
                    if french_info.get('line_type'):
                        result['line_type'] = french_info['line_type']
                    if not result.get('carrier') and french_info.get('operator'):
                        result['carrier'] = french_info['operator']
                except Exception as e:
                    logger.debug(f"Erreur détection française dans enrichissement basique: {e}")
        
        # Détection de patterns suspects
        if self._is_suspicious_pattern(phone_number):
            result["is_spam"] = True
            result["reputation"] = "low"
            result["confidence"] = 0.3
        
        return result
    
    def _is_suspicious_pattern(self, phone_number: str) -> bool:
        """
        Détecte des patterns suspects dans un numéro
        
        Args:
            phone_number: Numéro à analyser
            
        Returns:
            True si le pattern est suspect
        """
        # Numéros avec beaucoup de chiffres identiques
        if len(set(phone_number.replace('+', ''))) < 3:
            return True
        
        # Numéros très courts ou très longs
        digits = re.sub(r'\D', '', phone_number)
        if len(digits) < 8 or len(digits) > 15:
            return True
        
        return False
    
    def _merge_results(self, base: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fusionne deux résultats OSINT
        
        Args:
            base: Résultat de base
            new: Nouveau résultat à fusionner
            
        Returns:
            Résultat fusionné
        """
        # Fusionner les sources
        base["sources"].extend(new.get("sources", []))
        base["sources"] = list(set(base["sources"]))
        
        # Mettre à jour les champs si disponibles
        for key in ["carrier", "operator", "operator_description", "operator_full_name", "operator_type", 
                   "country", "region", "city", "department", "postal_code", "line_type", 
                   "name", "address", "reputation"]:
            if new.get(key) and not base.get(key):
                base[key] = new[key]
        
        # Fusionner les médias sociaux
        if new.get("social_media"):
            base["social_media"].update(new["social_media"])
        
        # Mettre à jour les flags
        if new.get("is_spam"):
            base["is_spam"] = True
        if new.get("is_scam"):
            base["is_scam"] = True
        
        # Augmenter la confiance
        if new.get("sources"):
            base["confidence"] = min(1.0, base.get("confidence", 0.0) + 0.2)
        
        return base
    
    async def check_reputation(self, phone_number: str, caller_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Vérifie la réputation d'un numéro de téléphone
        
        Args:
            phone_number: Numéro à vérifier
            caller_name: Nom de l'appelant (optionnel)
            
        Returns:
            Informations sur la réputation
        """
        result = await self.enrich_phone_number(phone_number, caller_name)

        rep = result.get("reputation")
        if rep is None:
            rep = "unknown"
        elif not isinstance(rep, str):
            rep = str(rep) if rep is not None else "unknown"

        sources = result.get("sources")
        if sources is None or not isinstance(sources, list):
            sources = []

        conf = result.get("confidence", 0.0)
        if conf is None:
            conf = 0.0
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.0

        reputation_info = {
            "phone_number": phone_number,
            "reputation": rep,
            "is_spam": bool(result.get("is_spam", False)),
            "is_scam": bool(result.get("is_scam", False)),
            "is_commercial": bool(result.get("is_commercial", False)),
            "is_telemarketer": bool(result.get("is_telemarketer", False)),
            "confidence": conf,
            "sources": sources,
            "recommendation": self._get_recommendation(result),
        }

        return reputation_info
    
    def _get_recommendation(self, result: Dict[str, Any]) -> str:
        """
        Génère une recommandation basée sur les résultats
        
        Args:
            result: Résultats OSINT
            
        Returns:
            Recommandation (block, allow, review)
        """
        if result.get("is_scam"):
            return "block"
        
        if result.get("is_spam"):
            return "block"
        
        if result.get("is_telemarketer"):
            return "block"
        
        if result.get("is_commercial") and result.get("confidence", 0.0) > 0.8:
            return "block"
        
        if result.get("reputation") == "low":
            return "block"
        
        if result.get("reputation") == "high":
            return "allow"
        
        return "review"
    
    async def _query_numlookup(self, phone_number: str) -> Dict[str, Any]:
        """
        Interroge NumLookup API pour obtenir des informations
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Informations depuis NumLookup
        """
        if not self.numlookup_api_key:
            return {}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://api.numlookupapi.com/v1/validate",
                    params={
                        "number": phone_number,
                        "apikey": self.numlookup_api_key
                    }
                )
                external_api_metrics.record("numlookup", response.status_code == 200)
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "sources": ["numlookup"],
                        "carrier": data.get("carrier"),
                        "country": data.get("country_name"),
                        "line_type": data.get("line_type"),
                        "valid": data.get("valid", False),
                    }
        except Exception as e:
            logger.exception(f"Erreur lors de l'interrogation NumLookup: {e}")
            external_api_metrics.record("numlookup", False)
        
        return {}
    
    async def _query_opencnam(self, phone_number: str) -> Dict[str, Any]:
        """
        Interroge OpenCNAM pour obtenir le nom de l'appelant
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Informations depuis OpenCNAM
        """
        if not self.opencnam_api_key:
            return {}
        
        try:
            # Nettoyer le numéro pour OpenCNAM (format E.164)
            clean_number = self._clean_phone_number(phone_number)
            if not clean_number.startswith('+'):
                clean_number = '+' + clean_number
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://api.opencnam.com/v3/phone/{clean_number}",
                    params={
                        "account_sid": self.opencnam_api_key,
                        "auth_token": self.opencnam_api_key
                    }
                )
                external_api_metrics.record("opencnam", response.status_code == 200)
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "sources": ["opencnam"],
                        "name": data.get("name"),
                    }
        except Exception as e:
            logger.exception(f"Erreur lors de l'interrogation OpenCNAM: {e}")
            external_api_metrics.record("opencnam", False)
        
        return {}
    
    async def _query_numverify(self, phone_number: str) -> Dict[str, Any]:
        """
        Interroge NumVerify API pour obtenir des informations
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Informations depuis NumVerify
        """
        if not self.numverify_api_key:
            return {}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "http://apilayer.net/api/validate",
                    params={
                        "access_key": self.numverify_api_key,
                        "number": phone_number
                    }
                )
                external_api_metrics.record("numverify", response.status_code == 200)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("valid"):
                        return {
                            "sources": ["numverify"],
                            "carrier": data.get("carrier"),
                            "country": data.get("country_name"),
                            "line_type": data.get("line_type"),
                            "location": data.get("location"),
                        }
        except Exception as e:
            logger.exception(f"Erreur lors de l'interrogation NumVerify: {e}")
            external_api_metrics.record("numverify", False)
        
        return {}
    
    async def _query_hlr_lookup(self, phone_number: str) -> Dict[str, Any]:
        """
        Interroge HLR Lookup API pour vérifier la validité et l'opérateur
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Informations depuis HLR Lookup
        """
        if not self.hlr_api_key:
            return {}
        
        try:
            # Nettoyer le numéro pour HLR (format E.164)
            clean_number = self._clean_phone_number(phone_number)
            if not clean_number.startswith('+'):
                clean_number = '+' + clean_number
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://api.hlrlookup.com/api/hlr",
                    params={
                        "apikey": self.hlr_api_key,
                        "number": clean_number
                    }
                )
                external_api_metrics.record("hlr_lookup", response.status_code == 200)
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "sources": ["hlr_lookup"],
                        "carrier": data.get("network"),
                        "country": data.get("country_name"),
                        "valid": data.get("status") == "active",
                    }
        except Exception as e:
            logger.exception(f"Erreur lors de l'interrogation HLR Lookup: {e}")
            external_api_metrics.record("hlr_lookup", False)
        
        return {}

    async def _query_nomorobo_reputation(self, phone_number: str) -> Dict[str, Any]:
        """
        Interroge Nomorobo (USA) pour reputation robocall/spam.
        Utilise quand block_service=NOMOROBO et NOMOROBO_API_KEY sont configures.
        """
        return await check_nomorobo(
            phone_number,
            api_key=self.nomorobo_api_key,
        )

    async def _query_shouldianswer_reputation(self, phone_number: str) -> Dict[str, Any]:
        """
        Interroge Should I Answer (hors USA, communaute).
        Stub : pas d'API publique pour l'instant.
        """
        return await check_shouldianswer(
            phone_number,
            api_key=self.shouldianswer_api_key,
        )
    
    def install_phoneinfoga(self) -> bool:
        """
        Installe phoneinfoga (pour WSL/Kali Linux)
        
        Returns:
            True si l'installation réussit
        """
        if not self.is_wsl:
            logger.warning("Installation de phoneinfoga recommandée sur Linux/WSL")
            return False
        
        try:
            logger.info("Installation de phoneinfoga...")
            
            # Méthode 1: Via Go (recommandé)
            install_cmd = [
                "bash", "-c",
                "go install -v github.com/sundowndev/phoneinfoga/v2@latest"
            ]
            
            process = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if process.returncode == 0:
                logger.info("phoneinfoga installé avec succès")
                self.available_tools["phoneinfoga"] = True
                return True
            else:
                logger.error(f"Erreur lors de l'installation: {process.stderr}")
                return False
        
        except Exception as e:
            logger.exception(f"Erreur lors de l'installation de phoneinfoga: {e}")
            return False

