# main.py
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging
import asyncio
import json     

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger('discord')

# Charger les variables d'environnement
load_dotenv()

# --- Récupération des variables d'environnement ---
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise ValueError("Le Token Discord n'a pas été trouvé dans le fichier .env")

# Dictionnaire pour stocker la configuration
CONFIG = {}
try:
    # Liste des clés d'ID attendues (ajoutez ou retirez selon vos besoins)
    REQUIRED_INT_IDS = [
        'GUILD_ID', 'RULES_CHANNEL_ID', 'REGISTRATION_CHANNEL_ID',
        'VERIFIED_PLAYER_ROLE_ID', 'ADMIN_ROLE_ID',
        'PRESENTATION_CHANNEL_ID', 'JOUEUR_TEST_ROLE_ID',
        'ARRIVALS_CHANNEL_ID', 'DEPARTURES_CHANNEL_ID',
        'TICKET_CREATION_CHANNEL_ID', 'TICKET_CATEGORY_ID',
        'JOUEUR_CLUB_ROLE_ID', 'STREAM_ANNOUNCE_CHANNEL_ID',
        'STREAM_WATCH_ROLE_ID'
        
    ]
    OPTIONAL_INT_IDS = [
        'NEW_PLAYER_ROLE_ID',
        'AIDE_CHANNEL_ID',
        'AIDE_ROLE_ID',
        'TICKET_LOG_CHANNEL_ID',
        'EVALUATION_CATEGORY_ID',
        'STREAM_PING_ROLE_ID'
        
    ] 

    # Charger et convertir les IDs requis
    for key in REQUIRED_INT_IDS:
        value = os.getenv(key)
        if value is None or not value.isdigit():
            raise ValueError(f"Variable d'environnement requise '{key}' manquante ou invalide dans .env")
        CONFIG[key] = int(value)

    # Charger et convertir les IDs optionnels
    for key in OPTIONAL_INT_IDS:
        value = os.getenv(key)
        if value and value.isdigit():
            CONFIG[key] = int(value)
        else:
            CONFIG[key] = None # Mettre à None si absent ou invalide

    # Charger l'ID du message des règles (depuis fichier runtime)
    CONFIG['RULES_MESSAGE_ID'] = None # Initialiser

except (ValueError, TypeError) as e:
     # Attrape les erreurs de conversion int() et les ValueError explicites
     logger.critical(f"Erreur critique lors du chargement de la configuration depuis .env: {e}")
     # Vous pourriez vouloir arrêter le bot ici si la config est essentielle
     exit("Erreur de configuration critique.")


