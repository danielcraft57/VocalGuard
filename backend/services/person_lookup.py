"""
Service de recherche de personnes et entreprises par numéro de téléphone
Intègre plusieurs sources pour obtenir nom, prénom, adresse, entreprise
"""

import os
import re
from typing import Dict, Optional, Any
from loguru import logger
import httpx


class PersonLookupService:
    """
    Service pour rechercher des informations sur une personne ou entreprise
    """
    
    def __init__(self):
        """Initialise le service de recherche"""
        # Clés API optionnelles
        self.twilio_account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.twilio_auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.infogreffe_api_key = os.getenv('INFOGREFFE_API_KEY')
        # API Sirene (authentification par clé API simple)
        self.sirene_api_key = os.getenv('SIRENE_API_KEY')
    
    async def lookup_person(self, phone_number: str) -> Dict[str, Any]:
        """
        Recherche des informations sur une personne
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Dictionnaire avec les informations trouvées
        """
        result = {
            'first_name': None,
            'last_name': None,
            'full_name': None,
            'address': None,
            'city': None,
            'postal_code': None,
            'is_company': False,
            'company_name': None,
            'company_siret': None,
            'sources': [],
        }
        
        # Nettoyer le numéro
        clean_number = self._clean_number(phone_number)
        
        # Essayer plusieurs sources
        tasks = []
        
        # Twilio Lookup (si disponible)
        if self.twilio_account_sid and self.twilio_auth_token:
            tasks.append(self._query_twilio(clean_number))
        
        # API Sirene (gratuite, pour les entreprises)
        if self.sirene_api_key:
            tasks.append(self._query_sirene(clean_number))
        
        # Infogreffe (si disponible)
        if self.infogreffe_api_key:
            tasks.append(self._query_infogreffe(clean_number))
        
        # Recherche dans les annuaires publics (à implémenter)
        tasks.append(self._query_public_directories(clean_number))
        
        # Exécuter les requêtes
        import asyncio
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, dict):
                    result = self._merge_person_results(result, res)
        
        return result
    
    async def lookup_company(self, phone_number: str) -> Dict[str, Any]:
        """
        Recherche des informations sur une entreprise
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Dictionnaire avec les informations de l'entreprise
        """
        result = {
            'company_name': None,
            'company_siret': None,
            'company_siren': None,
            'company_address': None,
            'company_city': None,
            'company_postal_code': None,
            'company_activity': None,
            'company_legal_form': None,
            'company_creation_date': None,
            'sources': [],
        }
        
        clean_number = self._clean_number(phone_number)
        
        # API Sirene (gratuite, officielle)
        if self.sirene_api_key:
            sirene_result = await self._query_sirene(clean_number)
            if sirene_result.get('company_name'):
                result.update(sirene_result)
        
        # Infogreffe
        if self.infogreffe_api_key:
            infogreffe_result = await self._query_infogreffe(clean_number)
            if infogreffe_result.get('company_name'):
                result.update(infogreffe_result)
        
        return result
    
    async def _query_twilio(self, phone_number: str) -> Dict[str, Any]:
        """
        Interroge Twilio Lookup API
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Informations depuis Twilio
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://lookups.twilio.com/v1/PhoneNumbers/{phone_number}",
                    auth=(self.twilio_account_sid, self.twilio_auth_token),
                    params={
                        "Type": "caller-name"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        'sources': ['twilio'],
                        'full_name': data.get('caller_name', {}).get('caller_name'),
                        'carrier': data.get('carrier', {}).get('name'),
                    }
        except Exception as e:
            logger.debug(f"Erreur Twilio Lookup: {e}")
        
        return {}
    
    async def _query_sirene(self, phone_number: str) -> Dict[str, Any]:
        """
        Interroge l'API Sirene (gratuite, officielle) pour les entreprises
        
        IMPORTANT: L'API Sirene nécessite une inscription sur le portail API de l'INSEE
        https://portail-api.insee.fr/
        
        Pour obtenir l'accès:
        1. Aller sur https://www.data.gouv.fr/dataservices/api-sirene-open-data
        2. Cliquer sur "Documentation métier" (redirige vers portail-api.insee.fr)
        3. Cliquer sur "Souscrire"
        4. Créer un compte ou se connecter
        5. La clé API est générée automatiquement dans l'onglet "Souscriptions"
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Informations depuis Sirene
        """
        if not self.sirene_api_key:
            logger.debug("Clé API Sirene non configurée. Voir https://portail-api.insee.fr/ pour obtenir l'accès")
            return {}
        
        try:
            # L'API Sirene nécessite un SIRET ou SIREN, pas directement un numéro
            # On peut chercher par numéro dans les établissements via le champ "telephone"
            # Format de l'API: https://api.insee.fr/api-sirene/3.11/siret?q=telephone:XXXXXXXXXX
            
            # Nettoyer le numéro pour la recherche
            clean_phone = re.sub(r'[^\d]', '', phone_number)
            if clean_phone.startswith('0'):
                clean_phone = '33' + clean_phone[1:]  # Format international sans +
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Authentification par clé API (header Authorization: Bearer)
                headers = {
                    'Authorization': f'Bearer {self.sirene_api_key}',
                    'Accept': 'application/json'
                }
                
                # Recherche par téléphone (si supporté)
                # Note: L'API Sirene ne permet pas toujours la recherche directe par téléphone
                # Il faudrait d'abord obtenir le SIRET via un autre service
                url = f"https://api.insee.fr/api-sirene/3.11/siret"
                params = {
                    'q': f'telephone:{clean_phone}'
                }
                
                response = await client.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    # Traiter les résultats
                    if data.get('etablissements'):
                        etablissement = data['etablissements'][0]
                        unite_legale = etablissement.get('uniteLegale', {})
                        return {
                            'sources': ['sirene'],
                            'company_name': unite_legale.get('denominationUniteLegale') or unite_legale.get('nomUniteLegale'),
                            'company_siret': etablissement.get('siret'),
                            'company_siren': unite_legale.get('siren'),
                            'company_address': etablissement.get('adresseEtablissement', {}).get('libelleVoieEtablissement'),
                            'company_city': etablissement.get('adresseEtablissement', {}).get('libelleCommuneEtablissement'),
                            'company_postal_code': etablissement.get('adresseEtablissement', {}).get('codePostalEtablissement'),
                            'company_activity': unite_legale.get('activitePrincipaleUniteLegale'),
                        }
                elif response.status_code == 404:
                    logger.debug(f"Aucun établissement trouvé pour le téléphone {clean_phone}")
                else:
                    logger.debug(f"Erreur API Sirene: {response.status_code} - {response.text}")
        except Exception as e:
            logger.debug(f"Erreur API Sirene: {e}")
        
        return {}
    
    async def _query_infogreffe(self, phone_number: str) -> Dict[str, Any]:
        """
        Interroge Infogreffe (si API disponible)
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Informations depuis Infogreffe
        """
        # Infogreffe n'a pas d'API publique directe
        # Il faudrait scraper ou utiliser un service tiers
        return {}
    
    async def _query_public_directories(self, phone_number: str) -> Dict[str, Any]:
        """
        Recherche dans les annuaires publics
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Informations depuis les annuaires publics
        """
        # Recherche dans les pages blanches, etc.
        # Note: Beaucoup d'annuaires nécessitent un scraper ou une API
        return {}
    
    def _clean_number(self, phone_number: str) -> str:
        """Nettoie le numéro"""
        cleaned = re.sub(r'[^\d+]', '', phone_number)
        if cleaned.startswith('0') and not cleaned.startswith('+33'):
            cleaned = '+33' + cleaned[1:]
        return cleaned
    
    def _merge_person_results(self, base: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        """Fusionne les résultats de recherche"""
        # Fusionner les sources
        base['sources'].extend(new.get('sources', []))
        base['sources'] = list(set(base['sources']))
        
        # Mettre à jour les champs
        for key in ['first_name', 'last_name', 'full_name', 'address', 'city', 
                   'postal_code', 'company_name', 'company_siret']:
            if new.get(key) and not base.get(key):
                base[key] = new[key]
        
        if new.get('is_company'):
            base['is_company'] = True
        
        return base

