"""
Script pour initialiser la base de données des numéros français
Peut être exécuté pour peupler la base avec les données par défaut
"""

import sys
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database.database import init_database, get_db
from backend.services.french_phone_db import FrenchPhoneDatabase
from backend.services.french_phone_data import FrenchPhoneDataManager
from backend.core.config import Config
import asyncio


async def main():
    """Initialise la base de données avec les données françaises"""
    print("Initialisation de la base de données des numéros français...")
    
    # Charger la config
    config = Config()
    
    # Initialiser la base de données
    await init_database(config.database_url)
    
    # Obtenir une session
    db = next(get_db())
    
    try:
        # Initialiser le gestionnaire de base de données
        db_manager = FrenchPhoneDatabase(db)
        
        # Charger les données par défaut depuis le gestionnaire JSON
        data_path = config.base_path / "french_phone_data"
        data_manager = FrenchPhoneDataManager(data_path)
        
        # Si pas de données, initialiser
        if not data_manager.prefix_data:
            data_manager._init_default_data()
            data_manager._save_data()
        
        # Importer dans la base de données
        print(f"Import de {len(data_manager.prefix_data)} préfixes...")
        prefixes_to_import = []
        
        for prefix, info in data_manager.prefix_data.items():
            prefixes_to_import.append({
                'prefix': prefix,
                'city': info.get('city'),
                'region': info.get('region'),
                'department': info.get('department'),
                'postal_code': info.get('postal_code'),
                'operator': info.get('operator'),
                'line_type': 'landline' if prefix[0] in ['0', '1', '2', '3', '4', '5'] else 'mobile' if prefix[0] in ['6', '7'] else 'special',
            })
        
        count = db_manager.bulk_import(prefixes_to_import)
        print(f"✓ {count} préfixes importés avec succès")
        
        # Afficher les statistiques
        stats = db_manager.get_statistics()
        print(f"\nStatistiques:")
        print(f"  - Total préfixes: {stats.get('total_prefixes', 0)}")
        print(f"  - Opérateurs uniques: {stats.get('unique_operators', 0)}")
        print(f"  - Villes uniques: {stats.get('unique_cities', 0)}")
        print(f"  - Régions uniques: {stats.get('unique_regions', 0)}")
        
    finally:
        db.close()
    
    print("\n✓ Base de données initialisée avec succès!")


if __name__ == "__main__":
    asyncio.run(main())

