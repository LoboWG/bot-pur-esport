# cogs/ticket_system.py
import discord
from discord.ext import commands
from discord import ui, utils, app_commands
import logging
import asyncio
import re # Pour nettoyer les noms de salon

logger = logging.getLogger(__name__)

# --- Fonction pour nettoyer nom de salon ---
def sanitize_channel_name(name):
    name = name.lower()
    name = re.sub(r'[^\w-]', '', name) # Garde alphanumérique, underscore, tiret
    name = re.sub(r'[-_]+', '-', name) # Remplace multiples par un seul tiret
    return name[:90] # Limite la longueur

# --- Dictionnaire EN MEMOIRE pour suivre les tickets ouverts ---
# Clé: user_id (int), Valeur: channel_id (int)
# Sera perdu au redémarrage ! Pour la persistance, utiliser DB/fichier.
open_tickets_state = {}

# --- Vue Persistante pour le bouton de création ---
class TicketCreationView(ui.View):
    """Vue persistante avec le bouton 'Créer un ticket'."""
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None) # Persistante
        self.bot = bot

    @ui.button(label="Créer un ticket", style=discord.ButtonStyle.primary, custom_id="create_ticket_button", emoji="➕")
    async def create_ticket_callback(self, interaction: discord.Interaction, button: ui.Button):
        """Callback pour créer un nouveau salon de ticket."""
        user = interaction.user
        guild = interaction.guild
        logger.info(f"Ticket creation requested by {user} ({user.id})")

        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except discord.NotFound: # L'interaction peut parfois expirer très vite
            logger.warning("Interaction for ticket creation already expired before defer.")
            return
        except Exception as e_defer:
             logger.error(f"Error during initial defer for ticket creation: {e_defer}")
             # Essayer d'envoyer un message d'erreur si possible, sinon abandonner
             try: await interaction.followup.send("Une erreur s'est produite au début du traitement.", ephemeral=True)
             except: pass
             return

        if not guild: return await interaction.response.send_message("Erreur interne (Guilde).", ephemeral=True)

        # --- Vérification: Ticket déjà ouvert ? ---
        if user.id in open_tickets_state:
            existing_channel_id = open_tickets_state[user.id]
            existing_channel = guild.get_channel(existing_channel_id)
            if existing_channel:
                logger.warning(f"{user} tried to open ticket, already has {existing_channel.mention}")
                return await interaction.response.send_message(f"Vous avez déjà un ticket ouvert : {existing_channel.mention}", ephemeral=True)
            else:
                logger.info(f"Cleaning up non-existent ticket channel {existing_channel_id} for {user}")
                try: del open_tickets_state[user.id]
                except KeyError: pass

        # --- Récupération de la configuration ---
        category_id = self.bot.config.get('TICKET_CATEGORY_ID')
        staff_role_ids = self.bot.config.get('TICKET_STAFF_ROLE_IDS', [])
        log_channel_id = self.bot.config.get('TICKET_LOG_CHANNEL_ID') # Optionnel

        category = guild.get_channel(category_id) if category_id else None
        if category_id and (not category or not isinstance(category, discord.CategoryChannel)):
            logger.error(f"Ticket category ID {category_id} invalid.")
            category = None
            logger.warning("Création du ticket hors catégorie.")

        staff_roles = [guild.get_role(role_id) for role_id in staff_role_ids]
        staff_roles = [role for role in staff_roles if role]
        if not staff_roles and staff_role_ids:
             logger.error(f"Aucun rôle staff valide trouvé pour IDs: {staff_role_ids}")

        # --- Préparation des permissions ---
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, embed_links=True, manage_messages=True, read_message_history=True)
        }
        staff_mentions = []
        for role in staff_roles:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True, read_message_history=True, manage_messages=True)
            staff_mentions.append(role.mention)

        # --- Création du salon ---
        channel_name = f"ticket-{sanitize_channel_name(user.name)}-{str(user.id)[-4:]}"
        new_channel = None
        try:
            reason = f"Ticket créé par {str(user)} ({user.id})"
            # Stocke l'ID créateur dans le topic pour la commande /closeticket
            topic = f"Ticket de {str(user)} (ID: {user.id}). Créé le {utils.utcnow().strftime('%d/%m/%Y %H:%M')} UTC. CréateurID:{user.id}"
            new_channel = await guild.create_text_channel(
                name=channel_name, category=category, overwrites=overwrites, topic=topic, reason=reason
            )
            logger.info(f"Ticket channel created: {new_channel.name} ({new_channel.id}) for {user}")
            open_tickets_state[user.id] = new_channel.id # Ajouter au suivi global

        except discord.Forbidden:
            logger.error(f"Permissions manquantes pour créer ticket pour {user.name}.")
            return await interaction.response.send_message("Permissions manquantes pour créer le salon ticket.", ephemeral=True)
        except Exception as e:
             logger.error(f"Erreur création ticket pour {user.name}: {e}", exc_info=True)
             return await interaction.response.send_message("Erreur lors de la création du ticket.", ephemeral=True)

        # --- Actions post-création ---
        if new_channel:
            try:
                # Vue avec bouton Fermer (attachée au message, timeout long)
                close_view = TicketCloseView(bot=self.bot, ticket_channel_id=new_channel.id, creator_id=user.id)
                staff_mention_str = " ".join(staff_mentions) if staff_mentions else "(non configuré)"
                welcome_embed = discord.Embed(
                    title=f"Ticket ouvert par {user.display_name}",
                    description=(f"Bienvenue {user.mention} !\n\n"
                                 f"Décrivez votre problème/question.\n"
                                 f"Staff notifié: {staff_mention_str}\n\n"
                                 "Utilisez le bouton ci-dessous ou la commande `!closeticket` pour fermer."),
                    color=discord.Color.blurple()
                )
                # Note : Le message d'accueil peut être personnalisé davantage
                await new_channel.send(embed=welcome_embed, view=close_view)
            except Exception as e_msg: logger.error(f"Erreur envoi message initial ticket {new_channel.name}: {e_msg}")

            try: await interaction.followup.send(f"Votre ticket a été créé : {new_channel.mention}", ephemeral=True)
            except Exception as e_followup: logger.error(f"Erreur followup création ticket: {e_followup}")

            # Log (optionnel)
            if log_channel_id:
                log_channel = guild.get_channel(log_channel_id)
                if log_channel and isinstance(log_channel, discord.TextChannel):
                    log_embed = discord.Embed(
                         title="📝 Nouveau Ticket Créé",
                         color=discord.Color.green(),
                         timestamp=utils.utcnow()
                     )
                    log_embed.add_field(name="Créateur", value=f"{user.mention} ({user.id})", inline=False)
                    log_embed.add_field(name="Salon Ticket", value=f"{new_channel.mention} ({new_channel.id})", inline=False)
                    try: await log_channel.send(embed=log_embed)
                    except Exception as e_log: logger.error(f"Erreur envoi log création ticket: {e_log}")


