# cogs/registration.py
import discord
from discord.ext import commands
from discord import ui
import logging
import json
import os
import asyncio

logger = logging.getLogger(__name__)

PLAYER_DATA_FILE = 'data/player_data.json'

# --- Définition des listes d'options ---
POSITIONS = [
    discord.SelectOption(label="Gardien (GK)", value="GK"),
    discord.SelectOption(label="Défenseur Central (DC)", value="DC"),
    discord.SelectOption(label="Défenseur Central (DCG)", value="DCG"),
    discord.SelectOption(label="Défenseur Central (DCD)", value="DCD"),
    discord.SelectOption(label="Défenseur Latéral (DD)", value="DD"),
    discord.SelectOption(label="Défenseur Latéral (DG)", value="DG"),
    discord.SelectOption(label="Milieu de terrain défensif (MDC)", value="MDC"),
    discord.SelectOption(label="Milieu de terrain défensif (MDD)", value="MDD"),
    discord.SelectOption(label="Milieu de terrain défensif (MDG)", value="MDG"),
    discord.SelectOption(label="Milieu de terrain piston (MD)", value="MD"),
    discord.SelectOption(label="Milieu de terrain piston (MG)", value="MG"),
    discord.SelectOption(label="Milieu de terrain offensif (MOC)", value="MOC"),
    discord.SelectOption(label="Attaquant ailié  (AG)", value="AG"),
    discord.SelectOption(label="Attaquant ailié  (AD)", value="AD"),
    discord.SelectOption(label="Attaquant  (ATG)", value="ATG"),
    discord.SelectOption(label="Attaquant  (ATD)", value="ATD"),
    discord.SelectOption(label="Buteur (BU)", value="BU")
]
POSITIONS_SECONDAIRE = [discord.SelectOption(label="Aucun", value="Aucun")] + POSITIONS

DAYS = [
    discord.SelectOption(label="Lundi", value="Lundi", emoji="🇱"),
    discord.SelectOption(label="Mardi", value="Mardi", emoji="🇲"),
    discord.SelectOption(label="Mercredi", value="Mercredi", emoji="🇼"),
    discord.SelectOption(label="Jeudi", value="Jeudi", emoji="🇹")
]

COMPETITIONS = [
    discord.SelectOption(label="VPG France", value="VPGF"),
    discord.SelectOption(label="VPG Belgique", value="VPGB"),
    discord.SelectOption(label="VPG Europe", value="VPGE"),
    discord.SelectOption(label="VPG Suisse", value="VPGS"),
    discord.SelectOption(label="SMG Santa France", value="SMGF"),
    discord.SelectOption(label="SMG Santa Belgique", value="SMGB"),
    discord.SelectOption(label="SMG Santa Monaco", value="SMGM"),
    discord.SelectOption(label="ePRO LEAGUE", value="EPL"),
    discord.SelectOption(label="VFT", value="VFT"),
    discord.SelectOption(label="IFC", value="IFC"),
    discord.SelectOption(label="FVPA", value="FVPA"),
    
    discord.SelectOption(label="Aucune Compétition Jouée", value="Aucune")
]


# --- Classe pour la Vue du Bouton d'Enregistrement ---
class RegistrationView(ui.View):
    """Vue persistante contenant le bouton pour démarrer l'enregistrement."""
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label="Créer mon joueur", style=discord.ButtonStyle.success, custom_id="persistent_register_button")
    async def register_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        """Callback exécuté quand le bouton 'Créer mon joueur' est cliqué."""
        logger.info(f"Bouton 'Créer mon joueur' cliqué par {interaction.user.name} ({interaction.user.id})")
        registration_cog = self.bot.get_cog('RegistrationCog')
        if not registration_cog:
            logger.error("Impossible de récupérer le RegistrationCog dans la vue.")
            await interaction.response.send_message("Une erreur interne s'est produite (Cog non trouvé). Contactez un admin.", ephemeral=True)
            return

        author = interaction.user
        guild = interaction.guild
        if not guild:
             await interaction.response.send_message("Erreur: Guilde non trouvée.", ephemeral=True)
             return

        # Vérifications (déjà enregistré, rôle)
        # Assurez-vous que ces clés existent bien dans bot.config (chargées depuis .env)
        verified_role_id = self.bot.config.get('VERIFIED_PLAYER_ROLE_ID')
        if not verified_role_id:
             logger.error("VERIFIED_PLAYER_ROLE_ID non trouvé dans la configuration du bot.")
             await interaction.response.send_message("Erreur de configuration interne (Rôle Vérifié).", ephemeral=True)
             return

        if str(author.id) in registration_cog.player_data:
            await interaction.response.send_message("Vous êtes déjà enregistré.", ephemeral=True)
            logger.warning(f"{author.name} a cliqué sur register mais est déjà enregistré.")
            return

        verified_role = guild.get_role(verified_role_id)
        if not verified_role or verified_role not in author.roles:
             await interaction.response.send_message("Vous n'avez pas (ou plus) le rôle requis pour vous enregistrer.", ephemeral=True)
             logger.warning(f"{author.name} a cliqué sur register sans le rôle requis.")
             return

        # Lancer le processus
        await interaction.response.send_message("Préparation du formulaire d'enregistrement...", ephemeral=True)
        # Utilise followup car la réponse initiale doit être rapide (moins de 3s)
        await interaction.followup.send(f"Ok {author.mention}, nous allons commencer ici.", ephemeral=True)
        # Passe l'interaction originale pour pouvoir récupérer user, guild, channel etc.
        await registration_cog._start_registration_flow(interaction)


