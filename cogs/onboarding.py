# cogs/onboarding.py
import discord
from discord.ext import commands
import logging
import json
import os
# Importe la classe de la Vue depuis registration.py
# Cette ligne causera une erreur si registration.py a une SyntaxError
from .registration import RegistrationView

logger = logging.getLogger(__name__)

class OnboardingCog(commands.Cog):
    """Cog pour gérer l'arrivée des nouveaux membres et la validation des règles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Récupère l'ID depuis la config chargée dans main.py
        self.rules_message_id = self.bot.config.get('RULES_MESSAGE_ID')

    def save_rules_message_id(self, message_id: int):
        """Sauvegarde l'ID du message des règles dans config_runtime.json"""
        try:
            data = {}
            try:
                with open(self.bot.runtime_config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                logger.warning(f"Fichier {self.bot.runtime_config_path} non trouvé ou invalide lors de la lecture pour sauvegarde. Création/Écrasement.")
            except Exception as e_read:
                 logger.error(f"Erreur de lecture de {self.bot.runtime_config_path}: {e_read}")
                 return # Ne pas continuer si on ne peut pas lire

            data['rules_message_id'] = message_id
            with open(self.bot.runtime_config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)

            self.bot.config['RULES_MESSAGE_ID'] = message_id
            self.rules_message_id = message_id
            logger.info(f"ID du message des règles ({message_id}) sauvegardé dans {self.bot.runtime_config_path} et mis à jour en mémoire.")

        except IOError as e:
            logger.error(f"Erreur d'écriture lors de la sauvegarde de l'ID du message des règles: {e}")
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la sauvegarde de l'ID du message des règles: {e}")


    @commands.command(name='postrules', help="Poste le message des règles et enregistre son ID.")
    @commands.has_role(int(os.getenv('ADMIN_ROLE_ID'))) # Assurez-vous que ADMIN_ROLE_ID est bien un int dans config
    async def post_rules_message(self, ctx: commands.Context):
        """(Re)poste le message des règles."""
        rules_channel_id = self.bot.config.get('RULES_CHANNEL_ID')
        if not rules_channel_id:
             await ctx.send("Erreur : RULES_CHANNEL_ID non configuré.")
             logger.error("RULES_CHANNEL_ID non trouvé dans bot.config")
             return

        rules_channel = self.bot.get_channel(rules_channel_id)
        if not rules_channel or not isinstance(rules_channel, discord.TextChannel):
            await ctx.send(f"Erreur : Salon des règles ({rules_channel_id}) introuvable/invalide.")
            logger.error(f"Salon des règles introuvable ou invalide : {rules_channel_id}")
            return

        # --- Message Embed ---
        embed = discord.Embed(
            title="📜 Règlement et Présentation de Pur Esport 📜",
            description=(
                "Bienvenue sur le serveur de **Pur Esport** !\n\n"
                # ... (votre texte) ...
                "**Si vous êtes d'accord avec ces points et souhaitez continuer, réagissez avec ✅ à ce message.**"
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="Pur Esport - La gagne avant tout !")
        # --- Fin Embed ---

        try:
            # Supprimer l'ancien message si possible
            if self.rules_message_id:
                 try:
                     old_message = await rules_channel.fetch_message(self.rules_message_id)
                     await old_message.delete()
                     logger.info(f"Ancien message des règles ({self.rules_message_id}) supprimé.")
                 except Exception: pass # Ignore si non trouvé ou erreur

            # Envoyer le nouveau
            rules_message = await rules_channel.send(embed=embed)
            await rules_message.add_reaction("✅")
            self.save_rules_message_id(rules_message.id)
            await ctx.send(f"Message des règles posté dans {rules_channel.mention} (ID: {rules_message.id}).", delete_after=15)
            logger.info(f"Message des règles posté par {ctx.author}, ID: {rules_message.id}")
        except discord.Forbidden:
            await ctx.send("Erreur : Permissions manquantes pour envoyer/réagir dans le salon des règles.")
            logger.error(f"Permissions manquantes dans {rules_channel.name}")
        except Exception as e:
            await ctx.send(f"Erreur inattendue lors de l'envoi du message des règles: {e}")
            logger.error(f"Erreur dans post_rules_message: {e}", exc_info=True)
        try: await ctx.message.delete(delay=15)
        except Exception: pass


    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Attribue le rôle vérifié et envoie le bouton d'enregistrement."""
        if payload.user_id == self.bot.user.id or not self.rules_message_id or payload.message_id != self.rules_message_id or str(payload.emoji) != '✅':
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild: return
        member = guild.get_member(payload.user_id)
        if not member: return

        verified_role_id = self.bot.config.get('VERIFIED_PLAYER_ROLE_ID')
        new_player_role_id = self.bot.config.get('NEW_PLAYER_ROLE_ID')
        reg_channel_id = self.bot.config.get('REGISTRATION_CHANNEL_ID')

        if not verified_role_id or not reg_channel_id:
            logger.error("VERIFIED_PLAYER_ROLE_ID ou REGISTRATION_CHANNEL_ID manquant dans la config!")
            return

        verified_role = guild.get_role(verified_role_id)
        if not verified_role:
            logger.error(f"Rôle vérifié ({verified_role_id}) introuvable.")
            return

        if verified_role in member.roles: return # Déjà vérifié

        # === Attribution du rôle Vérifié ===
        try:
            await member.add_roles(verified_role, reason="A accepté le règlement via réaction.")
            logger.info(f"Rôle '{verified_role.name}' ajouté à {member.display_name}.")

            # Retirer ancien rôle si configuré et présent
            if new_player_role_id:
                new_player_role = guild.get_role(new_player_role_id)
                if new_player_role and new_player_role in member.roles:
                    try: await member.remove_roles(new_player_role, reason="Règlement accepté.")
                    except Exception as e_rem: logger.warning(f"Impossible de retirer le rôle Nouveau Joueur pour {member.name}: {e_rem}")

            # === Envoyer le message avec le bouton ===
            reg_channel = guild.get_channel(reg_channel_id)
            if reg_channel and isinstance(reg_channel, discord.TextChannel):
                try:
                    # Créer et envoyer la vue avec le bouton
                    view = RegistrationView(bot=self.bot) # Assurez-vous que RegistrationView est importé
                    welcome_message = (
                        f"Bienvenue {member.mention} ! Vous avez accepté le règlement.\n\n"
                        "Cliquez sur le bouton ci-dessous pour commencer votre enregistrement :"
                    )
                    await reg_channel.send(welcome_message, view=view)
                    logger.info(f"Message avec bouton d'enregistrement envoyé à {member.name} dans {reg_channel.name}")
                except discord.Forbidden:
                    logger.error(f"Permissions manquantes pour envoyer le message avec bouton dans {reg_channel.name}")
                except Exception as e_send:
                    logger.error(f"Erreur lors de l'envoi du message avec bouton: {e_send}")
            else:
                 logger.warning(f"Salon d'enregistrement ({reg_channel_id}) introuvable ou invalide.")

        except discord.Forbidden:
            logger.error(f"Permissions manquantes pour ajouter le rôle '{verified_role.name}' à {member.display_name}.")
            try: await member.send(f"Je n'ai pas pu vous ajouter le rôle '{verified_role.name}'. Contactez un admin (problème de hiérarchie?).")
            except Exception: pass
        except Exception as e_add:
             logger.error(f"Erreur lors de l'attribution du rôle Vérifié à {member.name}: {e_add}", exc_info=True)


    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Attribue le rôle Nouveau Joueur à l'arrivée."""
        guild_id = self.bot.config.get('GUILD_ID')
        if not guild_id or member.guild.id != guild_id: return

        new_player_role_id = self.bot.config.get('NEW_PLAYER_ROLE_ID')
        if new_player_role_id:
            role = member.guild.get_role(new_player_role_id)
            if role:
                try: await member.add_roles(role, reason="Nouveau membre rejoint.")
                except Exception as e: logger.error(f"Impossible d'ajouter le rôle Nouveau Joueur à {member.name}: {e}")
            else: logger.warning(f"Rôle Nouveau Joueur ({new_player_role_id}) introuvable.")


# Fonction setup
async def setup(bot: commands.Bot):
    # Vérifier config
    required_ids = ['ADMIN_ROLE_ID', 'RULES_CHANNEL_ID', 'VERIFIED_PLAYER_ROLE_ID', 'REGISTRATION_CHANNEL_ID', 'GUILD_ID'] # IDs requis pour ce Cog
    missing_ids = [id_name for id_name in required_ids if not bot.config.get(id_name)]
    if missing_ids:
        logger.error(f"Config manquante pour OnboardingCog: {', '.join(missing_ids)}. Le Cog risque de mal fonctionner.")
    # Charger le Cog
    await bot.add_cog(OnboardingCog(bot))
    logger.info("Cog Onboarding chargé.")