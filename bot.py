import os
import telebot
import random
import threading
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
import time
from flask import Flask, request
import logging
import requests
from pymongo import MongoClient

# ✅ تفعيل السجلات
logging.basicConfig(level=logging.INFO)
print("🚀 Starting Bot...")

# فحص BOT_TOKEN
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ BOT_TOKEN not found!")
    exit(1)

# 🔗 اتصال MongoDB
MONGO_URI = os.environ.get('MONGO_URI')
if not MONGO_URI:
    print("❌ MONGO_URI not found!")
    exit(1)

try:
    client = MongoClient(MONGO_URI)
    db = client['usdt_bot']
    users_collection = db['users']
    print("✅ Connected to MongoDB")
except Exception as e:
    print(f"❌ MongoDB error: {e}")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

# 🔐 إعدادات المشرفين
ADMIN_IDS = [8400225549]
YOUR_USER_ID = 8400225549

def is_admin(user_id):
    return user_id in ADMIN_IDS

# مستويات VIP - أرباح مخفضة للنصف
VIP_LEVELS = {
    0: {"name_ar": "🟢 مبتدئ", "name_en": "🟢 Beginner", "daily_bonus": 0.4, "max_attempts": 3, "price": 0},
    1: {"name_ar": "🟢 برونز", "name_en": "🟢 Bronze", "daily_bonus": 0.6, "max_attempts": 5, "price": 5},
    2: {"name_ar": "🔵 سيلفر", "name_en": "🔵 Silver", "daily_bonus": 0.9, "max_attempts": 8, "price": 10},
    3: {"name_ar": "🟡 جولد", "name_en": "🟡 Gold", "daily_bonus": 1.4, "max_attempts": 13, "price": 20}
}

# نظام اللغات
LANGUAGES = {
    'ar': {
        'games_btn': "🎮 ألعاب الربح",
        'vip_btn': "💎 ترقية VIP",
        'referral_btn': "👥 نظام الإحالات",
        'withdraw_btn': "💰 سحب الأرباح",
        'deposit_btn': "💳 إيداع الرصيد",
        'daily_bonus_btn': "🎁 المكافأة اليومية",
        'support_btn': "🆘 الدعم الفني",
        'refresh_btn': "🔄 تحديث البيانات",
        'back_btn': "🔙 رجوع",
    },
    'en': {
        'games_btn': "🎮 Earn Games",
        'vip_btn': "💎 Upgrade VIP",
        'referral_btn': "👥 Referral System",
        'withdraw_btn': "💰 Withdraw Earnings",
        'deposit_btn': "💳 Deposit Balance",
        'daily_bonus_btn': "🎁 Daily Bonus",
        'support_btn': "🆘 Technical Support",
        'refresh_btn': "🔄 Refresh Data",
        'back_btn': "🔙 Back",
    }
}

def get_user_language(user_id):
    user = get_user(user_id)
    return user.get('language', 'ar')

def set_user_language(user_id, language):
    return update_user(user_id, language=language)

def t(user_id, key):
    lang = get_user_language(user_id)
    return LANGUAGES[lang].get(key, key)

def get_user(user_id):
    user_id_str = str(user_id)
    try:
        user_data = users_collection.find_one({"user_id": user_id_str})
        if user_data:
            user_data.pop('_id', None)
            return user_data
        else:
            new_user = {
                'user_id': user_id_str,
                'first_name': "", 'username': "",
                'balance': 0.75, 'referral_count': 0, 'new_referrals': 0,
                'vip_level': 0, 'attempts': 3, 'total_earnings': 0.75,
                'total_deposits': 0.0, 'registration_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'last_activity': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'last_mining_date': None,
                'games_played_today': 0, 'has_deposit': 0, 'language': 'ar',
                'referral_tracking': {},
                'joined_via_referral': False,
                'referral_notification_sent': False,
                'referral_source': None,
                'first_game_played': False,
                'referral_verified': False,
                'has_received_referral': False  # 🔐 الحقل الجديد
            }
            users_collection.insert_one(new_user)
            return new_user
    except Exception as e:
        print(f"❌ Error getting user: {e}")
        return None

def update_user(user_id, **kwargs):
    try:
        user_id_str = str(user_id)
        users_collection.update_one({"user_id": user_id_str}, {"$set": kwargs})
        return True
    except Exception as e:
        print(f"❌ Error updating user: {e}")
        return False

def handle_referral_system(message):
    """🎯 نظام الإحالات المعدل - حل نهائي"""
    try:
        user_id = message.from_user.id
        command_parts = message.text.split()
        
        if len(command_parts) > 1 and command_parts[1].startswith('ref'):
            try:
                referrer_id = int(command_parts[1][3:])
                
                # 🔒 منع الإحالة الذاتية
                if referrer_id == user_id:
                    return
                
                referrer = get_user(referrer_id)
                current_user = get_user(user_id)
                
                if not referrer or not current_user:
                    return
                
                # 🔐 الشرط الحاسم: منع الإحالة إذا كان المستخدم قد استقبل إحالة من قبل
                if current_user.get('has_received_referral', False):
                    print(f"🚫 User {user_id} already received referral before - BLOCKED")
                    return
                
                # 🔐 منع الإحالة إذا كان المستخدم لديه أي نشاط سابق
                user_reg_date = datetime.strptime(current_user['registration_date'], '%Y-%m-%d %H:%M:%S')
                time_since_reg = datetime.now() - user_reg_date
                
                has_previous_activity = (
                    current_user.get('games_played_today', 0) > 0 or
                    current_user.get('total_deposits', 0) > 0 or
                    current_user.get('balance', 0) > 0.75 or
                    current_user.get('referral_count', 0) > 0 or
                    time_since_reg.total_seconds() > 300  # أكثر من 5 دقائق
                )
                
                if has_previous_activity:
                    print(f"🚫 User {user_id} has previous activity - BLOCKED")
                    return
                
                # 🔒 منع الإحالات المكررة
                referral_key = f"ref_{user_id}"
                if referrer.get('referral_tracking', {}).get(referral_key):
                    return
                
                # ✅ تسجيل الإحالة كمعلقة
                referral_tracking = referrer.get('referral_tracking', {})
                referral_tracking[referral_key] = {
                    'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'new_user_id': user_id,
                    'status': 'pending_verification'
                }
                
                update_user(referrer_id, referral_tracking=referral_tracking)
                update_user(user_id, referral_source=referrer_id, joined_via_referral=True)
                
                print(f"✅ Referral pending: {referrer_id} -> {user_id}")
                
            except Exception as e:
                print(f"❌ Referral error: {e}")
    except Exception as e:
        print(f"❌ Referral system error: {e}")

