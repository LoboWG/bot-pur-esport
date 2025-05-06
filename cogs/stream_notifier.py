# cogs/stream_notifier.py
import discord
from discord.ext import commands
import logging
import datetime

logger = logging.getLogger(__name__)

class StreamNotifierCog(commands.Cog, name="StreamNotifier"):
    """Cog pour annoncer les streams des membres ayant un rôle spécifique."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Utiliser un set pour garder en mémoire les membres qui sont déjà notifiés comme étant en live
        # pour éviter les notifications répétées lors de petites fluctuations de statut.
        self.currently_live = set()

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        """Déclenché quand le statut/activité d'un membre change."""

        # 1. Vérifier si c'est le bon serveur
        guild_id = self.bot.config.get('GUILD_ID')
        if not guild_id or after.guild.id != guild_id:
            return

        # 2. Récupérer les IDs de config nécessaires
        streamer_role_id = self.bot.config.get('STREAM_WATCH_ROLE_ID')
        announce_channel_id = self.bot.config.get('STREAM_ANNOUNCE_CHANNEL_ID')
        ping_role_id = self.bot.config.get('STREAM_PING_ROLE_ID') # Optionnel

        # Si la config de base manque, on ne peut rien faire
        if not streamer_role_id or not announce_channel_id:
            # logger.debug("Config stream manquante (rôle à suivre ou salon annonce)") # Log trop verbeux peut-être
            return

        # 3. Récupérer l'objet rôle à suivre
        streamer_role = after.guild.get_role(streamer_role_id)
        if not streamer_role:
            # logger.warning(f"Rôle à suivre ({streamer_role_id}) introuvable.") # Log une seule fois peut-être dans setup?
            return

        # 4. Vérifier si le membre a le rôle requis
        if streamer_role not in after.roles:
            # Si le membre n'a plus le rôle et était en live, on le retire du suivi
            if after.id in self.currently_live:
                self.currently_live.remove(after.id)
                # logger.debug(f"{after.name} n'a plus le rôle streamer, retiré du suivi live.")
            return

        # 5. Détecter si un stream Twitch/YouTube VIENT DE COMMENCER
        streaming_before = any(isinstance(activity, discord.Streaming) for activity in before.activities)
        streaming_after = any(isinstance(activity, discord.Streaming) for activity in after.activities)

        # Cas 1: Le membre commence à streamer et n'était pas notifié avant
        if not streaming_before and streaming_after and after.id not in self.currently_live:
            # Trouver l'activité de streaming
            stream_activity = None
            for activity in after.activities:
                if isinstance(activity, discord.Streaming):
                    # On vérifie si c'est Twitch ou YouTube (platform peut être None parfois)
                    if activity.platform and activity.platform.lower() in ["twitch", "youtube"]:
                         stream_activity = activity
                         break # On prend le premier stream Twitch/YouTube trouvé

            if stream_activity:
                # Ajouter au suivi pour éviter double notif
                self.currently_live.add(after.id)
                logger.info(f"Stream détecté pour {after.name} ({after.id}) sur {stream_activity.platform}: {stream_activity.name} ({stream_activity.url})")

                # Envoyer l'annonce
                announce_channel = after.guild.get_channel(announce_channel_id)
                if announce_channel and isinstance(announce_channel, discord.TextChannel):
                    ping_role = after.guild.get_role(ping_role_id) if ping_role_id else None
                    ping_mention = ping_role.mention if ping_role else ""

                    embed = discord.Embed(
                        title=f"🔴 {after.display_name} est en live !",
                        description=f"**{stream_activity.name}**\n{stream_activity.details if stream_activity.details else 'Regardez maintenant !'}",
                        url=stream_activity.url,
                        color=discord.Color.purple() if stream_activity.platform.lower() == "twitch" else discord.Color.red(), # Couleur différente pour Twitch/YT
                        timestamp=discord.utils.utcnow()
                    )
                    embed.set_thumbnail(url=after.display_avatar.url)
                    # Ajouter le nom du jeu si disponible et différent du titre du stream
                    if stream_activity.game and stream_activity.game != stream_activity.name:
                         embed.add_field(name="Jeu", value=stream_activity.game, inline=False)

                    embed.set_footer(text=f"Plateforme: {stream_activity.platform}")

                    try:
                        await announce_channel.send(content=ping_mention, embed=embed)
                        logger.info(f"Annonce envoyée pour le live de {after.name}")
                    except Exception as e:
                        logger.error(f"Erreur envoi annonce live {after.name}: {e}")
                else:
                     logger.error(f"Salon d'annonce stream ({announce_channel_id}) introuvable/invalide.")

        # Cas 2: Le membre arrête de streamer (ou son activité change) et il était suivi
        elif streaming_before and not streaming_after and after.id in self.currently_live:
             self.currently_live.remove(after.id)
             logger.info(f"Stream terminé (ou plus détecté) pour {after.name} ({after.id}). Retiré du suivi.")
             # On pourrait envoyer un message "Live terminé" mais ça peut être spammy


# Fonction setup
async def setup(bot: commands.Bot):
    # Vérification config
    required_ids = ['GUILD_ID', 'STREAM_ANNOUNCE_CHANNEL_ID', 'STREAM_WATCH_ROLE_ID']
    optional_ids = ['STREAM_PING_ROLE_ID']
    missing = [k for k in required_ids if not bot.config.get(k)]
    if missing: logger.error(f"Config manquante StreamNotifierCog: {', '.join(missing)}. Le Cog risque de mal fonctionner.")
    else: logger.info("Configuration nécessaire pour StreamNotifierCog trouvée.")

    await bot.add_cog(StreamNotifierCog(bot))
    logger.info("Cog StreamNotifier chargé.")