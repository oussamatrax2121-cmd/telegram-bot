import logging
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_ID  = 123456789

VIP_CHANNELS = [
    {"name": "قناة VIP 1", "link": "https://t.me/your_vip_1"},
    {"name": "قناة VIP 2", "link": "https://t.me/your_vip_2"},
]

CHOOSE_SERVICE, WAITING_INFO, ADMIN_REPLY_TEXT = range(3)
tickets = {}
ticket_counter = [0]

logging.basicConfig(level=logging.INFO)

SERVICE_LABELS = {
    "app":       "📱 مفتاح تفعيل التطبيق",
    "indicator": "📊 مفتاح تفعيل المؤشرات",
    "admin":     "💬 تواصل مع الأدمن",
}

class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, format, *args):
        pass

def run_server():
    server = HTTPServer(("0.0.0.0", 8080), PingHandler)
    server.serve_forever()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📱 مفتاح تفعيل التطبيق",  callback_data="service_app")],
        [InlineKeyboardButton("📊 مفتاح تفعيل المؤشرات", callback_data="service_indicator")],
        [InlineKeyboardButton("📡 الدخول إلى قنوات VIP",  callback_data="service_vip")],
        [InlineKeyboardButton("💬 تواصل مع الأدمن",       callback_data="service_admin")],
    ]
    await update.message.reply_text(
        f"مرحباً {user.first_name} 👋\n\nاختر الخدمة التي تريدها:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_SERVICE

async def service_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.replace("service_", "")
    context.user_data["service"] = key

    if key == "vip":
        lines = ["✅ قنوات VIP الخاصة بنا:\n"]
        for ch in VIP_CHANNELS:
            lines.append(f"• {ch['name']}: {ch['link']}")
        lines.append("\nللاشتراك المدفوع تواصل مع الأدمن.")
        await query.edit_message_text("\n".join(lines))
        return ConversationHandler.END

    label = SERVICE_LABELS.get(key, "الخدمة")
    await query.edit_message_text(
        f"اخترت: {label}\n\n"
        "أرسل اسمك الكامل وأي تفاصيل تريد إيصالها للأدمن:"
    )
    return WAITING_INFO

async def receive_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    info  = update.message.text
    key   = context.user_data.get("service", "admin")
    label = SERVICE_LABELS.get(key, key)

    ticket_counter[0] += 1
    tid = ticket_counter[0]
    tickets[tid] = {
        "tid":      tid,
        "user_id":  user.id,
        "username": user.username or "—",
        "fname":    user.first_name,
        "service":  label,
        "info":     info,
        "status":   "🟡 جديد",
        "time":     datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    keyboard = [[
        InlineKeyboardButton("✉️ رد نصي",    callback_data=f"replytext_{tid}_{user.id}"),
        InlineKeyboardButton("📞 فتح محادثة", url=f"tg://user?id={user.id}"),
        InlineKeyboardButton("❌ رفض",        callback_data=f"reject_{tid}_{user.id}"),
    ]]
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"🔔 طلب جديد!\n"
            f"━━━━━━━━━━━━━━\n"
            f"🎫 تذكرة: #{tid}\n"
            f"👤 {user.first_name}  |  @{user.username or '—'}\n"
            f"🆔 ID: {user.id}\n"
            f"📦 {label}\n"
            f"🕐 {tickets[tid]['time']}\n"
            f"━━━━━━━━━━━━━━\n"
            f"{info}"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text(
        f"✅ تم إرسال طلبك!\n🎫 رقم تذكرتك: #{tid}\n\nسيتواصل معك الأدمن قريباً 🙏"
    )
    return ConversationHandler.END

async def admin_reply_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ ليس لديك صلاحية!", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    parts = query.data.split("_")
    context.user_data["reply_tid"] = int(parts[1])
    context.user_data["reply_cid"] = int(parts[2])
    await query.message.reply_text(
        f"✏️ اكتب ردّك على تذكرة #{parts[1]} وسأرسله للعميل:"
    )
    return ADMIN_REPLY_TEXT

async def admin_send_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    tid  = context.user_data.get("reply_tid")
    cid  = context.user_data.get("reply_cid")
    text = update.message.text
    await context.bot.send_message(
        chat_id=cid,
        text=f"📩 رد الأدمن على طلبك #{tid}:\n\n{text}"
    )
    if tid in tickets:
        tickets[tid]["status"] = "✅ تم الرد"
    await update.message.reply_text(f"✅ تم إرسال ردّك على تذكرة #{tid}")
    return ConversationHandler.END

async def admin_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ ليس لديك صلاحية!", show_alert=True)
        return
    await query.answer()
    parts = query.data.split("_")
    tid = int(parts[1])
    cid = int(parts[2])
    if tid in tickets:
        tickets[tid]["status"] = "❌ مرفوض"
    await query.edit_message_text(query.message.text + "\n\n❌ تم الرفض")
    await context.bot.send_message(
        chat_id=cid,
        text=f"عذراً، لم نتمكن من معالجة طلبك #{tid}.\nيمكنك المحاولة مجدداً بكتابة /start"
    )

async def show_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not tickets:
        await update.message.reply_text("لا توجد تذاكر بعد.")
        return
    recent = list(tickets.values())[-20:]
    lines  = ["📋 آخر التذاكر:\n"]
    btns   = []
    for t in reversed(recent):
        lines.append(f"#{t['tid']} | {t['status']} | {t['fname']} | {t['time']}")
        btns.append([InlineKeyboardButton(
            f"#{t['tid']} — {t['fname']} — {t['status']}",
            callback_data=f"viewticket_{t['tid']}"
        )])
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(btns)
    )

async def view_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔", show_alert=True)
        return
    await query.answer()
    tid = int(query.data.split("_")[1])
    t   = tickets.get(tid)
    if not t:
        await query.message.reply_text("التذكرة غير موجودة.")
        return
    keyboard = [[
        InlineKeyboardButton("✉️ رد نصي",    callback_data=f"replytext_{tid}_{t['user_id']}"),
        InlineKeyboardButton("📞 فتح محادثة", url=f"tg://user?id={t['user_id']}"),
        InlineKeyboardButton("❌ رفض",        callback_data=f"reject_{tid}_{t['user_id']}"),
    ]]
    await query.message.reply_text(
        f"🎫 تذكرة #{tid}\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 {t['fname']}  |  @{t['username']}\n"
        f"🆔 ID: {t['user_id']}\n"
        f"📦 {t['service']}\n"
        f"📊 الحالة: {t['status']}\n"
        f"🕐 {t['time']}\n"
        f"━━━━━━━━━━━━━━\n"
        f"{t['info']}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    client_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_SERVICE: [CallbackQueryHandler(service_selected, pattern="^service_")],
            WAITING_INFO:   [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_info)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_reply_trigger, pattern="^replytext_")],
        states={
            ADMIN_REPLY_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_send_reply)],
        },
        fallbacks=[],
    )

    app.add_handler(client_conv)
    app.add_handler(admin_conv)
    app.add_handler(CallbackQueryHandler(admin_reject,  pattern="^reject_"))
    app.add_handler(CallbackQueryHandler(view_ticket,   pattern="^viewticket_"))
    app.add_handler(CommandHandler("tickets", show_tickets))

    print("✅ البوت يعمل...")
    await app.run_polling(drop_pending_updates=True)

def main():
    # تشغيل سيرفر HTTP في thread منفصل
    threading.Thread(target=run_server, daemon=True).start()
    # تشغيل البوت عبر asyncio مباشرة
    asyncio.run(run_bot())

if __name__ == "__main__":
    main()
