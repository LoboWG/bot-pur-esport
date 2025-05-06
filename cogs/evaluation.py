# cogs/evaluation.py
import discord
from discord.ext import commands
from discord import ui, utils
import logging
import asyncio
import re
import os

logger = logging.getLogger(__name__)

# Fonction utilitaire
def sanitize_channel_name(name):
    name = name.lower()
    name = re.sub(r'[^\w-]', '', name)
    name = re.sub(r'[-_]+', '-', name)
    return name[:90]

open_eval_channels = {}

# --- Vue Persistante pour les boutons de décision ---
class EvaluationActionView(ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot
        self._processing_lock = asyncio.Lock()

    async def handle_decision(self, interaction: discord.Interaction, approved: bool):
        async with self._processing_lock:
            user_who_clicked = interaction.user; channel = interaction.channel; guild = interaction.guild
            if not isinstance(channel, discord.TextChannel) or not guild:
                try: await interaction.response.send_message("Erreur interne.", ephemeral=True)
                except: pass # Ignore if interaction already responded
                return

            evaluated_member_id = None
            if channel.topic and "EvaluateID:" in channel.topic:
                match = re.search(r'EvaluateID:(\d+)', channel.topic)
                if match:
                    try: evaluated_member_id = int(match.group(1))
                    except ValueError: pass

            if not evaluated_member_id:
                logger.error(f"Impossible trouver EvaluateID topic {channel.name}")
                try: await interaction.response.send_message("Erreur: Joueur non identifiable.", ephemeral=True)
                except: pass
                return

            evaluated_member = None
            try: evaluated_member = await guild.fetch_member(evaluated_member_id)
            except discord.NotFound: logger.warning(f"Membre éval ({evaluated_member_id}) introuvable (fetch).")
            except discord.HTTPException: evaluated_member = guild.get_member(evaluated_member_id); logger.warning(f"Erreur HTTP fetch {evaluated_member_id}, fallback cache.")

            # Vérifier permissions cliqueur
            staff_ids_key = 'EVALUATION_STAFF_ROLE_IDS' if 'EVALUATION_STAFF_ROLE_IDS' in self.bot.config else 'TICKET_STAFF_ROLE_IDS'
            staff_role_ids = self.bot.config.get(staff_ids_key, [])
            admin_role_id = self.bot.config.get('ADMIN_ROLE_ID')
            is_staff = any(role.id in staff_role_ids for role in getattr(user_who_clicked, 'roles', []))
            is_admin_role = any(role.id == admin_role_id for role in getattr(user_who_clicked, 'roles', [])) if admin_role_id else False
            has_admin_perm = user_who_clicked.guild_permissions.administrator
            if not is_staff and not is_admin_role and not has_admin_perm:
                 try: await interaction.response.send_message("Seul un admin ou staff peut décider.", ephemeral=True)
                 except: pass
                 return

            # Désactiver boutons
            try:
                disabled_view = ui.View(timeout=None)
                disabled_view.add_item(ui.Button(label="Test approuvé", style=discord.ButtonStyle.success, emoji="✅", disabled=True, custom_id="eval_approve_disabled"))
                disabled_view.add_item(ui.Button(label="Test raté", style=discord.ButtonStyle.danger, emoji="❌", disabled=True, custom_id="eval_reject_disabled"))
                if not interaction.response.is_done(): await interaction.response.edit_message(content=interaction.message.content, embed=interaction.message.embeds[0], view=None)
                else: await interaction.edit_original_response(content=interaction.message.content, embed=interaction.message.embeds[0], view=None)
                logger.info(f"Vue désactivée dans {channel.name} par {user_who_clicked.name}")
            except Exception as e_edit:
                 logger.warning(f"Impossible éditer message {channel.name}: {e_edit}")
                 if not interaction.response.is_done(): await interaction.response.defer() # Defer si edit échoue

            # Actions spécifiques
            action_successful = False
            if approved:
                action_successful = await self.approve_member(interaction, evaluated_member)
            else:
                action_successful = await self.reject_member(interaction, evaluated_member)

            # Nettoyage final
            if action_successful or evaluated_member is None:
                logger.info(f"Nettoyage de {channel.name} dans 15s.")
                await interaction.followup.send("Fin de l'évaluation. Ce salon sera supprimé dans 15 secondes.", ephemeral=False)
                await asyncio.sleep(15)
                try:
                    await channel.delete(reason=f"Évaluation terminée par {str(user_who_clicked)}")
                    logger.info(f"Salon évaluation {channel.name} supprimé.")
                    if evaluated_member_id in open_eval_channels and open_eval_channels[evaluated_member_id] == channel.id:
                        try: del open_eval_channels[evaluated_member_id]
                        except KeyError: pass
                        logger.info(f"Salon évaluation {channel.id} retiré état mémoire pour {evaluated_member_id}.")
                except Exception as e_del: logger.error(f"Erreur suppression salon éval {channel.name}: {e_del}", exc_info=True)
            else:
                logger.warning(f"Nettoyage de {channel.name} annulé car action principale échouée.")
                await interaction.followup.send("L'action principale ayant échoué, le salon ne sera pas supprimé automatiquement.", ephemeral=True)


    async def approve_member(self, interaction: discord.Interaction, member: discord.Member | None) -> bool:
        """Logique d'approbation. Retourne True si succès."""
        guild = interaction.guild
        joueur_club_role_id = self.bot.config.get('JOUEUR_CLUB_ROLE_ID')
        joueur_test_role_id = self.bot.config.get('JOUEUR_TEST_ROLE_ID')
        result_message = f"✅ **Test approuvé** par {interaction.user.mention}."

        if not joueur_club_role_id or not joueur_test_role_id:
             logger.error("Config rôles Club/Test manquante."); await interaction.followup.send("Erreur config rôles.", ephemeral=True); return False
        joueur_club_role = guild.get_role(joueur_club_role_id); joueur_test_role = guild.get_role(joueur_test_role_id)
        if not joueur_club_role or not joueur_test_role:
             logger.error(f"Rôle Club ou Test introuvable."); await interaction.followup.send("Erreur: Rôle requis introuvable.", ephemeral=True); return False
        if guild.me.top_role <= joueur_club_role or guild.me.top_role <= joueur_test_role:
             logger.error(f"Hiérarchie insuffisante."); await interaction.followup.send("Erreur: Hiérarchie rôle insuffisante.", ephemeral=True); return False

        if not member:
            topic_id_str = interaction.channel.topic.split('EvaluateID:')[1].split(')')[0] if interaction.channel and interaction.channel.topic and 'EvaluateID:' in interaction.channel.topic else 'Inconnu'
            await interaction.followup.send(result_message + f"\nMembre introuvable (ID: {topic_id_str}).", ephemeral=False); return True

        role_change_success = False
        try:
            await member.edit(roles=[role for role in member.roles if role != joueur_test_role] + [joueur_club_role], reason=f"Test approuvé par {str(interaction.user)}")
            logger.info(f"Rôles MAJ {member.name}: +{joueur_club_role.name}, -{joueur_test_role.name}")
            result_message += f"\n{member.mention} a reçu le rôle {joueur_club_role.mention} (rôle {joueur_test_role.mention} retiré)."
            role_change_success = True
        except Exception as e_roles: logger.error(f"Erreur rôles {member.name}: {e_roles}", exc_info=True); result_message += "\nErreur gestion rôles."

        await interaction.followup.send(result_message, ephemeral=False)
        return role_change_success


    async def reject_member(self, interaction: discord.Interaction, member: discord.Member | None) -> bool:
        """Logique de refus. Retourne True si succès."""
        guild = interaction.guild
        reason_kick = f"Test non concluant (décision par {str(interaction.user)})"
        result_message = f"❌ **Test non concluant** (décision de {interaction.user.mention})."
        kick_success = False

        if not member:
             topic_id_str = interaction.channel.topic.split('EvaluateID:')[1].split(')')[0] if interaction.channel and interaction.channel.topic and 'EvaluateID:' in interaction.channel.topic else 'Inconnu'
             await interaction.followup.send(result_message + f"\nMembre introuvable (ID: {topic_id_str}).", ephemeral=False); return True

        # --- CORRECTION SYNTAXE Ligne ~140 ---
        dm_sent = False
        try:
            await member.send(f"Bonjour {member.display_name}, suite à votre test avec l'équipe {guild.name}, nous ne donnons malhereusement pas une suite favorable. Nous vous souhaintons une bonne recherche de club merci. Et au plaisirs sur le carré vert 🏟️")
            dm_sent = True
        except Exception:
             logger.warning(f"Impossible envoyer MP expulsion à {member.name}")
        # --- FIN CORRECTION SYNTAXE ---

        try:
            if guild.me.top_role > member.top_role:
                await member.kick(reason=reason_kick)
                logger.info(f"Membre {member.name} expulsé (test raté).")
                result_message += f"\n{member.display_name} a été **expulsé** du serveur." + ("" if dm_sent else " (MP non envoyé.)")
                kick_success = True
            else: logger.error(f"Impossible expulser {member.name}: Hiérarchie."); result_message += f"\nImpossible d'expulser (hiérarchie)."
        except discord.Forbidden: logger.error(f"Permissions manquantes ('Expulser') pour {member.name}."); result_message += f"\nErreur: Permissions manquantes."
        except Exception as e_kick: logger.error(f"Erreur expulsion {member.name}: {e_kick}", exc_info=True); result_message += f"\nErreur interne expulsion."

        await interaction.followup.send(result_message, ephemeral=False)
        return kick_success


    @ui.button(label="Test approuvé", style=discord.ButtonStyle.success, custom_id="eval_approve", emoji="✅")
    async def approve_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        await self.handle_decision(interaction, approved=True)

    @ui.button(label="Test raté", style=discord.ButtonStyle.danger, custom_id="eval_reject", emoji="❌")
    async def reject_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        await self.handle_decision(interaction, approved=False)


# --- Classe Cog Evaluation ---
class EvaluationCog(commands.Cog, name="EvaluationCog"):
    """Cog pour gérer l'évaluation des joueurs en test."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.open_eval_channels = open_eval_channels

    @commands.command(name="testresultat", aliases=["eval"])
    # Permission Check (Utilise les rôles staff ET admin)
    @commands.has_any_role(int(os.getenv('ADMIN_ROLE_ID') or 0), *(int(rid) for rid in (os.getenv('EVALUATION_STAFF_ROLE_IDS') or os.getenv('TICKET_STAFF_ROLE_IDS') or '').split(',') if rid.isdigit()))
    async def test_resultat(self, ctx: commands.Context, member: discord.Member):
        """Crée un salon d'évaluation pour un joueur en test."""
        # ... (Code de la commande comme précédemment) ...
        author = ctx.author; guild = ctx.guild
        joueur_test_role_id = self.bot.config.get('JOUEUR_TEST_ROLE_ID');
        if not joueur_test_role_id: return await ctx.send("Erreur config: Rôle Joueur Test.", ephemeral=True)
        joueur_test_role = guild.get_role(joueur_test_role_id)
        if not joueur_test_role: return await ctx.send(f"Erreur config: Rôle Joueur Test introuvable.", ephemeral=True)
        if joueur_test_role not in member.roles: return await ctx.send(f"{member.mention} n'a pas rôle {joueur_test_role.mention}.", ephemeral=True)
        if member.id in self.open_eval_channels:
            existing_channel = guild.get_channel(self.open_eval_channels[member.id])
            if existing_channel: return await ctx.send(f"Salon éval déjà ouvert : {existing_channel.mention}", ephemeral=True)
            else: del self.open_eval_channels[member.id]
        category_id = self.bot.config.get('EVALUATION_CATEGORY_ID'); category = guild.get_channel(category_id) if category_id else None
        staff_ids_key = 'EVALUATION_STAFF_ROLE_IDS' if 'EVALUATION_STAFF_ROLE_IDS' in self.bot.config else 'TICKET_STAFF_ROLE_IDS'
        staff_role_ids = self.bot.config.get(staff_ids_key, [])
        staff_roles = [guild.get_role(rid) for rid in staff_role_ids if rid]; staff_roles = [r for r in staff_roles if r]
        admin_role_id = self.bot.config.get('ADMIN_ROLE_ID'); admin_role = guild.get_role(admin_role_id) if admin_role_id else None
        overwrites = { guild.default_role: discord.PermissionOverwrite(view_channel=False), member: discord.PermissionOverwrite(view_channel=True, send_messages=True), author: discord.PermissionOverwrite(view_channel=True, send_messages=True), guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, embed_links=True, manage_messages=True) }
        for role in staff_roles: overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)
        if admin_role and admin_role not in staff_roles: overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)
        channel_name = f"eval-{sanitize_channel_name(member.name)}-{str(member.id)[-4:]}"; new_channel = None
        try:
            topic = f"Évaluation de {str(member)} (ID: {member.id}). Lancé par {str(author)}. EvaluateID:{member.id}"
            new_channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites, topic=topic, reason=f"Éval par {str(author)} pour {str(member)}"); self.open_eval_channels[member.id] = new_channel.id; logger.info(f"Salon éval créé: {new_channel.name} pour {member.name}")
        except Exception as e: logger.error(f"Erreur création salon éval: {e}", exc_info=True); return await ctx.send("Erreur création salon.", ephemeral=True)
        if new_channel:
            try:
                eval_view = EvaluationActionView(bot=self.bot); embed = discord.Embed(title=f"📋 Évaluation de {member.display_name}", description=(f"Session par {author.mention} pour {member.mention}.\n\n**Décision Staff :**"), color=discord.Color.dark_purple())
                await new_channel.send(embed=embed, view=eval_view); await ctx.send(f"Salon éval créé : {new_channel.mention}", ephemeral=True)
            except Exception as e_msg: logger.error(f"Erreur envoi message/vue éval {new_channel.name}: {e_msg}")

# Fonction setup
async def setup(bot: commands.Bot):
    # ... (code setup comme précédemment) ...
    required_ids = ['GUILD_ID', 'ADMIN_ROLE_ID', 'JOUEUR_TEST_ROLE_ID', 'JOUEUR_CLUB_ROLE_ID']
    optional_ids = ['EVALUATION_CATEGORY_ID', 'TICKET_STAFF_ROLE_IDS', 'EVALUATION_STAFF_ROLE_IDS']
    missing = [k for k in required_ids if not bot.config.get(k)]
    staff_ids_key = 'EVALUATION_STAFF_ROLE_IDS' if bot.config.get('EVALUATION_STAFF_ROLE_IDS') else 'TICKET_STAFF_ROLE_IDS'
    if not bot.config.get(staff_ids_key): missing.append(f"{staff_ids_key} (ou TICKET_STAFF_ROLE_IDS)")
    if missing: logger.error(f"Config manquante EvaluationCog: {', '.join(missing)}.")
    await bot.add_cog(EvaluationCog(bot))
    logger.info("Cog Evaluation chargé.")