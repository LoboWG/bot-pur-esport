# cogs/member_events.py
import discord
from discord.ext import commands
import logging
import datetime
from discord import utils

logger = logging.getLogger(__name__)

# --- Helper Function pour formater la durée ---
def format_duration(duration: datetime.timedelta) -> str:
    """Formate un timedelta en une chaîne lisible (jours, heures, minutes)."""
    days = duration.days
    seconds = duration.seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    parts = []
    if days > 0: parts.append(f"{days} jour{'s' if days > 1 else ''}")
    if hours > 0: parts.append(f"{hours} heure{'s' if hours > 1 else ''}")
    if minutes > 0: parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")

    if not parts:
         if duration.total_seconds() < 60 and duration.total_seconds() >= 0: return "il y a quelques instants"
         else: return "depuis un court instant"

    if len(parts) == 1: return "depuis " + parts[0]
    elif len(parts) == 2: return "depuis " + parts[0] + " et " + parts[1]
    else: return "depuis " + parts[0] + ", " + parts[1] + " et " + parts[2]


class MemberEventsCog(commands.Cog):
    """Cog pour gérer les événements d'arrivée et de départ des membres."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # === Fonction on_member_join MODIFIÉE pour utiliser les Champs ===
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Envoyé lorsqu'un membre rejoint le serveur."""
        guild = member.guild
        guild_id = self.bot.config.get('GUILD_ID')
        if not guild_id or guild.id != guild_id: return

        arrivals_channel_id = self.bot.config.get('ARRIVALS_CHANNEL_ID')
        if not arrivals_channel_id: return logger.warning("ARRIVALS_CHANNEL_ID non configuré.")

        arrivals_channel = guild.get_channel(arrivals_channel_id)
        if not arrivals_channel or not isinstance(arrivals_channel, discord.TextChannel):
            return logger.error(f"Salon arrivées ({arrivals_channel_id}) introuvable/invalide.")

        logger.info(f"Nouveau membre rejoint : {member.name} ({member.id})")

        # --- Préparation des informations et mentions ---
        member_count = guild.member_count
        server_name = guild.name
        rules_channel_id = self.bot.config.get('RULES_CHANNEL_ID')
        registration_channel_id = self.bot.config.get('REGISTRATION_CHANNEL_ID')
        ticket_channel_id = self.bot.config.get('AIDE_CHANNEL_ID')

        # Mentions (avec fallback texte)
        rules_channel_mention = f"`#{(guild.get_channel(rules_channel_id) or 'règlement').name}`"
        if rules_channel_id and (chan := guild.get_channel(rules_channel_id)): rules_channel_mention = chan.mention

        registration_channel_mention = f"`#{(guild.get_channel(registration_channel_id) or 'enregistrement-joueur').name}`"
        if registration_channel_id and (chan := guild.get_channel(registration_channel_id)): registration_channel_mention = chan.mention

        ticket_channel_mention = f"`#{(guild.get_channel(ticket_channel_id) or 'sos-ticket').name}`"
        if ticket_channel_id and (chan := guild.get_channel(ticket_channel_id)): ticket_channel_mention = chan.mention

        # --- Création de l'embed d'arrivée avec Champs ---
        embed = discord.Embed(
            title=f"👋 Bienvenue sur {server_name}, {member.display_name} !",
            # Description plus courte : juste le message de bienvenue et le compte
            description=(
                f"{member.mention} vient de nous rejoindre.\n"
                f"Nous sommes désormais **{member_count}** membres ✨\n\n"
                # On enlève les étapes d'ici
            ),
            color=discord.Color.blue() # Ou une autre couleur
        )
        embed.set_thumbnail(url=member.display_avatar.url) # Avatar du membre

        # --- AJOUT DES CHAMPS pour les étapes ---
        embed.add_field(
            name="1️⃣ Valider le Règlement",
            value=f"Lis et valide le règlement dans {rules_channel_mention}.",
            inline=False # Chaque étape sur sa propre ligne
        )
        embed.add_field(
            name="2️⃣ Enregistrer ton Joueur",
            value=f"Complète ton profil joueur dans {registration_channel_mention}.",
            inline=False
        )
        embed.add_field(
            name="3️⃣ Besoin d'Aide ?",
            value=f"N'hésite pas à créer un ticket dans {ticket_channel_mention}.",
            inline=False
        )
        # Ajouter la conclusion comme un champ sans titre (ou avec un titre comme "Et ensuite ?")
        embed.add_field(
            name="\u200b", # Caractère invisible pour un champ sans titre apparent
            value="*Voila tu sais tout et c'est maintenant à toi de jouer et passons de bon moments ensemble!*",
            inline=False
        )
        # --- FIN AJOUT CHAMPS ---


        embed.set_footer(text=f"ID: {member.id}") # Footer minimaliste

        # --- Image bannière pour l'arrivée (code existant) ---
        # Assurez-vous que l'URL est la bonne et que l'image est plutôt paysage
        IMAGE_URL_BANNIERE_ARRIVEE = "https://i.imgur.com/XKAuUKv.png" # URL de votre fichier

        # Le check avec "URL_DE_VOTRE_IMAGE_BIENVENUE_ICI" n'est plus utile si vous avez mis la vraie URL
        if IMAGE_URL_BANNIERE_ARRIVEE:
            try:
                embed.set_image(url=IMAGE_URL_BANNIERE_ARRIVEE)
                logger.info(f"Ajout de l'image de bienvenue pour {member.name}")
            except Exception as e_img:
                 logger.error(f"Impossible définir image arrivée (URL: {IMAGE_URL_BANNIERE_ARRIVEE}): {e_img}")
        else:
            logger.info("Pas d'URL configurée pour l'image bannière d'arrivée.")

        # --- Envoyer l'embed ---
        try:
            await arrivals_channel.send(embed=embed)
        except discord.Forbidden:
            logger.error(f"Permissions manquantes (Send Messages/Embed Links) dans {arrivals_channel.name}")
        except Exception as e:
             logger.error(f"Erreur inattendue envoi arrivée pour {member.name}: {e}", exc_info=True)
    # === FIN DE on_member_join ===


    # === Fonction on_member_remove (inchangée) ===
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Envoyé lorsqu'un membre quitte le serveur."""
        # ... (Tout le code de on_member_remove reste exactement comme dans votre fichier) ...
        guild_id = self.bot.config.get('GUILD_ID')
        if not guild_id or member.guild.id != guild_id: return

        departures_channel_id = self.bot.config.get('DEPARTURES_CHANNEL_ID')
        if not departures_channel_id: return logger.warning("DEPARTURES_CHANNEL_ID non configuré.")

        departures_channel = member.guild.get_channel(departures_channel_id)
        if not departures_channel or not isinstance(departures_channel, discord.TextChannel):
             return logger.error(f"Salon départs ({departures_channel_id}) introuvable/invalide.")

        logger.info(f"Membre parti : {member.name} ({member.id})")

        duration_text = "a rejoint le serveur"
        if member.joined_at:
            try:
                now = utils.utcnow(); duration = now - member.joined_at
                if duration.total_seconds() >= 0: duration_text = f"était avec nous {format_duration(duration)}"
                else: duration_text += f" le {utils.format_dt(member.joined_at, style='D')}"
            except Exception as e:
                 logger.error(f"Erreur calcul durée {member.name}: {e}")
                 duration_text += f" le {utils.format_dt(member.joined_at, style='D')}" if member.joined_at else ""
        else: duration_text = "Présence de durée inconnue"

        embed = discord.Embed(
            title="😥 Un membre nous a quittés...",
            description=f"Merci et à bientôt **{member.display_name}** ({str(member)}) !",
            color=discord.Color.from_rgb(255, 140, 0)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=duration_text)

        IMAGE_URL_BANNIERE_DEPART = "https://i.imgur.com/XKAuUKv.png" # Gardez VOTRE URL ici
        # Simplification de la condition
        if IMAGE_URL_BANNIERE_DEPART:
             try: embed.set_image(url=IMAGE_URL_BANNIERE_DEPART)
             except Exception as e_img: logger.error(f"Err image départ URL({IMAGE_URL_BANNIERE_DEPART}): {e_img}")
        else: logger.info("Pas d'URL image bannière départ.")

        try: await departures_channel.send(embed=embed)
        except Exception as e: logger.error(f"Erreur envoi départ {member.name}: {e}", exc_info=True)
    # === FIN de on_member_remove ===


# Fonction setup (inchangée)
async def setup(bot: commands.Bot):
    # ... (code setup inchangé) ...
    required_ids = ['GUILD_ID', 'ARRIVALS_CHANNEL_ID', 'DEPARTURES_CHANNEL_ID']
    # Ajouter ici les IDs optionnels utilisés dans on_member_join si on veut logger leur absence
    optional_check = ['RULES_CHANNEL_ID', 'REGISTRATION_CHANNEL_ID', 'AIDE_CHANNEL_ID']
    missing_ids = [id_name for id_name in required_ids + optional_check if not bot.config.get(id_name)]
    if missing_ids: logger.warning(f"Config manquante/invalide pour MemberEventsCog: {', '.join(missing_ids)}. Certaines mentions pourraient ne pas fonctionner.")
    # else: logger.info("Configuration nécessaire pour MemberEventsCog trouvée.")
    await bot.add_cog(MemberEventsCog(bot))
    logger.info("Cog MemberEvents chargé.")