def verify_referral_on_first_game(user_id):
    """🎯 التحقق من الإحالة عند أول لعبة"""
    try:
        user = get_user(user_id)
        if not user or not user.get('joined_via_referral') or not user.get('referral_source'):
            return False
        
        referrer_id = user['referral_source']
        referrer = get_user(referrer_id)
        
        if not referrer:
            return False
        
        # 🔐 الشروط النهائية لمنح المكافأة
        user_reg_date = datetime.strptime(user['registration_date'], '%Y-%m-%d %H:%M:%S')
        time_since_reg = datetime.now() - user_reg_date
        
        can_get_bonus = (
            user.get('games_played_today', 0) >= 1 and
            time_since_reg.total_seconds() > 60 and  # مضى أكثر من دقيقة
            not user.get('has_received_referral', False) and
            not user.get('referral_verified', False)
        )
        
        if not can_get_bonus:
            return False
        
        referral_key = f"ref_{user_id}"
        referral_tracking = referrer.get('referral_tracking', {})
        
        if referral_tracking.get(referral_key, {}).get('status') == 'pending_verification':
            # ✅ منح المكافأة للمُحيل
            update_user(referrer_id,
                balance=round(referrer['balance'] + 0.50, 2),
                total_earnings=round(referrer['total_earnings'] + 0.50, 2),
                referral_count=referrer['referral_count'] + 1,
                new_referrals=referrer['new_referrals'] + 1
            )
            
            # ✅ تحديث حالة المستخدم
            update_user(user_id,
                referral_verified=True,
                referral_notification_sent=True,
                has_received_referral=True  # 🔐 منع المستقبل
            )
            
            # تحديث حالة الإحالة
            referral_tracking[referral_key]['status'] = 'verified'
            referral_tracking[referral_key]['verified_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            update_user(referrer_id, referral_tracking=referral_tracking)
            
            # 📩 إرسال إشعار
            try:
                lang = get_user_language(referrer_id)
                if lang == 'ar':
                    msg = "🎉 إحالة جديدة مؤكدة! +0.50 USDT"
                else:
                    msg = "🎉 New verified referral! +0.50 USDT"
                bot.send_message(referrer_id, msg)
            except:
                pass
            
            print(f"✅ Referral bonus given: {referrer_id} -> {user_id}")
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ Referral verification error: {e}")
        return False

def get_remaining_attempts(user):
    base_attempts = VIP_LEVELS[user['vip_level']]['max_attempts']
    extra_attempts = user.get('new_referrals', 0)
    used_attempts = user.get('games_played_today', 0)
    total_attempts = base_attempts + extra_attempts
    remaining = total_attempts - used_attempts
    return max(0, remaining), total_attempts, extra_attempts

def get_membership_days(user_id):
    user = get_user(user_id)
    if not user: return 0, 10
    try:
        reg_date = datetime.strptime(user['registration_date'].split()[0], '%Y-%m-%d')
        days_registered = (datetime.now() - reg_date).days
        days_remaining = max(0, 10 - days_registered)
        return days_registered, days_remaining
    except:
        return 0, 10

def can_withdraw(user):
    try:
        reg_date = datetime.strptime(user['registration_date'].split()[0], '%Y-%m-%d')
        days_registered = (datetime.now() - reg_date).days
        has_10_days = days_registered >= 10
        has_150_balance = user['balance'] >= 150
        has_25_refs = user.get('new_referrals', 0) >= 25
        has_deposit = user.get('has_deposit', 0) == 1
        return has_deposit and has_150_balance and has_25_refs and has_10_days
    except:
        return False

def get_mining_time_left(user_id):
    user = get_user(user_id)
    if not user or not user['last_mining_date']:
        return "جاهز الآن! 🎁" if get_user_language(user_id) == 'ar' else "Ready Now! 🎁"
    try:
        last_mining = datetime.strptime(user['last_mining_date'], '%Y-%m-%d %H:%M:%S')
        next_mining = last_mining + timedelta(hours=24)
        if datetime.now() >= next_mining:
            return "جاهز الآن! 🎁" if get_user_language(user_id) == 'ar' else "Ready Now! 🎁"
        time_left = next_mining - datetime.now()
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d} ⏳"
    except:
        return "جاهز الآن! 🎁" if get_user_language(user_id) == 'ar' else "Ready Now! 🎁"