# --- Classe Cog Principale ---
class RegistrationCog(commands.Cog):
    """Cog gérant le flux d'enregistrement et les données joueurs."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.player_data = self.load_player_data()

    def load_player_data(self) -> dict:
        """Charge les données des joueurs depuis le fichier JSON."""
        # ... (code inchangé) ...
        if os.path.exists(PLAYER_DATA_FILE):
            try:
                with open(PLAYER_DATA_FILE, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if not content: return {}
                    return json.loads(content)
            except json.JSONDecodeError:
                logger.error(f"Erreur décodage JSON: {PLAYER_DATA_FILE}")
                return {}
            except Exception as e:
                 logger.error(f"Erreur chargement {PLAYER_DATA_FILE}: {e}", exc_info=True)
                 return {}
        return {}

    def save_player_data(self):
        """Sauvegarde les données actuelles des joueurs dans le fichier JSON."""
        # ... (code inchangé) ...
        try:
            with open(PLAYER_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.player_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur sauvegarde {PLAYER_DATA_FILE}: {e}", exc_info=True)


    # --- Fonctions Helper pour poser les questions ---

    async def _ask_question_text(self, target_channel: discord.TextChannel, author: discord.User, question: str, timeout: float = 300.0) -> str | None:
        """Pose une question texte et attend une réponse message."""
        # ... (code inchangé - avec suppression de la réponse) ...
        if not isinstance(target_channel, discord.TextChannel): return None
        message_q = await target_channel.send(f"{author.mention}, {question}")
        try:
            def check(message):
                return message.author.id == author.id and message.channel.id == target_channel.id
            response_msg = await self.bot.wait_for('message', check=check, timeout=timeout)
            response_content = response_msg.content
            try: await response_msg.delete(delay=1)
            except Exception: pass
            return response_content
        except asyncio.TimeoutError:
            await target_channel.send(f"{author.mention}, temps écoulé ! Annulation.", delete_after=30)
            try: await message_q.delete(delay=30)
            except Exception: pass
            return None
        except Exception as e:
            logger.error(f"Erreur dans _ask_question_text pour {author.name}: {e}")
            await target_channel.send(f"{author.mention}, erreur. Annulation.", delete_after=30)
            try: await message_q.delete(delay=30)
            except Exception: pass
            return None

    async def _ask_question_select(self, target_channel: discord.TextChannel, author: discord.User, question: str, options: list[discord.SelectOption], base_custom_id: str, min_val: int = 1, max_val: int = 1, timeout: float = 300.0) -> list[str] | None:
        """Pose une question avec un menu déroulant."""
        # ... (code inchangé - avec callback interne et edit_message) ...
        if not isinstance(target_channel, discord.TextChannel): return None
        unique_custom_id = f"{base_custom_id}_{author.id}_{discord.utils.utcnow().timestamp()}"
        select = ui.Select(placeholder="Faites votre choix...", options=options, custom_id=unique_custom_id, min_values=min_val, max_values=max_val)
        view = ui.View(timeout=timeout)
        view.add_item(select)
        result = None

        async def select_callback(interaction: discord.Interaction):
            nonlocal result
            if interaction.user.id != author.id:
                await interaction.response.send_message("Ce n'est pas votre menu !", ephemeral=True)
                return
            if interaction.data.get('custom_id') != unique_custom_id:
                await interaction.response.send_message("Menu expiré ou invalide.", ephemeral=True)
                return

            result = interaction.data.get('values', [])
            view.stop()
            selected_labels = [opt.label for opt in options if opt.value in result]
            await interaction.response.edit_message(content=f"{author.mention} : {question}\n*Votre choix : {', '.join(selected_labels)}*", view=None)

        select.callback = select_callback
        message = await target_channel.send(f"{author.mention}, {question}", view=view)
        timed_out = await view.wait()

        if timed_out:
            await target_channel.send(f"{author.mention}, temps écoulé ! Annulation.", delete_after=30)
            try: await message.edit(content=f"{author.mention} : {question}\n*(Temps écoulé)*", view=None)
            except Exception: pass
            return None
        return result


    # --- Méthode principale du flux (avec modification pour retrait de rôle) ---

    async def _start_registration_flow(self, interaction_origin: discord.Interaction):
        """Gère la conversation publique, la sauvegarde, l'ajout/retrait de rôles et la présentation."""
        author = interaction_origin.user
        guild = interaction_origin.guild
        target_channel = interaction_origin.channel

        if not isinstance(target_channel, discord.TextChannel):
             logger.error(f"Canal d'interaction invalide pour {author.name}: {target_channel}")
             await interaction_origin.followup.send("Impossible de démarrer l'enregistrement dans ce type de salon.", ephemeral=True)
             return

        responses = {}
        logger.info(f"Début flux enregistrement public pour {author.name} dans #{target_channel.name}")
        start_message = None

        try:
            start_message = await target_channel.send(f"--- Début de l'enregistrement pour {author.mention} (Répondez aux questions suivantes) ---")
            session_id_prefix = f"reg_{author.id}" # Simplifié, timestamp pas forcément utile si on gère bien les vues

            # --- Poser les questions ---
            responses['nom_joueur'] = await self._ask_question_text(target_channel, author, "Quel est votre nom de joueur principal (GT/PSN/EA ID) ?")
            if responses['nom_joueur'] is None: raise asyncio.CancelledError("Timeout/Erreur Nom Joueur")

            poste_principal_result = await self._ask_question_select(target_channel, author, "Poste principal ?", POSITIONS, f"{session_id_prefix}_poste1", max_val=1)
            if poste_principal_result is None: raise asyncio.CancelledError("Timeout/Erreur Poste Principal")
            responses['poste_principal'] = poste_principal_result[0]

            poste_secondaire_result = await self._ask_question_select(target_channel, author, "Poste secondaire ?", POSITIONS_SECONDAIRE, f"{session_id_prefix}_poste2", max_val=1)
            if poste_secondaire_result is None: raise asyncio.CancelledError("Timeout/Erreur Poste Secondaire")
            responses['poste_secondaire'] = poste_secondaire_result[0]

            dispo_result = await self._ask_question_select(target_channel, author, "Disponibilités en soirée ? (Plusieurs choix possibles)", DAYS, f"{session_id_prefix}_dispo", max_val=len(DAYS))
            if dispo_result is None: raise asyncio.CancelledError("Timeout/Erreur Disponibilités")
            responses['disponibilites'] = ", ".join(dispo_result)

            responses['ancien_club'] = await self._ask_question_text(target_channel, author, "Dernier club Pro ? (Ou 'Aucun')")
            if responses['ancien_club'] is None: raise asyncio.CancelledError("Timeout/Erreur Ancien Club")

            compets_result = await self._ask_question_select(target_channel, author, "Compétitions jouées ? (Plusieurs choix possibles)", COMPETITIONS, f"{session_id_prefix}_compets", max_val=len(COMPETITIONS))
            if compets_result is None: raise asyncio.CancelledError("Timeout/Erreur Compétitions")
            responses['competitions_jouees'] = ", ".join(compets_result)

            responses['experience'] = await self._ask_question_text(target_channel, author, "Décrivez votre expérience Club Pro (Divisions, style jeu, années...) :")
            if responses['experience'] is None: raise asyncio.CancelledError("Timeout/Erreur Expérience")

            if start_message:
                try: await start_message.delete()
                except Exception: pass

        except asyncio.CancelledError as user_cancel:
            logger.info(f"Enregistrement annulé pour {author.name}: {user_cancel}")
            if start_message:
                try: await start_message.delete(delay=10)
                except Exception: pass
            # Envoyer un message d'annulation à l'utilisateur
            await target_channel.send(f"Enregistrement annulé, {author.mention}.", delete_after=30)
            return
        except Exception as e:
            logger.error(f"Erreur majeure pendant le flux d'enregistrement pour {author.name}: {e}", exc_info=True)
            await target_channel.send(f"{author.mention}, une erreur critique est survenue. Contactez un admin.")
            if start_message:
                try: await start_message.delete()
                except Exception: pass
            return

        # --- Finalisation et Actions Post-Enregistrement ---
        responses['discord_id'] = author.id
        responses['discord_name'] = str(author)
        responses['discord_display_name'] = author.display_name
        responses['avatar_url'] = str(author.avatar.url) if author.avatar else None

        self.player_data[str(author.id)] = responses
        self.save_player_data()
        logger.info(f"Joueur enregistré (public) : {author.name} ({author.id}) - Données sauvegardées.")

        # --- Création Embed Présentation ---
        # ... (code de l'embed inchangé) ...
        presentation_embed = discord.Embed(
            title=f"✨ Présentation : {author.display_name} ✨",
            description=f"{author.mention} a terminé son enregistrement !",
            color=discord.Color.from_rgb(0, 153, 255)
        )
        if responses['avatar_url']:
            presentation_embed.set_thumbnail(url=responses['avatar_url'])
        presentation_embed.add_field(name="Nom Joueur", value=responses.get('nom_joueur', 'N/A'), inline=False)
        presentation_embed.add_field(name="Poste Principal", value=responses.get('poste_principal', 'N/A'), inline=True)
        presentation_embed.add_field(name="Poste Secondaire", value=responses.get('poste_secondaire', 'N/A'), inline=True)
        presentation_embed.add_field(name="Disponibilités", value=responses.get('disponibilites', 'N/A'), inline=False)
        presentation_embed.add_field(name="Ancien Club", value=responses.get('ancien_club', 'N/A'), inline=True)
        presentation_embed.add_field(name="Compétitions Jouées", value=responses.get('competitions_jouees', 'N/A'), inline=False)
        presentation_embed.add_field(name="Expérience Détail", value=responses.get('experience', 'N/A'), inline=False)
        presentation_embed.set_footer(text=f"ID: {author.id}")
        presentation_embed.timestamp = discord.utils.utcnow()


        # --- Envoi dans #présentations ---
        presentation_channel_sent = False
        presentation_channel_id = self.bot.config.get('PRESENTATION_CHANNEL_ID')
        if presentation_channel_id:
            presentation_channel = guild.get_channel(presentation_channel_id)
            if presentation_channel and isinstance(presentation_channel, discord.TextChannel):
                try:
                    await presentation_channel.send(embed=presentation_embed)
                    presentation_channel_sent = True
                    logger.info(f"Embed présentation pour {author.name} envoyé dans #{presentation_channel.name}")
                except Exception as e: logger.error(f"Erreur envoi embed présentation: {e}")
            else: logger.error(f"Salon présentation ({presentation_channel_id}) introuvable/invalide.")
        else: logger.warning("PRESENTATION_CHANNEL_ID non configuré.")


        # !!! DEBUT DE LA MODIFICATION : GESTION DES ROLES !!!
        test_role_assigned = False
        verified_role_removed = False
        test_role_name = "Non défini (Test)"
        verified_role_name = "Non défini (Vérifié)"

        test_role_id = self.bot.config.get('JOUEUR_TEST_ROLE_ID')
        verified_role_id = self.bot.config.get('VERIFIED_PLAYER_ROLE_ID') # ID du rôle à retirer

        # Récupérer les objets Rôle
        test_role = guild.get_role(test_role_id) if test_role_id else None
        verified_role = guild.get_role(verified_role_id) if verified_role_id else None

        if not test_role:
            logger.error(f"Rôle Joueur Test ({test_role_id}) introuvable ou non configuré.")
        if not verified_role:
             logger.error(f"Rôle Joueur Vérifié ({verified_role_id}) introuvable ou non configuré (nécessaire pour le retrait).")

        # Procéder seulement si les deux rôles sont trouvés
        if test_role and verified_role:
            test_role_name = test_role.name
            verified_role_name = verified_role.name

            # Vérifier la hiérarchie pour les deux rôles
            if guild.me.top_role > test_role and guild.me.top_role > verified_role:
                # Essayer d'abord d'ajouter le nouveau rôle
                try:
                    await author.add_roles(test_role, reason="Enregistrement terminé")
                    test_role_assigned = True
                    logger.info(f"Rôle '{test_role.name}' ajouté à {author.name}")

                    # Si l'ajout réussit, essayer de retirer l'ancien rôle
                    try:
                        await author.remove_roles(verified_role, reason=f"Remplacé par '{test_role.name}'")
                        verified_role_removed = True
                        logger.info(f"Rôle '{verified_role.name}' retiré de {author.name}")
                    except Exception as e_rem:
                        logger.error(f"Erreur retrait rôle '{verified_role.name}' pour {author.name}: {e_rem}")

                except discord.Forbidden:
                    logger.error(f"Permissions manquantes pour ajouter/retirer des rôles à {author.name}.")
                except discord.HTTPException as e_http:
                    logger.error(f"Erreur HTTP gestion rôles pour {author.name}: {e_http}")
                except Exception as e_roles:
                    logger.error(f"Erreur inattendue gestion rôles pour {author.name}: {e_roles}", exc_info=True)
            else:
                logger.error(f"Hiérarchie insuffisante pour gérer '{test_role.name}' et/ou '{verified_role.name}'")
        else:
             logger.error("Un ou plusieurs rôles (Test ou Vérifié) n'ont pas pu être récupérés.")
        # !!! FIN DE LA MODIFICATION : GESTION DES ROLES !!!


        # --- Message de confirmation final (adapté) ---
        final_confirm_msg_text = f"✅ Enregistrement terminé, {author.mention} !"
        if presentation_channel_sent: final_confirm_msg_text += " Votre présentation a été postée."
        else: final_confirm_msg_text += " (Erreur publication présentation)."

        if test_role_assigned:
            final_confirm_msg_text += f" Le rôle '{test_role_name}' attribué."
            if verified_role_removed:
                 final_confirm_msg_text += f" Rôle '{verified_role_name}' retiré."
            else:
                 final_confirm_msg_text += f" (Erreur retrait rôle '{verified_role_name}')." # Message si retrait échoue
        else:
            final_confirm_msg_text += f" (Erreur attribution rôle '{test_role_name}')." # Message si ajout échoue

        final_msg_confirm = None
        try:
            final_msg_confirm = await target_channel.send(final_confirm_msg_text)
        except Exception as e:
             logger.error(f"Impossible d'envoyer confirmation finale dans {target_channel.name}: {e}")

        # --- Nettoyage du salon ---
        logger.info(f"Tentative nettoyage {target_channel.name} pour {author.name}")
        await asyncio.sleep(10)

        def always_true_check(message): return True # Défini ici pour être sûr

        try:
            if final_msg_confirm:
                try: await final_msg_confirm.delete()
                except Exception: pass

            deleted_messages = await target_channel.purge(limit=200, check=always_true_check, bulk=True)
            logger.info(f"{len(deleted_messages)} messages purgés dans {target_channel.name}.")
            await target_channel.send("Nettoyage automatique terminé.", delete_after=10)
        except discord.Forbidden:
            logger.error(f"Permissions manquantes ('Gérer les messages') pour purger {target_channel.name}")
            await target_channel.send(f"Je n'ai pas la permission de nettoyer ce salon.", delete_after=30)
        except Exception as e:
             logger.error(f"Erreur purge salon {target_channel.name}: {e}", exc_info=True)

    # --- Fin de la méthode _start_registration_flow ---


# --- Fonction Setup ---
async def setup(bot: commands.Bot):
    # Créer data/ et player_data.json si besoin
    if not os.path.exists(PLAYER_DATA_FILE):
        logger.warning(f"{PLAYER_DATA_FILE} non trouvé. Création.")
        try:
            os.makedirs(os.path.dirname(PLAYER_DATA_FILE), exist_ok=True)
            with open(PLAYER_DATA_FILE, 'w', encoding='utf-8') as f: json.dump({}, f)
        except Exception as e: logger.error(f"Impossible de créer {PLAYER_DATA_FILE}: {e}")

    # Charger le Cog (La vue est enregistrée dans main.py/on_ready maintenant)
    await bot.add_cog(RegistrationCog(bot))
    logger.info("Cog Registration chargé.")
    # Note: L'enregistrement de la vue persistante est déplacé dans main.py pour plus de sûreté