import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "0"))

VIP_CHANNELS = [
    {"name": "قناة VIP 1", "link": "https://t.me/your_vip_1"},
    {"name": "قناة VIP 2", "link": "https://t.me/your_vip_2"},
]

CHOOSE_SERVICE, WAITING_INFO, ADMIN_REPLY_TEXT = range(3)
tickets = {}
ticket_counter = [0]
# تتبع آخر تذكرة لكل مستخدم
user_last_ticket = {}

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

def ticket_keyboard(tid, user_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✉️ رد",         callback_data=f"replytext_{tid}_{user_id}"),
        InlineKeyboardButton("📞 فتح محادثة", url=f"tg://user?id={user_id}"),
        InlineKeyboardButton("✅ إغلاق",       callback_data=f"close_{tid}_{user_id}"),
        InlineKeyboardButton("❌ رفض",         callback_data=f"reject_{tid}_{user_id}"),
    ]])

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
        "messages": [],
    }
    user_last_ticket[user.id] = tid

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
        reply_markup=ticket_keyboard(tid, user.id)
    )
    await update.message.reply_text(
        f"✅ تم إرسال طلبك!\n🎫 رقم تذكرتك: #{tid}\n\n"
        f"سيتواصل معك الأدمن قريباً 🙏\n\n"
        f"يمكنك إرسال أي رسالة إضافية وستصل للأدمن."
    )
    return ConversationHandler.END

async def relay_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        return
    text = update.message.text
    tid = user_last_ticket.get(user.id)

    if tid and tid in tickets:
        tickets[tid]["messages"].append({
            "from": "user",
            "text": text,
            "time": datetime.now().strftime("%H:%M")
        })
        tickets[tid]["status"] = "🔵 رد العميل"
        header = f"💬 رسالة من العميل على تذكرة #{tid}:"
        kb = ticket_keyboard(tid, user.id)
    else:
        header = f"💬 رسالة جديدة من عميل:"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("📞 فتح محادثة", url=f"tg://user?id={user.id}"),
        ]])

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"{header}\n"
            f"━━━━━━━━━━━━━━\n"
            f"👤 {user.first_name}  |  @{user.username or '—'}\n"
            f"━━━━━━━━━━━━━━\n"
            f"{text}"
        ),
        reply_markup=kb
    )
    await update.message.reply_text("✅ تم إرسال رسالتك للأدمن.")

async def admin_reply_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ ليس لديك صلاحية!", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    parts = query.data.split("_")
    tid = int(parts[1])
    cid = int(parts[2])
    context.user_data["reply_tid"] = tid
    context.user_data["reply_cid"] = cid
    fname = tickets[tid]["fname"] if tid in tickets else "العميل"
    await query.message.reply_text(
        f"✏️ اكتب ردّك على {fname} (تذكرة #{tid}):"
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
        text=f"📩 رد الأدمن:\n\n{text}"
    )
    if tid and tid in tickets:
        tickets[tid]["status"] = "✅ تم الرد"
        tickets[tid]["messages"].append({
            "from": "admin",
            "text": text,
            "time": datetime.now().strftime("%H:%M")
        })
    await update.message.reply_text(f"✅ تم إرسال ردّك للعميل")
    return ConversationHandler.END

async def admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔", show_alert=True)
        return
    await query.answer()
    parts = query.data.split("_")
    tid = int(parts[1])
    cid = int(parts[2])
    if tid in tickets:
        tickets[tid]["status"] = "✅ مغلقة"
    await query.edit_message_text(query.message.text + "\n\n✅ تم إغلاق التذكرة")
    await context.bot.send_message(
        chat_id=cid,
        text=f"✅ تم إغلاق تذكرتك #{tid}.\nشكراً لتواصلك معنا! يمكنك فتح طلب جديد بكتابة /start"
    )

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

    args = context.args
    filter_status = args[0] if args else None

    if not tickets:
        await update.message.reply_text("لا توجد تذاكر بعد.")
        return

    filtered = [t for t in tickets.values()
                if not filter_status or filter_status in t["status"]]

    if not filtered:
        await update.message.reply_text(f"لا توجد تذاكر بحالة: {filter_status}")
        return

    recent = list(reversed(filtered))[-20:]
    lines  = [f"📋 التذاكر ({len(filtered)} إجمالي):\n"]
    btns   = []

    for t in recent:
        lines.append(f"#{t['tid']} {t['status']} | {t['fname']} | {t['time']}")
        btns.append([InlineKeyboardButton(
            f"#{t['tid']} — {t['fname']} — {t['status']}",
            callback_data=f"viewticket_{t['tid']}"
        )])

    # أزرار الفلترة
    btns.append([
        InlineKeyboardButton("🟡 الجديدة",   callback_data="filter_جديد"),
        InlineKeyboardButton("🔵 ردود العملاء", callback_data="filter_رد"),
        InlineKeyboardButton("✅ المغلقة",    callback_data="filter_مغلقة"),
        InlineKeyboardButton("📋 الكل",       callback_data="filter_all"),
    ])

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(btns)
    )

async def filter_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔", show_alert=True)
        return
    await query.answer()
    f = query.data.replace("filter_", "")

    if f == "all":
        filtered = list(tickets.values())
    else:
        filtered = [t for t in tickets.values() if f in t["status"]]

    if not filtered:
        await query.message.reply_text("لا توجد تذاكر.")
        return

    recent = list(reversed(filtered))[-20:]
    lines  = [f"📋 التذاكر ({len(filtered)}):\n"]
    btns   = []
    for t in recent:
        lines.append(f"#{t['tid']} {t['status']} | {t['fname']} | {t['time']}")
        btns.append([InlineKeyboardButton(
            f"#{t['tid']} — {t['fname']} — {t['status']}",
            callback_data=f"viewticket_{t['tid']}"
        )])

    btns.append([
        InlineKeyboardButton("🟡 الجديدة",      callback_data="filter_جديد"),
        InlineKeyboardButton("🔵 ردود العملاء", callback_data="filter_رد"),
        InlineKeyboardButton("✅ المغلقة",       callback_data="filter_مغلقة"),
        InlineKeyboardButton("📋 الكل",          callback_data="filter_all"),
    ])

    await query.message.edit_text(
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

    # عرض سجل المحادثة
    history = ""
    if t.get("messages"):
        history = "\n\n💬 سجل المحادثة:\n"
        for m in t["messages"][-5:]:
            who = "👤 عميل" if m["from"] == "user" else "🔑 أدمن"
            history += f"{who} [{m['time']}]: {m['text']}\n"

    await query.message.reply_text(
        f"🎫 تذكرة #{tid}\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 {t['fname']}  |  @{t['username']}\n"
        f"🆔 ID: {t['user_id']}\n"
        f"📦 {t['service']}\n"
        f"📊 الحالة: {t['status']}\n"
        f"🕐 {t['time']}\n"
        f"━━━━━━━━━━━━━━\n"
        f"{t['info']}"
        f"{history}",
        reply_markup=ticket_keyboard(tid, t["user_id"])
    )

async def post_init(application):
    await application.bot.delete_webhook(drop_pending_updates=True)

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    print("✅ البوت يعمل...")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

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
    app.add_handler(CallbackQueryHandler(admin_reject,    pattern="^reject_"))
    app.add_handler(CallbackQueryHandler(admin_close,     pattern="^close_"))
    app.add_handler(CallbackQueryHandler(view_ticket,     pattern="^viewticket_"))
    app.add_handler(CallbackQueryHandler(filter_tickets,  pattern="^filter_"))
    app.add_handler(CommandHandler("tickets", show_tickets))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_user_message))

    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