def claim_daily_bonus(user_id):
    user = get_user(user_id)
    if not user: return False, "❌ User not found"
    
    if user.get('last_mining_date'):
        last_claim = datetime.strptime(user['last_mining_date'], '%Y-%m-%d %H:%M:%S')
        next_claim = last_claim + timedelta(hours=24)
        if datetime.now() < next_claim:
            time_left = next_claim - datetime.now()
            hours = time_left.seconds // 3600
            minutes = (time_left.seconds % 3600) // 60
            if get_user_language(user_id) == 'ar':
                return False, f"⏳ انتظر {hours:02d}:{minutes:02d} للمكافأة التالية"
            else:
                return False, f"⏳ Wait {hours:02d}:{minutes:02d} for next bonus"
    
    vip_info = VIP_LEVELS[user['vip_level']]
    daily_bonus = vip_info['daily_bonus']
    new_balance = user['balance'] + daily_bonus
    
    if update_user(user_id, balance=new_balance, total_earnings=user['total_earnings'] + daily_bonus, last_mining_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S')):
        if get_user_language(user_id) == 'ar':
            return True, f"🎉 <b>تم استلام المكافأة اليومية!</b>\n💰 <b>المبلغ:</b> {daily_bonus:.2f} USDT\n💵 <b>الرصيد الجديد:</b> {new_balance:.2f} USDT"
        else:
            return True, f"🎉 <b>Daily Bonus Claimed!</b>\n💰 <b>Amount:</b> {daily_bonus:.2f} USDT\n💵 <b>New Balance:</b> {new_balance:.2f} USDT"
    return False, "❌ Failed to claim bonus"

def show_main_menu(chat_id, message_id=None, user_id=None):
    try:
        if not user_id: return False
        user_data = get_user(user_id)
        if not user_data: return False
        
        remaining_attempts, total_attempts, _ = get_remaining_attempts(user_data)
        vip_info = VIP_LEVELS[user_data['vip_level']]
        days_registered, days_remaining = get_membership_days(user_id)
        lang = get_user_language(user_id)
        
        vip_name = vip_info['name_ar'] if lang == 'ar' else vip_info['name_en']
        can_withdraw_user = can_withdraw(user_data)
        status_text = "✅ <b>مفعل</b>" if can_withdraw_user else "❌ <b>غير مفعل</b>" if lang == 'ar' else "✅ <b>Active</b>" if can_withdraw_user else "❌ <b>Inactive</b>"
        days_text = f"({days_remaining} متبقي)" if days_registered < 10 else "✅" if lang == 'ar' else f"({days_remaining} days left)" if days_registered < 10 else "✅"
        
        profile_text = f"""
<b>✨ الملف الشخصي المتقدم ✨</b>

👤 <b>المستخدم:</b> {user_data['first_name'] or 'زائر جديد'}
🆔 <b>المعرف:</b> <code>{user_id}</code>
📅 <b>مدة العضوية:</b> {days_registered}/10 أيام {days_text}

<b>💼 الحالة المالية:</b>
├ 💰 <b>الرصيد:</b> <code>{user_data['balance']:.2f} USDT</code>
├ 💎 <b>إجمالي الأرباح:</b> <code>{user_data['total_earnings']:.2f} USDT</code>
└ 💳 <b>إجمالي الإيداعات:</b> <code>{user_data['total_deposits']:.2f} USDT</code>

<b>🏆 المستوى والصلاحيات:</b>
├ {vip_name}
├ 🎯 <b>محاولات اليوم:</b> {remaining_attempts}/{total_attempts}
└ 💼 <b>الإحالات:</b> انقر لعرض التفاصيل

⏰ <b>المكافأة اليومية:</b> {get_mining_time_left(user_id)}
🔐 <b>حالة السحب:</b> {status_text}
📅 <b>تاريخ التسجيل:</b> {user_data['registration_date'].split()[0]}
        """ if lang == 'ar' else f"""
<b>✨ Advanced Profile ✨</b>

👤 <b>User:</b> {user_data['first_name'] or 'New User'}
🆔 <b>ID:</b> <code>{user_id}</code>
📅 <b>Membership:</b> {days_registered}/10 days {days_text}

<b>💼 Financial Status:</b>
├ 💰 <b>Balance:</b> <code>{user_data['balance']:.2f} USDT</code>
├ 💎 <b>Total Earnings:</b> <code>{user_data['total_earnings']:.2f} USDT</code>
└ 💳 <b>Total Deposits:</b> <code>{user_data['total_deposits']:.2f} USDT</code>

<b>🏆 Level & Privileges:</b>
├ {vip_name}
├ 🎯 <b>Daily Attempts:</b> {remaining_attempts}/{total_attempts}
└ 💼 <b>Referrals:</b> Click for details

⏰ <b>Daily Bonus:</b> {get_mining_time_left(user_id)}
🔐 <b>Withdrawal Status:</b> {status_text}
📅 <b>Registration Date:</b> {user_data['registration_date'].split()[0]}
        """
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton(t(user_id, 'games_btn'), callback_data="games"),
            InlineKeyboardButton(t(user_id, 'vip_btn'), callback_data="vip_services")
        )
        keyboard.add(
            InlineKeyboardButton(t(user_id, 'referral_btn'), callback_data="referral"),
            InlineKeyboardButton(t(user_id, 'withdraw_btn'), callback_data="withdraw")
        )
        keyboard.add(
            InlineKeyboardButton(t(user_id, 'deposit_btn'), callback_data="deposit"),
            InlineKeyboardButton(t(user_id, 'daily_bonus_btn'), callback_data="daily_bonus")
        )
        keyboard.add(
            InlineKeyboardButton(t(user_id, 'support_btn'), url="https://t.me/Trust_wallet_Support_4"),
            InlineKeyboardButton(t(user_id, 'refresh_btn'), callback_data="refresh_profile")
        )
        
        if lang == 'ar':
            keyboard.add(InlineKeyboardButton("🌐 Switch to English", callback_data="change_language_en"))
        else:
            keyboard.add(InlineKeyboardButton("🌐 التغيير إلى العربية", callback_data="change_language_ar"))
        
        if message_id:
            bot.edit_message_text(profile_text, chat_id=chat_id, message_id=message_id, reply_markup=keyboard)
        else:
            bot.send_message(chat_id, profile_text, reply_markup=keyboard)
        return True
    except Exception as e:
        print(f"❌ Menu error: {e}")
        return False

