"""
Telegram bot command and message handlers.
"""

import asyncio
import re
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .config import APPLE_ID, APPLE_PASSWORD, log
from .rclone_utils import check_auth, run_backup
from .reauth import feed_2fa_code, poll_for_2fa_prompt, start_reauth_in_thread
from .scheduler import send_backup_result
from .state import state


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    auth_ok, _ = await check_auth()

    last_backup = state.data.get("last_backup", "Nie")
    if last_backup and last_backup != "Nie":
        try:
            dt = datetime.fromisoformat(last_backup)
            last_backup = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            pass

    text = (
        f"📷 <b>iCloud Photos Backup</b>\n\n"
        f"🔐 Auth Status: {'✅ OK' if auth_ok else '❌ Abgelaufen'}\n"
        f"📁 Letztes Backup: {last_backup}\n"
        f"📊 Letzte neue Dateien: {state.data.get('last_backup_files', '—')}\n\n"
        f"<b>Befehle:</b>\n"
        f"/status – Status anzeigen\n"
        f"/backup – Manuelles Backup starten\n"
        f"/reauth – Neu authentifizieren\n"
        f"/logs – Letzte Log-Eintraege"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    auth_ok, _ = await check_auth()

    last_backup = state.data.get("last_backup", "Nie")
    files = state.data.get("last_backup_files", 0)
    errors = state.data.get("last_backup_errors", 0)

    text = (
        f"🔐 <b>Auth:</b> {'✅ Gueltig' if auth_ok else '❌ Abgelaufen'}\n"
        f"📁 <b>Letztes Backup:</b> {last_backup}\n"
        f"📊 <b>Neue Dateien:</b> {files}\n"
        f"⚠️ <b>Fehler:</b> {errors}\n"
    )
    if not auth_ok:
        text += "\n⚠️ <i>Auth ist abgelaufen. /reauth zum erneuern.</i>"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /backup command."""
    msg = await update.message.reply_text("🔄 Backup wird gestartet...")

    auth_ok, _ = await check_auth()
    if not auth_ok:
        await msg.edit_text("❌ Authentifizierung ist abgelaufen. Bitte zuerst /reauth ausfuehren.")
        return

    files, summary = await run_backup()
    await msg.edit_text(summary, parse_mode=ParseMode.HTML)


async def cmd_reauth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reauth command."""
    if not APPLE_ID or not APPLE_PASSWORD:
        await update.message.reply_text("❌ APPLE_ID oder APPLE_PASSWORD sind nicht gesetzt.")
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Ja, neu authentifizieren", callback_data="reauth_yes"),
            InlineKeyboardButton("❌ Nein, spaeter", callback_data="reauth_no"),
        ]
    ])
    await update.message.reply_text(
        "⚠️ <b>iCloud Authentifizierung erneuern?</b>\n\n"
        "Du wirst nach deinem 2FA-Code gefragt.",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /logs command."""
    last_backup = state.data.get("last_backup", "Nie")
    files = state.data.get("last_backup_files", 0)
    errors = state.data.get("last_backup_errors", 0)

    text = (
        f"📋 <b>Letzte Backup-Logs</b>\n\n"
        f"📅 Zeit: {last_backup}\n"
        f"📁 Neue Dateien: {files}\n"
        f"❌ Fehler: {errors}\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks (re-auth yes/no)."""
    query = update.callback_query
    await query.answer()

    if query.data == "reauth_yes":
        await query.edit_message_text("🔄 Starte Re-Authentifizierung...")

        future = await start_reauth_in_thread()
        await poll_for_2fa_prompt(context.application, str(query.message.chat_id), future)

        try:
            success, error = await asyncio.wait_for(future, timeout=360)
        except asyncio.TimeoutError:
            success, error = False, "Timeout"

        if success:
            await query.message.reply_text("✅ Authentifizierung erfolgreich erneuert!")
            await send_backup_result(query.message.chat_id, context.application)
        else:
            await query.message.reply_text(
                f"❌ Authentifizierung fehlgeschlagen: {error}\nBitte /reauth erneut versuchen."
            )

    elif query.data == "reauth_no":
        await query.edit_message_text("👌 OK, ich erinnere dich spaeter wieder.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages – used for 2FA code input."""
    if not state.pending_2fa:
        await update.message.reply_text(
            "ℹ️ Sende /start fuer eine Uebersicht der verfuegbaren Befehle."
        )
        return

    text = update.message.text.strip()

    if text.lower() == "sms":
        code = "sms"
    elif re.match(r"^\d{6}$", text):
        code = text
    else:
        await update.message.reply_text(
            "⚠️ Bitte einen gueltigen 6-stelligen Code oder 'sms' senden."
        )
        return

    success, message = await feed_2fa_code(code)
    await update.message.reply_text(f"{'✅' if success else '❌'} {message}")