# --- Vue pour le bouton de fermeture ---
class TicketCloseView(ui.View):
     def __init__(self, bot: commands.Bot, ticket_channel_id: int, creator_id: int):
        super().__init__(timeout=3*24*60*60) # 3 jours timeout
        self.bot = bot
        self.ticket_channel_id = ticket_channel_id
        self.creator_id = creator_id
        self.closing = False # Sécurité anti-double clic

     async def on_timeout(self):
         logger.info(f"Vue fermeture ticket {self.ticket_channel_id} expirée.")
         # Idéalement, trouver le message et retirer la vue, mais complexe ici.

     @ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_button_in_channel", emoji="🔒")
     async def close_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        if self.closing: return await interaction.response.defer()
        self.closing = True

        user = interaction.user; channel = interaction.channel; guild = interaction.guild
        staff_role_ids = self.bot.config.get('TICKET_STAFF_ROLE_IDS', [])
        # Vérifier si l'utilisateur a un des rôles staff ou est le créateur
        is_staff = any(role.id in staff_role_ids for role in getattr(user, 'roles', []))
        is_creator = user.id == self.creator_id

        if not is_staff and not is_creator:
            self.closing = False
            return await interaction.response.send_message("Seul le créateur ou le staff peut fermer.", ephemeral=True)

        # Vérifier si on est bien dans le bon salon (au cas où la vue serait corrompue/mal utilisée)
        if not channel or channel.id != self.ticket_channel_id:
             self.closing = False
             logger.warning(f"Tentative de fermeture de ticket via bouton dans un mauvais salon ({channel.id} vs {self.ticket_channel_id})")
             return await interaction.response.send_message("Erreur interne: Action invalide ici.", ephemeral=True)

        # --- Fermeture ---
        try:
            button.disabled = True # Griser le bouton
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"🔒 Fermeture du ticket par {user.mention} dans 10 secondes...")
            logger.info(f"Fermeture ticket {channel.name} par {user.name} (bouton).")
            await asyncio.sleep(10)
            await channel.delete(reason=f"Ticket fermé par {str(user)} (bouton).")
            logger.info(f"Salon ticket {channel.name} ({channel.id}) supprimé.")

            # Nettoyer état mémoire global
            if self.creator_id in open_tickets_state and open_tickets_state[self.creator_id] == channel.id:
                 del open_tickets_state[self.creator_id]
                 logger.info(f"Ticket {channel.id} retiré état mémoire pour {self.creator_id}.")

            # Log optionnel ...
            log_channel_id = self.bot.config.get('TICKET_LOG_CHANNEL_ID')
            if log_channel_id:
                log_channel = guild.get_channel(log_channel_id)
                if log_channel and isinstance(log_channel, discord.TextChannel):
                     log_embed = discord.Embed(
                         title="🔒 Ticket Fermé (Bouton)",
                         description=f"Le ticket `{channel.name}` créé par <@{self.creator_id}> a été fermé par {user.mention}.",
                         color=discord.Color.red(), timestamp=utils.utcnow()
                     )
                     try: await log_channel.send(embed=log_embed)
                     except Exception as e_log: logger.error(f"Erreur log fermeture ticket: {e_log}")

        except discord.NotFound:
             logger.warning(f"Tentative de fermeture d'un ticket déjà supprimé: {channel.name}")
             # Le followup peut échouer si le channel a déjà été supprimé par une autre action
             try: await interaction.followup.send("Le salon semble déjà supprimé.", ephemeral=True)
             except: pass
        except discord.Forbidden:
             logger.error(f"Permissions manquantes pour fermer/supprimer ticket {channel.name}")
             await interaction.followup.send("Permissions manquantes pour supprimer ce salon.", ephemeral=True)
        except Exception as e:
             logger.error(f"Erreur fermeture ticket {channel.name} (bouton): {e}", exc_info=True)
             try: await interaction.followup.send("Erreur interne lors de la fermeture.", ephemeral=True)
             except: pass
        finally:
            self.closing = False # Important pour permettre une nouvelle tentative si échec