# 🎯 الأوامر الأساسية
@bot.message_handler(commands=['start', 'profile'])
def handle_start(message):
    try:
        user_id = message.from_user.id
        
        handle_referral_system(message)
        
        update_user(user_id, 
                   first_name=message.from_user.first_name or "", 
                   username=message.from_user.username or "", 
                   last_activity=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        show_main_menu(message.chat.id, user_id=user_id)
    except Exception as e:
        print(f"❌ Start error: {e}")

@bot.message_handler(commands=['language'])
def handle_language(message):
    try:
        user_id = message.from_user.id
        current_lang = get_user_language(user_id)
        keyboard = InlineKeyboardMarkup()
        if current_lang == 'ar':
            keyboard.add(InlineKeyboardButton("🇺🇸 English", callback_data="change_language_en"))
            bot.send_message(message.chat.id, "🌐 <b>اختر اللغة:</b>", reply_markup=keyboard)
        else:
            keyboard.add(InlineKeyboardButton("🇸🇦 العربية", callback_data="change_language_ar"))
            bot.send_message(message.chat.id, "🌐 <b>Choose Language:</b>", reply_markup=keyboard)
    except Exception as e:
        print(f"❌ Language error: {e}")

@bot.message_handler(commands=['myid'])
def handle_myid(message):
    bot.reply_to(message, f"🆔 <b>معرفك:</b> <code>{message.from_user.id}</code>")

# 🎮 نظام الألعاب
@bot.callback_query_handler(func=lambda call: call.data == "games")
def show_games(call):
    try:
        user = get_user(call.from_user.id)
        remaining_attempts, total_attempts, _ = get_remaining_attempts(user)
        lang = get_user_language(call.from_user.id)
        
        games_text = f"""🎮 <b>قائمة الألعاب</b>

🎯 <b>المحاولات المتبقية:</b> {remaining_attempts}/{total_attempts}
💰 <b>الربح لكل محاولة:</b> 0.1 - 0.3 USDT

<b>اختر اللعبة:</b>""" if lang == 'ar' else f"""🎮 <b>Games List</b>

🎯 <b>Remaining Attempts:</b> {remaining_attempts}/{total_attempts}
💰 <b>Earnings per attempt:</b> 0.1 - 0.3 USDT

<b>Choose game:</b>"""
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        if lang == 'ar':
            keyboard.add(
                InlineKeyboardButton("🎰 سلوت", callback_data="game_slot"),
                InlineKeyboardButton("🎲 نرد", callback_data="game_dice")
            )
            keyboard.add(InlineKeyboardButton("🔙 رجوع", callback_data="back_to_profile"))
        else:
            keyboard.add(
                InlineKeyboardButton("🎰 Slots", callback_data="game_slot"),
                InlineKeyboardButton("🎲 Dice", callback_data="game_dice")
            )
            keyboard.add(InlineKeyboardButton("🔙 Back", callback_data="back_to_profile"))
        
        bot.edit_message_text(games_text, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
    except Exception as e:
        print(f"❌ Games error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "game_slot")
def play_slot(call):
    try:
        user = get_user(call.from_user.id)
        remaining_attempts, total_attempts, _ = get_remaining_attempts(user)
        
        if remaining_attempts <= 0:
            bot.answer_callback_query(call.id, "❌ لا توجد محاولات متبقية اليوم!" if get_user_language(call.from_user.id) == 'ar' else "❌ No attempts left today!", show_alert=True)
            return
        
        games_played_before = user.get('games_played_today', 0)
        update_user(call.from_user.id, games_played_today=games_played_before + 1)
        
        # 🔐 إذا كانت هذه أول لعبة، تحقق من الإحالة
        if games_played_before == 0:
            verify_referral_on_first_game(call.from_user.id)
        
        symbols = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎"]
        result = [random.choice(symbols) for _ in range(3)]
        
        if result[0] == result[1] == result[2]:
            win_amount = round(random.uniform(0.1, 0.3), 2)
            win_text = "🎉 ربح كبير!" if get_user_language(call.from_user.id) == 'ar' else "🎉 Big win!"
        elif result[0] == result[1] or result[1] == result[2]:
            win_amount = round(random.uniform(0.05, 0.15), 2)
            win_text = "👍 ربح جيد!" if get_user_language(call.from_user.id) == 'ar' else "👍 Good win!"
        else:
            win_amount = 0
            win_text = "😞 حاول مرة أخرى" if get_user_language(call.from_user.id) == 'ar' else "😞 Try again"
        
        new_balance = user['balance'] + win_amount
        update_user(call.from_user.id, balance=new_balance, total_earnings=user['total_earnings'] + win_amount)
        
        user = get_user(call.from_user.id)
        remaining_attempts, total_attempts, _ = get_remaining_attempts(user)
        lang = get_user_language(call.from_user.id)
        
        game_result = f"""🎰 <b>لعبة السلوت</b>

{' | '.join(result)}

{win_text}
💰 <b>الربح:</b> {win_amount:.2f} USDT
💵 <b>الرصيد الجديد:</b> {new_balance:.2f} USDT

🎯 <b>المحاولات المتبقية:</b> {remaining_attempts}/{total_attempts}""" if lang == 'ar' else f"""🎰 <b>Slot Game</b>

{' | '.join(result)}

{win_text}
💰 <b>Win:</b> {win_amount:.2f} USDT
💵 <b>New Balance:</b> {new_balance:.2f} USDT

🎯 <b>Remaining Attempts:</b> {remaining_attempts}/{total_attempts}"""
        
        keyboard = InlineKeyboardMarkup()
        if lang == 'ar':
            keyboard.add(InlineKeyboardButton("🎰 العب مرة أخرى", callback_data="game_slot"))
            keyboard.add(InlineKeyboardButton("🔙 رجوع", callback_data="games"))
        else:
            keyboard.add(InlineKeyboardButton("🎰 Play Again", callback_data="game_slot"))
            keyboard.add(InlineKeyboardButton("🔙 Back", callback_data="games"))
        
        bot.edit_message_text(game_result, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
    except Exception as e:
        print(f"❌ Slot error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "game_dice")
def play_dice(call):
    try:
        user = get_user(call.from_user.id)
        remaining_attempts, total_attempts, _ = get_remaining_attempts(user)
        
        if remaining_attempts <= 0:
            bot.answer_callback_query(call.id, "❌ لا توجد محاولات متبقية اليوم!" if get_user_language(call.from_user.id) == 'ar' else "❌ No attempts left today!", show_alert=True)
            return
        
        games_played_before = user.get('games_played_today', 0)
        update_user(call.from_user.id, games_played_today=games_played_before + 1)
        
        # 🔐 إذا كانت هذه أول لعبة، تحقق من الإحالة
        if games_played_before == 0:
            verify_referral_on_first_game(call.from_user.id)
        
        dice1 = random.randint(1, 6)
        dice2 = random.randint(1, 6)
        total = dice1 + dice2
        
        if total == 7:
            win_amount = round(random.uniform(0.08, 0.2), 2)
            win_text = "🎉 ربح كبير! (رقم الحظ)" if get_user_language(call.from_user.id) == 'ar' else "🎉 Big win! (Lucky number)"
        elif total >= 10:
            win_amount = round(random.uniform(0.04, 0.12), 2)
            win_text = "👍 ربح جيد!" if get_user_language(call.from_user.id) == 'ar' else "👍 Good win!"
        elif total <= 4:
            win_amount = round(random.uniform(0.02, 0.08), 2)
            win_text = "👌 ربح صغير" if get_user_language(call.from_user.id) == 'ar' else "👌 Small win"
        else:
            win_amount = 0
            win_text = "😞 حاول مرة أخرى" if get_user_language(call.from_user.id) == 'ar' else "😞 Try again"
        
        new_balance = user['balance'] + win_amount
        update_user(call.from_user.id, balance=new_balance, total_earnings=user['total_earnings'] + win_amount)
        
        user = get_user(call.from_user.id)
        remaining_attempts, total_attempts, _ = get_remaining_attempts(user)
        lang = get_user_language(call.from_user.id)
        
        game_result = f"""🎲 <b>لعبة النرد</b>

🎲 <b>النرد:</b> {dice1} + {dice2} = {total}

{win_text}
💰 <b>الربح:</b> {win_amount:.2f} USDT
💵 <b>الرصيد الجديد:</b> {new_balance:.2f} USDT

🎯 <b>المحاولات المتبقية:</b> {remaining_attempts}/{total_attempts}""" if lang == 'ar' else f"""🎲 <b>Dice Game</b>

🎲 <b>Dice:</b> {dice1} + {dice2} = {total}

{win_text}
💰 <b>Win:</b> {win_amount:.2f} USDT
💵 <b>New Balance:</b> {new_balance:.2f} USDT

🎯 <b>Remaining Attempts:</b> {remaining_attempts}/{total_attempts}"""
        
        keyboard = InlineKeyboardMarkup()
        if lang == 'ar':
            keyboard.add(InlineKeyboardButton("🎲 العب مرة أخرى", callback_data="game_dice"))
            keyboard.add(InlineKeyboardButton("🔙 رجوع", callback_data="games"))
        else:
            keyboard.add(InlineKeyboardButton("🎲 Play Again", callback_data="game_dice"))
            keyboard.add(InlineKeyboardButton("🔙 Back", callback_data="games"))
        
        bot.edit_message_text(game_result, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
    except Exception as e:
        print(f"❌ Dice error: {e}")

# 🔄 معالجة الأزرار الأساسية
@bot.callback_query_handler(func=lambda call: call.data.startswith('change_language_'))
def handle_language_change(call):
    try:
        user_id = call.from_user.id
        new_lang = call.data.replace('change_language_', '')
        set_user_language(user_id, new_lang)
        bot.answer_callback_query(call.id, "✅ تم تغيير اللغة إلى العربية" if new_lang == 'ar' else "✅ Language changed to English")
        show_main_menu(call.message.chat.id, call.message.message_id, user_id)
    except Exception as e:
        print(f"❌ Language change error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "back_to_profile")
def back_to_profile(call):
    show_main_menu(call.message.chat.id, call.message.message_id, call.from_user.id)

@bot.callback_query_handler(func=lambda call: call.data == "refresh_profile")
def refresh_profile(call):
    show_main_menu(call.message.chat.id, call.message.message_id, call.from_user.id)
    bot.answer_callback_query(call.id, "✅ تم التحديث" if get_user_language(call.from_user.id) == 'ar' else "✅ Updated")

@bot.callback_query_handler(func=lambda call: call.data == "daily_bonus")
def handle_daily_bonus(call):
    success, message = claim_daily_bonus(call.from_user.id)
    bot.answer_callback_query(call.id, message, show_alert=True)
    if success:
        time.sleep(1)
        show_main_menu(call.message.chat.id, call.message.message_id, call.from_user.id)

# 👥 نظام الإحالات المعدل
@bot.callback_query_handler(func=lambda call: call.data == "referral")
def handle_referral(call):
    try:
        user_id = call.from_user.id
        user = get_user(user_id)
        referral_link = f"https://t.me/Usdt_Mini1Bot?start=ref{user_id}"
        
        lang = get_user_language(user_id)
        
        referral_text = f"""<b>👥 نظام الإحالات</b>

📊 <b>إحصائياتك:</b>
├ 👤 <b>الإحالات المؤكدة:</b> {user['referral_count']} مستخدم
├ 💰 <b>أرباح الإحالات:</b> {user['referral_count'] * 0.50:.2f} USDT
└ 🎯 <b>المطلوب للسحب:</b> {user['new_referrals']}/25 إحالة

<b>🔗 رابط الدعوة الخاص بك:</b>
<code>{referral_link}</code>

<b>🎁 مزايا الإحالات:</b>
• 0.50 USDT مكافأة فورية لكل إحالة مؤكدة
• +1 محاولة ألعاب يومية لكل إحالة  
• وصول أسرع لشروط السحب

<b>📤 شارك الرابط مع أصدقائك واكسب المزيد!</b>""" if lang == 'ar' else f"""<b>👥 Referral System</b>

📊 <b>Your Statistics:</b>
├ 👤 <b>Confirmed Referrals:</b> {user['referral_count']} users
├ 💰 <b>Referral Earnings:</b> {user['referral_count'] * 0.50:.2f} USDT
└ 🎯 <b>Required for Withdrawal:</b> {user['new_referrals']}/25 referrals

<b>🔗 Your referral link:</b>
<code>{referral_link}</code>

<b>🎁 Referral benefits:</b>
• 0.50 USDT instant bonus per confirmed referral
• +1 daily game attempt per referral  
• Faster access to withdrawal conditions

<b>📤 Share the link with your friends and earn more!</b>"""
        
        keyboard = InlineKeyboardMarkup()
        if lang == 'ar':
            keyboard.add(InlineKeyboardButton("📤 مشاركة الرابط", url=f"https://t.me/share/url?url={referral_link}"))
            keyboard.add(InlineKeyboardButton("🔙 رجوع", callback_data="back_to_profile"))
        else:
            keyboard.add(InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={referral_link}"))
            keyboard.add(InlineKeyboardButton("🔙 Back", callback_data="back_to_profile"))
        
        bot.edit_message_text(referral_text, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
    except Exception as e:
        print(f"❌ Referral error: {e}")

# ... (بقية الأكواد تبقى كما هي بدون تغيير)

# 💎 نظام VIP
@bot.callback_query_handler(func=lambda call: call.data == "vip_services")
def show_vip_services(call):
    try:
        lang = get_user_language(call.from_user.id)
        
        vip_text = """💎 <b>العضويات VIP المميزة:</b>

🟢 <b>برونز VIP - 5 USDT:</b>
• مكافأة يومية 0.6 USDT
• +2 محاولات ألعاب يومية
• دعم فني متميز

🔵 <b>سيلفر VIP - 10 USDT:</b>
• مكافأة يومية 0.9 USDT  
• +5 محاولات ألعاب يومية
• أولوية في معالجة طلبات السحب

🟡 <b>جولد VIP - 20 USDT:</b>
• مكافأة يومية 1.4 USDT
• +10 محاولات ألعاب يومية
• أولوية قصوى في جميع الخدمات

<b>اختر العضوية المناسبة:</b>""" if lang == 'ar' else """💎 <b>VIP Memberships:</b>

🟢 <b>Bronze VIP - 5 USDT:</b>
• Daily bonus 0.6 USDT
• +2 daily game attempts
• Premium technical support

🔵 <b>Silver VIP - 10 USDT:</b>
• Daily bonus 0.9 USDT  
• +5 daily game attempts
• Priority in withdrawal requests

🟡 <b>Gold VIP - 20 USDT:</b>
• Daily bonus 1.4 USDT
• +10 daily game attempts
• Top priority in all services

<b>Choose your membership:</b>"""
        
        keyboard = InlineKeyboardMarkup(row_width=1)
        if lang == 'ar':
            keyboard.add(
                InlineKeyboardButton("🟢 شراء برونز VIP - 5 USDT", callback_data="vip_bronze"),
                InlineKeyboardButton("🔵 شراء سيلفر VIP - 10 USDT", callback_data="vip_silver"),
                InlineKeyboardButton("🟡 شراء جولد VIP - 20 USDT", callback_data="vip_gold"),
                InlineKeyboardButton("🔙 رجوع", callback_data="back_to_profile")
            )
        else:
            keyboard.add(
                InlineKeyboardButton("🟢 Buy Bronze VIP - 5 USDT", callback_data="vip_bronze"),
                InlineKeyboardButton("🔵 Buy Silver VIP - 10 USDT", callback_data="vip_silver"),
                InlineKeyboardButton("🟡 Buy Gold VIP - 20 USDT", callback_data="vip_gold"),
                InlineKeyboardButton("🔙 Back", callback_data="back_to_profile")
            )
        
        bot.edit_message_text(vip_text, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
    except Exception as e:
        print(f"❌ VIP error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('vip_'))
def handle_vip_purchase(call):
    try:
        user = get_user(call.from_user.id)
        vip_type = call.data.replace('vip_', '')
        
        vip_names = {'bronze': 'برونز', 'silver': 'سيلفر', 'gold': 'جولد'}
        vip_prices = {'bronze': 5.0, 'silver': 10.0, 'gold': 20.0}
        
        lang = get_user_language(call.from_user.id)
        vip_name = vip_names[vip_type] if lang == 'ar' else vip_type.capitalize()
        vip_price = vip_prices[vip_type]
        
        user_link = f"<a href='tg://user?id={call.from_user.id}'>{user['first_name'] or 'مستخدم'}</a>"
        user_id_link = f"<a href='tg://user?id={call.from_user.id}'>{call.from_user.id}</a>"
        
        admin_message = f"""🆕 <b>طلب شراء VIP جديد</b>

👤 <b>المستخدم:</b> {user_link}
🆔 <b>الآيدي:</b> {user_id_link}
📞 <b>رابط التواصل:</b> <a href='tg://user?id={call.from_user.id}'>اضغط للتواصل</a>

💎 <b>النوع:</b> {vip_name} VIP
💰 <b>السعر:</b> {vip_price} USDT

💵 <b>رصيده الحالي:</b> {user['balance']:.2f} USDT
👥 <b>إحالاته:</b> {user['referral_count']}"""
        
        try:
            bot.send_message(YOUR_USER_ID, admin_message)
        except Exception as e:
            print(f"❌ Failed to send admin notification: {e}")
        
        message_text = f"""✅ <b>تم إرسال طلب شراء {vip_name} VIP بنجاح!</b>

💰 <b>السعر:</b> {vip_price} USDT
📞 <b>سيقوم المسؤول بالتواصل معك خلال 24 ساعة</b>

🔗 <b>للتواصل السريع:</b>
يمكنك مراسلة المسؤول مباشرة على @Trust_wallet_Support_4

شكراً لثقتك بنا! 🌟""" if lang == 'ar' else f"""✅ <b>{vip_name} VIP purchase request sent successfully!</b>

💰 <b>Price:</b> {vip_price} USDT
📞 <b>Admin will contact you within 24 hours</b>

🔗 <b>For fast contact:</b>
You can message admin directly at @Trust_wallet_Support_4

Thank you for your trust! 🌟"""
        
        bot.send_message(call.from_user.id, message_text)
        bot.answer_callback_query(call.id, f"✅ تم إرسال الطلب للمسؤول" if lang == 'ar' else f"✅ Request sent to admin")
        
    except Exception as e:
        print(f"❌ VIP purchase error: {e}")

# 💰 نظام السحب
@bot.callback_query_handler(func=lambda call: call.data == "withdraw")
def handle_withdraw(call):
    try:
        user = get_user(call.from_user.id)
        days_registered, days_remaining = get_membership_days(call.from_user.id)
        lang = get_user_language(call.from_user.id)
        
        if not user.get('has_deposit', 0):
            withdraw_text = f"""❌ <b>غير مؤهل للسحب</b>

📅 <b>مدة العضوية:</b> {days_registered}/10 أيام

<b>💰 الشروط المطلوبة للسحب:</b>
1. ✅ إيداع أولي (10 USDT)
2. ✅ رصيد 150 USDT  
3. ✅ 25 إحالة جديدة
4. ✅ 10 أيام عضوية

<b>💳 لبدء الإيداع، اضغط زر الإيداع في القائمة الرئيسية</b>""" if lang == 'ar' else f"""❌ <b>Not eligible for withdrawal</b>

📅 <b>Membership:</b> {days_registered}/10 days

<b>💰 Required conditions:</b>
1. ✅ Initial deposit (10 USDT)
2. ✅ 150 USDT balance  
3. ✅ 25 new referrals
4. ✅ 10 days membership

<b>💳 To start deposit, click deposit in main menu</b>"""
            
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("💳 الانتقال للإيداع" if lang == 'ar' else "💳 Go to Deposit", callback_data="deposit"))
            keyboard.add(InlineKeyboardButton("🔙 رجوع" if lang == 'ar' else "🔙 Back", callback_data="back_to_profile"))
        
        elif not can_withdraw(user):
            withdraw_text = f"""❌ <b>غير مؤهل للسحب بعد</b>

📅 <b>مدة العضوية:</b> {days_registered}/10 أيام ({days_remaining} يوم متبقي)

<b>📊 تقدمك نحو الشروط:</b>
• ✓ إيداع مفعل
• {'✓' if user['balance'] >= 150 else '✗'} رصيد 150 USDT ({user['balance']:.1f}/150)
• {'✓' if user['new_referrals'] >= 25 else '✗'} 25 إحالة جديدة ({user['new_referrals']}/25)
• {'✓' if days_registered >= 10 else '✗'} 10 أيام عضوية ({days_registered}/10)

<b>🎯 استكمل الشروط المتبقية لتصبح مؤهلاً للسحب</b>""" if lang == 'ar' else f"""❌ <b>Not eligible for withdrawal yet</b>

📅 <b>Membership:</b> {days_registered}/10 days ({days_remaining} days left)

<b>📊 Your progress:</b>
• ✓ Deposit activated
• {'✓' if user['balance'] >= 150 else '✗'} 150 USDT balance ({user['balance']:.1f}/150)
• {'✓' if user['new_referrals'] >= 25 else '✗'} 25 new referrals ({user['new_referrals']}/25)
• {'✓' if days_registered >= 10 else '✗'} 10 days membership ({days_registered}/10)

<b>🎯 Complete remaining conditions to become eligible</b>"""
            
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("👥 زيادة الإحالات" if lang == 'ar' else "👥 Increase Referrals", callback_data="referral"))
            keyboard.add(InlineKeyboardButton("🔙 رجوع" if lang == 'ar' else "🔙 Back", callback_data="back_to_profile"))
        
        else:
            withdraw_text = f"""💰 <b>نظام السحب</b>

✅ <b>أنت مؤهل للسحب بالكامل!</b>

📅 <b>مدة العضوية:</b> {days_registered} يوم

💰 <b>الرصيد المتاح:</b> {user['balance']:.1f} USDT

<b>📋 طريقة السحب:</b>
1. اختر مبلغ السحب أدناه
2. سيتم تحويلك للدعم الفني
3. قدم طلب السحب وسيتم معالجته خلال 24 ساعة

<b>🔒 التعامل شخصي مع الدعم لضمان أمان معاملاتك</b>""" if lang == 'ar' else f"""💰 <b>Withdrawal System</b>

✅ <b>You are fully eligible for withdrawal!</b>

📅 <b>Membership:</b> {days_registered} days

💰 <b>Available Balance:</b> {user['balance']:.1f} USDT

<b>📋 Withdrawal method:</b>
1. Choose withdrawal amount below
2. You will be redirected to support
3. Submit withdrawal request, processed within 24 hours

<b>🔒 Personal handling with support for transaction security</b>"""

            keyboard = InlineKeyboardMarkup(row_width=2)
            if lang == 'ar':
                keyboard.add(
                    InlineKeyboardButton("💰 سحب 150 USDT", callback_data="withdraw_150"),
                    InlineKeyboardButton("💰 سحب 300 USDT", callback_data="withdraw_300"),
                    InlineKeyboardButton("💰 سحب 500 USDT", callback_data="withdraw_500"),
                    InlineKeyboardButton("💰 سحب كل الرصيد", callback_data="withdraw_all")
                )
                keyboard.add(InlineKeyboardButton("🔙 رجوع", callback_data="back_to_profile"))
            else:
                keyboard.add(
                    InlineKeyboardButton("💰 Withdraw 150 USDT", callback_data="withdraw_150"),
                    InlineKeyboardButton("💰 Withdraw 300 USDT", callback_data="withdraw_300"),
                    InlineKeyboardButton("💰 Withdraw 500 USDT", callback_data="withdraw_500"),
                    InlineKeyboardButton("💰 Withdraw All Balance", callback_data="withdraw_all")
                )
                keyboard.add(InlineKeyboardButton("🔙 Back", callback_data="back_to_profile"))
        
        bot.edit_message_text(withdraw_text, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
    except Exception as e:
        print(f"❌ Withdraw error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('withdraw_'))
def handle_withdraw_request(call):
    try:
        user = get_user(call.from_user.id)
        days_registered, days_remaining = get_membership_days(call.from_user.id)
        lang = get_user_language(call.from_user.id)
        
        if not can_withdraw(user):
            if days_registered < 10:
                bot.answer_callback_query(call.id, f"❌ تحتاج {days_remaining} أيام إضافية للسحب!" if lang == 'ar' else f"❌ You need {days_remaining} more days for withdrawal!", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "❌ لست مؤهلاً للسحب بعد! تحقق من الشروط." if lang == 'ar' else "❌ You are not eligible for withdrawal yet! Check the conditions.", show_alert=True)
            return
        
        withdraw_type = call.data.replace('withdraw_', '')
        amount = 150.0 if withdraw_type == '150' else 300.0 if withdraw_type == '300' else 500.0 if withdraw_type == '500' else user['balance']
        
        if user['balance'] < amount:
            bot.answer_callback_query(call.id, f"❌ رصيدك غير كافي! الرصيد: {user['balance']:.1f} USDT" if lang == 'ar' else f"❌ Your balance is insufficient! Balance: {user['balance']:.1f} USDT", show_alert=True)
            return
        
        user_link = f"<a href='tg://user?id={call.from_user.id}'>{user['first_name'] or 'مستخدم'}</a>"
        user_id_link = f"<a href='tg://user?id={call.from_user.id}'>{call.from_user.id}</a>"
        
        admin_message = f"""🆕 <b>طلب سحب جديد</b>

👤 <b>المستخدم:</b> {user_link}
🆔 <b>الآيدي:</b> {user_id_link}
📞 <b>رابط التواصل:</b> <a href='tg://user?id={call.from_user.id}'>اضغط للتواصل</a>

💰 <b>المبلغ:</b> {amount:.1f} USDT
📅 <b>مدة العضوية:</b> {days_registered} يوم
👥 <b>الإحالات:</b> {user['new_referrals']}/25

💵 <b>رصيده الكلي:</b> {user['balance']:.1f} USDT
💎 <b>إجمالي أرباحه:</b> {user['total_earnings']:.1f} USDT"""
        
        try:
            bot.send_message(YOUR_USER_ID, admin_message)
        except Exception as e:
            print(f"❌ Failed to send admin notification: {e}")
        
        confirmation_text = f"""✅ <b>تم إرسال طلب السحب بنجاح!</b>

💰 <b>المبلغ:</b> {amount:.1f} USDT
📅 <b>مدة العضوية:</b> {days_registered} يوم
👥 <b>الإحالات:</b> {user['new_referrals']}/25

<b>📞 سيقوم الدعم الفني بالتواصل معك خلال 24 ساعة</b>

<b>🔗 للتواصل السريع:</b>
يمكنك مراسلة الدعم مباشرة على @Trust_wallet_Support_4

<b>🔒 لضمان أمان معاملاتك، سيتم التعامل مع طلبك شخصياً عبر الدعم الفني</b>

شكراً لاستخدامك خدماتنا! 🌟""" if lang == 'ar' else f"""✅ <b>Withdrawal request sent successfully!</b>

💰 <b>Amount:</b> {amount:.1f} USDT
📅 <b>Membership:</b> {days_registered} days
👥 <b>Referrals:</b> {user['new_referrals']}/25

<b>📞 Technical support will contact you within 24 hours</b>

<b>🔗 For fast contact:</b>
You can message support directly at @Trust_wallet_Support_4

<b>🔒 To ensure transaction security, your request will be handled personally by support</b>

Thank you for using our services! 🌟"""

        bot.send_message(call.from_user.id, confirmation_text)
        bot.answer_callback_query(call.id, f"✅ تم إرسال طلب سحب {amount:.1f} USDT للدعم" if lang == 'ar' else f"✅ Withdrawal request for {amount:.1f} USDT sent to support", show_alert=True)
        
    except Exception as e:
        print(f"❌ Withdraw request error: {e}")

# 💳 نظام الإيداع
@bot.callback_query_handler(func=lambda call: call.data == "deposit")
def handle_deposit(call):
    try:
        lang = get_user_language(call.from_user.id)
        
        deposit_text = """💳 <b>نظام الإيداع</b>

<b>📊 لماذا تحتاج للإيداع؟</b>
• تفعيل خاصية السحب
• زيادة فرص الربح
• وصول أسرع للأرباح

💰 <b>الحد الأدنى للإيداع:</b> 10 USDT

<b>🚀 لإجراء الإيداع:</b>
1. اضغط على زر 'طلب إيداع' أدناه
2. سيتم إرسال طلبك للمسؤول
3. سيتواصل معك المسؤول خلال 24 ساعة
4. أرسل مبلغ الإيداع للمسؤول

<b>✅ بعد الإيداع ستصبح مؤهلاً ل:</b>
• سحب الأرباح
• مزايا إضافية
• دعم متميز""" if lang == 'ar' else """💳 <b>Deposit System</b>

<b>📊 Why do you need to deposit?</b>
• Activate withdrawal feature
• Increase profit opportunities
• Faster access to earnings

💰 <b>Minimum deposit:</b> 10 USDT

<b>🚀 To make a deposit:</b>
1. Click 'Request Deposit' below
2. Your request will be sent to admin
3. Admin will contact you within 24 hours
4. Send deposit amount to admin

<b>✅ After deposit you will be eligible for:</b>
• Earnings withdrawal
• Additional benefits
• Premium support"""
        
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("📥 طلب إيداع" if lang == 'ar' else "📥 Request Deposit", callback_data="request_deposit"))
        keyboard.add(InlineKeyboardButton("🔙 رجوع" if lang == 'ar' else "🔙 Back", callback_data="back_to_profile"))
        
        bot.edit_message_text(deposit_text, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
    except Exception as e:
        print(f"❌ Deposit error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "request_deposit")
def handle_request_deposit(call):
    try:
        user = get_user(call.from_user.id)
        lang = get_user_language(call.from_user.id)
        
        user_link = f"<a href='tg://user?id={call.from_user.id}'>{user['first_name'] or 'مستخدم'}</a>"
        user_id_link = f"<a href='tg://user?id={call.from_user.id}'>{call.from_user.id}</a>"
        
        admin_message = f"""🆕 <b>طلب إيداع جديد</b>

👤 <b>المستخدم:</b> {user_link}
🆔 <b>الآيدي:</b> {user_id_link}
📞 <b>رابط التواصل:</b> <a href='tg://user?id={call.from_user.id}'>اضغط للتواصل</a>

💰 <b>الحد الأدنى:</b> 10 USDT
💵 <b>رصيده الحالي:</b> {user['balance']:.1f} USDT
👥 <b>إحالاته:</b> {user['referral_count']}
📅 <b>مدة العضوية:</b> {get_membership_days(call.from_user.id)[0]} يوم"""
        
        try:
            bot.send_message(YOUR_USER_ID, admin_message)
        except Exception as e:
            print(f"❌ Failed to send admin notification: {e}")
        
        message_text = """✅ <b>تم إرسال طلب الإيداع بنجاح!</b>

💰 <b>الحد الأدنى للإيداع: 10 USDT</b>
📞 <b>سيقوم المسؤول بالتواصل معك خلال 24 ساعة</b>

🔗 <b>للتواصل السريع:</b>
يمكنك مراسلة المسؤول مباشرة على @Trust_wallet_Support_4

شكراً لثقتك بنا! 🌟""" if lang == 'ar' else """✅ <b>Deposit request sent successfully!</b>

💰 <b>Minimum deposit: 10 USDT</b>
📞 <b>Admin will contact you within 24 hours</b>

🔗 <b>For fast contact:</b>
You can message admin directly at @Trust_wallet_Support_4

Thank you for your trust! 🌟"""
        
        bot.send_message(call.from_user.id, message_text)
        bot.answer_callback_query(call.id, "✅ تم إرسال طلب الإيداع للمسؤول" if lang == 'ar' else "✅ Deposit request sent to admin")
    except Exception as e:
        print(f"❌ Deposit request error: {e}")

# 🛠️ الأوامر الإدارية
@bot.message_handler(commands=['quickadd'])
def handle_quickadd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ <b>ليس لديك صلاحية!</b>")
        return
    try:
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "📝 <b>استخدام:</b> <code>/quickadd [user_id] [amount]</code>")
            return
        target_user_id, amount = parts[1], float(parts[2])
        user = get_user(target_user_id)
        if not user:
            bot.reply_to(message, "❌ <b>المستخدم غير موجود!</b>")
            return
        new_balance = user['balance'] + amount
        if update_user(target_user_id, balance=new_balance, total_earnings=user['total_earnings'] + amount):
            bot.reply_to(message, f"✅ <b>تم إضافة {amount} USDT للمستخدم {target_user_id}</b>\n💰 <b>الرصيد الجديد:</b> {new_balance:.2f} USDT")
        else:
            bot.reply_to(message, "❌ <b>فشل في إضافة الرصيد!</b>")
    except Exception as e:
        bot.reply_to(message, f"❌ <b>خطأ:</b> {e}")

# ... (جميع الأوامر الإدارية الأخرى تبقى كما هي)

# =============================================
# 🔧 نظام السيرفر والويب هوك
# =============================================

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        json_data = request.get_json()
        update = telebot.types.Update.de_json(json_data)
        bot.process_new_updates([update])
        return 'OK'
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return 'OK'

@app.route('/')
def home():
    return "🤖 البوت شغال - " + time.strftime("%Y-%m-%d %H:%M:%S")

@app.route('/health')
def health():
    return "✅ البوت بصحة جيدة"

@app.route('/ping')
def ping():
    return "🏓 Pong - " + time.strftime("%H:%M:%S")

@app.route('/set_webhook', methods=['GET'])
def set_webhook_manual():
    try:
        bot.remove_webhook()
        time.sleep(2)
        webhook_url = "https://usdt-telegram-bot-1-z7op.onrender.com/webhook"
        result = bot.set_webhook(url=webhook_url)
        return f"✅ تم تعيين الويب هوك!<br>الرابط: {webhook_url}<br>النتيجة: {result}"
    except Exception as e:
        return f"❌ خطأ: {str(e)}"

@app.route('/test')
def test():
    return "✅ البوت شغال تمام! - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def keep_alive():
    while True:
        try:
            response = requests.get('https://usdt-telegram-bot-1-z7op.onrender.com/ping', timeout=10)
            if response.status_code == 200:
                print(f"✅ Keep-alive - {time.strftime('%H:%M:%S')}")
            else:
                print(f"⚠️ Keep-alive status: {response.status_code}")
        except Exception as e:
            print(f"❌ Keep-alive failed: {e}")
        time.sleep(300)

def setup_webhook():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            time.sleep(15)
            print(f"🔄 جاري تعيين الويب هوك (المحاولة {attempt + 1})...")
            
            bot.remove_webhook()
            time.sleep(2)
            
            webhook_url = "https://usdt-telegram-bot-1-z7op.onrender.com/webhook"
            result = bot.set_webhook(url=webhook_url)
            
            webhook_info = bot.get_webhook_info()
            print(f"✅ تم تعيين الويب هوك: {webhook_url}")
            print(f"📊 معلومات الويب هوك: {webhook_info}")
            return True
            
        except Exception as e:
            print(f"❌ فشل تعيين الويب هوك (المحاولة {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
    return False

if __name__ == '__main__':
    print("🚀 بدء تشغيل البوت...")
    
    keep_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_thread.start()
    
    webhook_success = setup_webhook()
    if not webhook_success:
        print("⚠️ تشغيل بدون ويب هوك - استخدام polling")
        bot.remove_webhook()
        time.sleep(2)
        bot.polling(none_stop=True)
    else:
        port = int(os.environ.get("PORT", 8080))
        app.run(host='0.0.0.0', port=port, debug=False)
