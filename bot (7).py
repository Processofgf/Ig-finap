import os
import asyncio
import sqlite3
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatMembersFilter
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from pyrogram.errors import FloodWait
from dotenv import load_dotenv

load_dotenv()

# --- Config Setup ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

# --- Initialize Bot & SQLite Database ---
app = Client("PremiumManagementBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

# Tables Setup
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    vouches INTEGER DEFAULT 0,
    warnings INTEGER DEFAULT 0,
    is_verified INTEGER DEFAULT 0
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS groups (
    chat_id INTEGER PRIMARY KEY,
    last_msg_id INTEGER DEFAULT NULL
)
""")
conn.commit()

# --- Helper Functions ---
def get_user_data(user_id):
    cursor.execute("SELECT vouches, warnings, is_verified FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return {"user_id": user_id, "vouches": 0, "warnings": 0, "is_verified": False}
    return {"user_id": user_id, "vouches": row[0], "warnings": row[1], "is_verified": bool(row[2])}

def parse_time(time_str: str) -> int:
    unit = time_str[-1].lower()
    try:
        val = int(time_str[:-1])
        if unit == 'm': return val * 60
        if unit == 'h': return val * 3600
        if unit == 'd': return val * 86400
    except ValueError:
        return 0
    return 0

# --- Dynamic Admin Filter ---
async def is_admin_func(_, client, message):
    if not message.from_user:
        return False
    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        return False

admin_filter = filters.create(is_admin_func)

# --- Automatically Register Group from Messages ---
@app.on_message(filters.group, group=-1)
async def register_group(_, message):
    chat_id = message.chat.id
    cursor.execute("INSERT OR IGNORE INTO groups (chat_id) VALUES (?)", (chat_id,))
    conn.commit()

# --- NEW: Bot Added To Group Greeting Handler ---
@app.on_message(filters.new_chat_members)
async def welcome_bot_to_group(_, message):
    bot_info = await app.get_me()
    for member in message.new_chat_members:
        if member.id == bot_info.id:
            # Welcome Message text when bot joins
            text = (
                "🚀 **Premium Management Bot Activated!**\n\n"
                "Thanks for adding me to this group. I am ready to manage your marketplace!\n\n"
                "📌 **What I can do:**\n"
                "• Track Member Reputation & Vouches (`/profile`)\n"
                "• Protect users with Official Escrow MMs (`/escrow`)\n"
                "• Dynamic admin controls (Warn, Mute, Ban)\n\n"
                "👉 Type `/help` to see the full list of commands!"
            )
            await message.reply_text(text)
            
            # Immediately add to group database for auto-reminders
            cursor.execute("INSERT OR IGNORE INTO groups (chat_id) VALUES (?)", (message.chat.id,))
            conn.commit()

# --- NEW: Personal Chat Welcome Handler (DM) ---
@app.on_message(filters.command("start") & filters.private)
async def start_private(_, message):
    bot_info = await app.get_me()
    text = (
        f"👋 **Hello {message.from_user.first_name}!**\n\n"
        f"I am a **Premium Marketplace Management Bot**.\n"
        f"I help groups track member reputation, handle vouches, and keep chats safe from scammers.\n\n"
        f"⚠️ **Note:** My commands only work inside Telegram Groups. "
        f"Please add me to your group to use my features!"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Me To Your Group", url=f"https://t.me/{bot_info.username}?startgroup=true")]
    ])
    await message.reply_text(text, reply_markup=buttons)

# --- Background Task: Smart Auto-Reminder ---
async def auto_reminder():
    await asyncio.sleep(10)
    while True:
        cursor.execute("SELECT chat_id, last_msg_id FROM groups")
        groups = cursor.fetchall()
        
        for chat_id, last_msg_id in groups:
            try:
                if last_msg_id:
                    try:
                        await app.delete_messages(chat_id, last_msg_id)
                    except Exception:
                        pass
                
                text = (
                    "⚠️ **IMPORTANT SECURITY REMINDER** ⚠️\n\n"
                    "To protect yourself from scammers, always use an official Middleman for every deal. "
                    "Do not deal directly in DMs!\n\n"
                    "🛡️ **Trusted MMs:** `@BMG009` & `@LAUGH`\n"
                    "*Deals done without our official MMs will not be supported.*"
                )
                buttons = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("💬 Contact BMG009", url="https://t.me/BMG009"),
                        InlineKeyboardButton("💬 Contact LAUGH", url="https://t.me/LAUGH")
                    ]
                ])
                
                msg = await app.send_message(chat_id, text, reply_markup=buttons, disable_web_page_preview=True)
                
                cursor.execute("UPDATE groups SET last_msg_id = ? WHERE chat_id = ?", (msg.id, chat_id))
                conn.commit()
                
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception:
                cursor.execute("DELETE FROM groups WHERE chat_id = ?", (chat_id,))
                conn.commit()
                
        await asyncio.sleep(450) # Runs every 7.5 minutes

# --- Commands Block ---

# 1. Help Menu
@app.on_message(filters.command("help") & filters.group)
async def help_cmd(_, message):
    text = "👑 **Premium Bot Main Menu**\n\nSelect a category below to explore the commands:"
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("ℹ️ Info", callback_data="help_info")],
        [InlineKeyboardButton("👤 User Profile", callback_data="help_profile")],
        [InlineKeyboardButton("👑 Admin Tools", callback_data="help_admin")]
    ])
    await message.reply_text(text, reply_markup=buttons)

@app.on_callback_query(filters.regex("^help_"))
async def help_callback(_, query):
    action = query.data.split("_")[1]
    
    if action == "info":
        text = "ℹ️ **Information:**\n\n• `/escrow` - Trusted MMs\n• `/rules` - Guidelines\n• `/dealing` - Deal format\n• `/admin` - Contact admins"
    elif action == "profile":
        text = "👤 **User Profile:**\n\n• `/profile @user` - View rep\n• `/vouch @user` - Give +1 trust\n• `/getinfo @user` - User data"
    elif action == "admin":
        member = await app.get_chat_member(query.message.chat.id, query.from_user.id)
        if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return await query.answer("❌ This menu is strictly for Admins!", show_alert=True)
            
        text = "👑 **Admin Tools:**\n\n• `/verify` / `/unverify` - Seller status\n• `/warn @user` - Log a warning\n• `/mute @user 1h` - Mute\n• `/ban @user` - Ban user"
        
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Menu", callback_data="help_main")]])
    if action == "main":
        text = "👑 **Premium Bot Main Menu**\n\nSelect a category below to explore the commands:"
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ℹ️ Info", callback_data="help_info")],
            [InlineKeyboardButton("👤 User Profile", callback_data="help_profile")],
            [InlineKeyboardButton("👑 Admin Tools", callback_data="help_admin")]
        ])
        
    await query.message.edit_text(text, reply_markup=buttons)

# 2. Informational Auto-Delete Commands
@app.on_message(filters.command(["escrow", "rules", "dealing", "admin"]) & filters.group)
async def info_commands(_, message):
    cmd = message.command[0]
    await message.delete()
    
    if cmd == "escrow":
        await message.reply_text("🛡️ **Official Escrow Info**\n\nOnly `@BMG009` and `@LAUGH` are authorized and trusted Middlemen.")
    elif cmd == "rules":
        await message.reply_text("📜 **Group Rules**\n\n1. No scamming (Immediate Ban)\n2. No direct dealing without MMs\n3. Respect all members.")
    elif cmd == "dealing":
        await message.reply_text("🤝 **Standard Deal Format**\n\n• **Buyer:** [Tag]\n• **Seller:** [Tag]\n• **Item:** [Details]\n• **Amount:** $[Price]")
    elif cmd == "admin":
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Chat with BMG009", url="https://t.me/BMG009")],
            [InlineKeyboardButton("💬 Chat with LAUGH", url="https://t.me/LAUGH")]
        ])
        await message.reply_text("👑 **Official Admins:**", reply_markup=buttons)

# 3. Profile Handling
@app.on_message(filters.command("profile") & filters.group)
async def view_profile(_, message):
    target = message.from_user if len(message.command) < 2 else await app.get_users(message.command[1])
    u_data = get_user_data(target.id)
    v_status = "Verified Seller ✅" if u_data["is_verified"] else "Unverified Member ❌"
    
    card = f"👤 **REPUTATION CARD FOR {target.first_name}**\n━━━━━━━━━━━━━━━━━━━\n• **Status:** {v_status}\n• **Vouches:** {u_data['vouches']} ⭐\n• **Warnings:** {u_data['warnings']}/3 ⚠️"
    await message.reply_text(card)

@app.on_message(filters.command("vouch") & filters.group)
async def add_vouch(_, message):
    if len(message.command) < 2: return await message.reply_text("👉 Usage: `/vouch @username`")
    try: target = await app.get_users(message.command[1])
    except Exception: return await message.reply_text("❌ User not found.")
    
    if target.id == message.from_user.id: return await message.reply_text("❌ You cannot vouch for yourself!")
    
    cursor.execute("UPDATE users SET vouches = vouches + 1 WHERE user_id = ?", (target.id,))
    if cursor.rowcount == 0: cursor.execute("INSERT INTO users (user_id, vouches) VALUES (?, 1)", (target.id,))
    conn.commit()
    await message.reply_text(f"⭐ Successfully added +1 vouch to {target.mention}.")

@app.on_message(filters.command("getinfo") & filters.group)
async def get_info(_, message):
    target = message.from_user if len(message.command) < 2 else await app.get_users(message.command[1])
    join_date = "N/A"
    try:
        member = await app.get_chat_member(message.chat.id, target.id)
        if member.joined_date: join_date = datetime.fromtimestamp(member.joined_date).strftime('%Y-%m-%d')
    except Exception: pass
    await message.reply_text(f"📊 **Info:**\n• **Name:** {target.first_name}\n• **ID:** `{target.id}`\n• **Join Date:** {join_date}")

# 4. Dynamic Report (Tags active admins in the group)
@app.on_message(filters.command("report") & filters.group)
async def report_user(_, message):
    if len(message.command) < 2: return await message.reply_text("👉 Usage: `/report @username [reason]`")
    try: target = await app.get_users(message.command[1])
    except Exception: return await message.reply_text("❌ User not found.")
    
    reason = " ".join(message.command[2:]) if len(message.command) > 2 else "No reason provided."
    await message.delete()
    
    admins = []
    async for admin in app.get_chat_members(message.chat.id, filter=ChatMembersFilter.ADMINISTRATORS):
        if not admin.user.is_bot:
            admins.append(admin.user.mention)
            
    admin_tags = " ".join(admins) if admins else "Admins"
    await message.reply_text(f"🚨 **REPORT ALERT** {admin_tags}\n\n• **Reported By:** {message.from_user.mention}\n• **Target:** {target.mention}\n• **Reason:** {reason}")

# 5. Admin Actions (Protected by Dynamic Admin Filter)
@app.on_message(filters.command("verify") & admin_filter & filters.group)
async def verify_user(_, message):
    if len(message.command) < 2: return await message.reply_text("👉 Usage: `/verify @username`")
    target = await app.get_users(message.command[1])
    cursor.execute("UPDATE users SET is_verified = 1 WHERE user_id = ?", (target.id,))
    if cursor.rowcount == 0: cursor.execute("INSERT INTO users (user_id, is_verified) VALUES (?, 1)", (target.id,))
    conn.commit()
    await message.reply_text(f"✅ {target.mention} is now marked as a **Verified Seller**!")

@app.on_message(filters.command("unverify") & admin_filter & filters.group)
async def unverify_user(_, message):
    if len(message.command) < 2: return await message.reply_text("👉 Usage: `/unverify @username`")
    target = await app.get_users(message.command[1])
    cursor.execute("UPDATE users SET is_verified = 0 WHERE user_id = ?", (target.id,))
    conn.commit()
    await message.reply_text(f"❌ Removed **Verified Seller** status from {target.mention}.")

@app.on_message(filters.command("warn") & admin_filter & filters.group)
async def warn_user(_, message):
    if len(message.command) < 2: return await message.reply_text("👉 Usage: `/warn @username [reason]`")
    target = await app.get_users(message.command[1])
    reason = " ".join(message.command[2:]) if len(message.command) > 2 else "Violation of rules."
    
    cursor.execute("UPDATE users SET warnings = warnings + 1 WHERE user_id = ?", (target.id,))
    if cursor.rowcount == 0: cursor.execute("INSERT INTO users (user_id, warnings) VALUES (?, 1)", (target.id,))
    conn.commit()
    
    u_data = get_user_data(target.id)
    await message.reply_text(f"⚠️ {target.mention} warned for: **{reason}**\nWarnings: `{u_data['warnings']}/3`")
    
    if u_data['warnings'] >= 3:
        try:
            await message.chat.ban_member(target.id)
            await message.reply_text(f"🚫 {target.mention} hit 3 warnings and is banned.")
            cursor.execute("UPDATE users SET warnings = 0 WHERE user_id = ?", (target.id,))
            conn.commit()
        except Exception: pass

@app.on_message(filters.command("mute") & admin_filter & filters.group)
async def mute_user(_, message):
    if len(message.command) < 3: return await message.reply_text("👉 Usage: `/mute @username [time: 30m/1h/1d]`")
    target = await app.get_users(message.command[1])
    duration = parse_time(message.command[2])
    if duration == 0: return await message.reply_text("❌ Invalid format! Use 30m, 1h, or 1d.")
    
    try:
        await message.chat.restrict_member(target.id, ChatPermissions(can_send_messages=False), until_date=int(datetime.now().timestamp() + duration))
        await message.reply_text(f"🔇 {target.mention} muted for `{message.command[2]}`.")
    except Exception as e:
        await message.reply_text(f"❌ Failed: {e}")

@app.on_message(filters.command("ban") & admin_filter & filters.group)
async def ban_user(_, message):
    if len(message.command) < 2: return await message.reply_text("👉 Usage: `/ban @username`")
    target = await app.get_users(message.command[1])
    try:
        await message.chat.ban_member(target.id)
        await message.reply_text(f"🚫 {target.mention} has been banned.")
    except Exception as e:
        await message.reply_text(f"❌ Failed: {e}")

# --- Execute ---
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(auto_reminder())
    print("🚀 Premium Bot Engine Running...")
    app.run()