# --- Chargement de la configuration runtime ---
RUNTIME_CONFIG_PATH = 'data/config_runtime.json'
try:
    if os.path.exists(RUNTIME_CONFIG_PATH):
        with open(RUNTIME_CONFIG_PATH, 'r', encoding='utf-8') as f:
            try:
                runtime_data = json.load(f)
                rules_msg_id = runtime_data.get('rules_message_id')
                if isinstance(rules_msg_id, int):
                    CONFIG['RULES_MESSAGE_ID'] = rules_msg_id
                    logger.info(f"ID du message des règles chargé depuis {RUNTIME_CONFIG_PATH}: {CONFIG['RULES_MESSAGE_ID']}")
                elif rules_msg_id is not None:
                     logger.warning(f"rules_message_id trouvé dans {RUNTIME_CONFIG_PATH} mais n'est pas un entier valide.")

            except json.JSONDecodeError:
                 logger.error(f"Erreur de décodage JSON dans {RUNTIME_CONFIG_PATH}. Vérifiez le fichier.")
    else:
         logger.warning(f"Fichier {RUNTIME_CONFIG_PATH} non trouvé. L'ID du message des règles n'est pas chargé.")
         # Initialisation du fichier s'il n'existe pas
         try:
             os.makedirs(os.path.dirname(RUNTIME_CONFIG_PATH), exist_ok=True)
             with open(RUNTIME_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump({}, f)
         except Exception as e_create:
             logger.error(f"Impossible de créer le fichier runtime initial {RUNTIME_CONFIG_PATH}: {e_create}")

except Exception as e:
    logger.error(f"Erreur lors du chargement de {RUNTIME_CONFIG_PATH}: {e}")


# --- Configuration des Intents du Bot ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.presences = True

# --- Initialisation du Bot ---
bot = commands.Bot(command_prefix='!', intents=intents)
bot.config = CONFIG # Attachement de la configuration
bot.runtime_config_path = RUNTIME_CONFIG_PATH

# --- Fonction register_persistent_views (MISE À JOUR) ---
async def register_persistent_views():
    """Enregistre TOUTES les vues persistantes nécessaires au démarrage."""
    logger.info("Enregistrement des vues persistantes...")
    registered_views = 0
    # RegistrationView
    try:
        from cogs.registration import RegistrationView
        bot.add_view(RegistrationView(bot=bot))
        logger.info("-> Vue persistante RegistrationView enregistrée.")
        registered_views += 1
    except Exception as e: logger.error(f"Erreur enregistrement RegistrationView: {e}", exc_info=True)

    # TicketCreationView
    try:
        from cogs.ticket_system import TicketCreationView
        bot.add_view(TicketCreationView(bot=bot))
        logger.info("-> Vue persistante TicketCreationView enregistrée.")
        registered_views += 1
    except Exception as e: logger.error(f"Erreur enregistrement TicketCreationView: {e}", exc_info=True)

    # --- AJOUT : EvaluationActionView ---
    try:
        from cogs.evaluation import EvaluationActionView # Importer depuis le nouveau fichier
        # Créer une instance et l'enregistrer
        bot.add_view(EvaluationActionView(bot=bot))
        logger.info("-> Vue persistante EvaluationActionView enregistrée.")
        registered_views += 1
    except ImportError: logger.error("Impossible d'importer EvaluationActionView depuis cogs.evaluation.")
    except Exception as e: logger.error(f"Erreur enregistrement EvaluationActionView: {e}", exc_info=True)
    # --- FIN AJOUT ---

    logger.info(f"Enregistrement des vues persistantes terminé ({registered_views} vues).")

# --- Événements et Commandes de Chargement ---
@bot.event
async def on_ready():
    """Événement déclenché quand le bot est prêt et connecté."""
    logger.info(f'Connecté en tant que {bot.user.name} ({bot.user.id})')
    logger.info(f'Configuration chargée : {bot.config}')
    guild = bot.get_guild(bot.config['GUILD_ID'])
    if guild:
        logger.info(f'Opérationnel sur le serveur : {guild.name}')
        # Enregistrer les vues persistantes ICI après que le bot soit prêt
        # C'est plus sûr car on est sûr que le cache interne est prêt
        await register_persistent_views()
    else:
        logger.error(f"Le bot n'est pas sur le serveur spécifié avec l'ID {bot.config['GUILD_ID']} !")
    print("-" * 20)
    await bot.change_presence(activity=discord.Game(name="Observer les candidatures"))

async def load_cogs():
    """Charge tous les Cogs trouvés dans le dossier ./cogs"""
    logger.info("Chargement des Cogs...")
    loaded_cogs = []
    # Obtenir le chemin absolu du dossier où se trouve main.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Construire le chemin absolu vers le dossier 'cogs'
    cogs_dir = os.path.join(script_dir, 'cogs')
    logger.info(f"Recherche des Cogs dans : {cogs_dir}") # Log pour vérifier le chemin

    # Vérifier si le dossier cogs existe
    if not os.path.isdir(cogs_dir):
        logger.error(f"Le dossier des Cogs ({cogs_dir}) est introuvable !")
        logger.info("Chargement des Cogs terminé (ERREUR).")
        return # Arrêter le chargement si le dossier n'existe pas

    # Lister les fichiers dans le chemin absolu du dossier cogs
    for filename in os.listdir(cogs_dir):
        if filename.endswith('.py') and not filename.startswith('_'):
            cog_name = f'cogs.{filename[:-3]}'
            try:
                await bot.load_extension(cog_name)
                logger.info(f'Cog chargé avec succès : {cog_name}')
                loaded_cogs.append(cog_name)
            except commands.ExtensionError as e:
                logger.error(f'Erreur lors du chargement du Cog {cog_name}: {e.__class__.__name__} - {e}', exc_info=True)
            except Exception as e:
                 logger.error(f'Erreur inattendue lors du chargement du Cog {cog_name}: {e}', exc_info=True)
    logger.info(f"Chargement des Cogs terminé. Cogs chargés: {', '.join(loaded_cogs) if loaded_cogs else 'Aucun'}")

async def register_persistent_views():
    """Enregistre les vues persistantes nécessaires au démarrage."""
    # Importe la vue ici pour éviter les imports circulaires au niveau global
    try:
        from cogs.registration import RegistrationView
        # Si la vue prend des arguments (comme 'bot'), on les passe
        view_instance = RegistrationView(bot=bot)
        bot.add_view(view_instance)
        logger.info(f"Vue persistante {view_instance.__class__.__name__} enregistrée.")
    except ImportError:
        logger.error("Impossible d'importer RegistrationView depuis cogs.registration pour l'enregistrement persistant.")
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement de la vue persistante: {e}", exc_info=True)


async def main():
    """Fonction principale pour démarrer le bot."""
    async with bot:
        await load_cogs()
        # L'enregistrement des vues se fait dans on_ready maintenant
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arrêt du bot demandé par l'utilisateur.")
    except Exception as e:
        logger.critical(f"Erreur critique non gérée au niveau principal: {e}", exc_info=True)