# --- Classe Cog Système de Tickets ---
class TicketSystemCog(commands.Cog, name="TicketSystemCog"):
    """Cog pour gérer le système de tickets."""

    # --- Méthode __init__ CORRIGÉE ---
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Référence le dictionnaire global pour l'état partagé
        self.open_tickets = open_tickets_state
        logger.info("TicketSystemCog initialisé.")
    # --- FIN CORRECTION ---

    @commands.command(name="setuptickets", aliases=["setticket"])
    @commands.has_permissions(administrator=True)
    async def setup_ticket_button(self, ctx: commands.Context):
        """Poste le message initial avec le bouton pour créer des tickets."""
        target_channel_id = self.bot.config.get('TICKET_CREATION_CHANNEL_ID')
        if not target_channel_id: return await ctx.send("Erreur: `TICKET_CREATION_CHANNEL_ID` non configuré.")

        target_channel = ctx.guild.get_channel(target_channel_id)
        if not target_channel or not isinstance(target_channel, discord.TextChannel):
             return await ctx.send(f"Erreur: Salon ({target_channel_id}) introuvable/invalide.")

        embed = discord.Embed(
            title="Support & Aide - Création de Ticket",
            description="Besoin d'aide ? Des questions ? Un problème à signaler ?\n\n"
                        "Cliquez sur le bouton ci-dessous pour ouvrir un salon privé où le staff pourra vous assister.",
            color=discord.Color.dark_blue()
        )
        embed.set_footer(text="Merci de ne pas abuser de ce système.")
        view = TicketCreationView(bot=self.bot) # La vue persistante

        try:
            await target_channel.send(embed=embed, view=view)
            await ctx.send(f"Message de création de ticket envoyé dans {target_channel.mention}.", ephemeral=True)
            logger.info(f"Setup tickets par {ctx.author} dans {target_channel.name}")
        except discord.Forbidden:
             await ctx.send(f"Erreur: Permissions manquantes pour envoyer le message dans {target_channel.mention}.", ephemeral=True)
        except Exception as e:
             await ctx.send(f"Erreur envoi message setup: {e}", ephemeral=True)
             logger.error(f"Erreur setup tickets: {e}", exc_info=True)


    # Commande pour fermer un ticket
    @commands.command(name="closeticket", aliases=["fermer"])
    async def close_ticket_command(self, ctx: commands.Context, *, reason: str = "Aucune raison fournie"):
        """Ferme le ticket actuel (utilisable dans un salon ticket)."""
        channel = ctx.channel; guild = ctx.guild; user = ctx.author

        # Vérifier si c'est un salon ticket
        if not channel.name.startswith("ticket-"):
             try: await ctx.message.delete()
             except: pass
             return await ctx.send("Commande utilisable uniquement dans un salon ticket.", delete_after=15)

        # Vérifier permissions (Créateur ou Staff)
        creator_id = None
        if channel.topic and "CréateurID:" in channel.topic:
            match = re.search(r'CréateurID:(\d+)', channel.topic)
            if match:
                try: creator_id = int(match.group(1))
                except ValueError: pass

        # Fallback sur le dictionnaire en mémoire si pas trouvé dans le topic
        if not creator_id:
             for uid, cid in self.open_tickets.items(): # Utilise self.open_tickets (qui est open_tickets_state)
                 if cid == channel.id: creator_id = uid; break

        if not creator_id:
             logger.warning(f"Impossible déterminer créateur ticket {channel.name} pour commande close.")
             # Autoriser uniquement le staff si créateur inconnu ?
             # Pour l'instant, on bloque si on ne peut pas vérifier

        staff_role_ids = self.bot.config.get('TICKET_STAFF_ROLE_IDS', [])
        is_staff = any(role.id in staff_role_ids for role in user.roles)
        # Si on n'a pas trouvé le créateur, seul le staff peut fermer
        is_creator = (user.id == creator_id) if creator_id else False

        if not is_staff and not is_creator:
            try: await ctx.message.delete()
            except: pass
            # Donner un message plus clair si créateur non trouvé
            msg = "Seul le créateur original ou un membre du staff peut fermer ce ticket."
            if not creator_id: msg = "Impossible de vérifier le créateur; seul le staff peut fermer ce ticket."
            return await ctx.send(msg, delete_after=15)

        # Fermeture
        try:
            # Envoyer confirmation dans le salon avant de supprimer
            await ctx.send(f"🔒 Ticket fermé par {user.mention}. Suppression dans 10 secondes...\nRaison: {reason}")
            logger.info(f"Fermeture ticket {channel.name} par {user.name} (commande). Raison: {reason}")
            await asyncio.sleep(10)
            await channel.delete(reason=f"Ticket fermé par {str(user)} (cmd). Raison: {reason}")
            logger.info(f"Salon ticket {channel.name} ({channel.id}) supprimé.")

            # Nettoyer état mémoire
            if creator_id and creator_id in self.open_tickets and self.open_tickets[creator_id] == channel.id:
                 del self.open_tickets[creator_id] # Utilise self.open_tickets
                 logger.info(f"Ticket {channel.id} retiré état mémoire pour {creator_id}.")

            # Log optionnel...
            log_channel_id = self.bot.config.get('TICKET_LOG_CHANNEL_ID')
            if log_channel_id:
                log_channel = guild.get_channel(log_channel_id)
                if log_channel and isinstance(log_channel, discord.TextChannel):
                     log_embed = discord.Embed(
                        title="🔒 Ticket Fermé (Commande)",
                        description=f"Ticket `{channel.name}` (créé par <@{creator_id or 'Inconnu'}>) fermé par {user.mention}.",
                        color=discord.Color.red(), timestamp=utils.utcnow()
                     )
                     log_embed.add_field(name="Raison", value=reason, inline=False)
                     try: await log_channel.send(embed=log_embed)
                     except Exception as e_log: logger.error(f"Erreur log fermeture ticket: {e_log}")

        except discord.Forbidden: await ctx.send("Permissions manquantes pour supprimer salon.")
        except discord.NotFound: logger.warning(f"Tentative de fermeture d'un ticket déjà supprimé (commande): {channel.name}")
        except Exception as e: logger.error(f"Erreur fermeture ticket {channel.name} (cmd): {e}", exc_info=True); await ctx.send("Erreur interne fermeture.")


# Fonction setup (inchangée)
async def setup(bot: commands.Bot):
    required_ids = ['GUILD_ID', 'TICKET_CREATION_CHANNEL_ID', 'TICKET_CATEGORY_ID', 'ADMIN_ROLE_ID']
    optional_ids = ['TICKET_LOG_CHANNEL_ID', 'TICKET_STAFF_ROLE_IDS'] # Staff roles peut être vide
    missing = [k for k in required_ids if not bot.config.get(k)]
    if missing: logger.error(f"Config manquante TicketSystemCog: {', '.join(missing)}. Le Cog risque de mal fonctionner.")
    # else: logger.info("Config TicketSystemCog OK.")
    await bot.add_cog(TicketSystemCog(bot))
    logger.info("Cog TicketSystem chargé.")
    # L'enregistrement de TicketCreationView se fait via main.py/on_ready