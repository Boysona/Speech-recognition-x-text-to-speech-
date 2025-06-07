import os
import re
import uuid
import shutil
import logging
import requests
import telebot
import json
from flask import Flask, request, abort
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import imageio_ffmpeg as ffmpeg
from pydub import AudioSegment
import threading
import time
import subprocess

# --- NEW: Import SpeechRecognition for speech-to-text ---
import speech_recognition as sr

# --- NEW: Import MSSpeech for Text-to-Speech ---
from msspeech import MSSpeech, MSSpeechError

# Configure logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- BOT CONFIGURATION (Using Media Transcriber Bot's Token and Webhook) ---
TOKEN = "7790991731:AAH4rt8He_PABDa28xgcY3dIQwmtuQD-qiM"  # Bedel token-ka haddii loo baahdo
ADMIN_ID = 5978150981  # Bedel ID-gaaga haddii loo baahdo
# Webhook URL - Bedel URL-gaaga Render
WEBHOOK_URL = "https://speech-recognition-9cyh.onrender.com"

# --- REQUIRED CHANNEL CONFIGURATION ---
REQUIRED_CHANNEL = "@transcriberbo"  # Bedel kanaalka haddii loo baahdo

bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

# Download directory (isticmaalo uun inta loogu baahdo WAV)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- User tracking files ---
users_file = 'users.json'
user_data = {}
if os.path.exists(users_file):
    with open(users_file, 'r') as f:
        try:
            user_data = json.load(f)
        except json.JSONDecodeError:
            user_data = {}

# User-specific language settings for translate/summarize
user_language_settings_file = 'user_language_settings.json'
user_language_settings = {}
if os.path.exists(user_language_settings_file):
    with open(user_language_settings_file, 'r') as f:
        try:
            user_language_settings = json.load(f)
        except json.JSONDecodeError:
            user_language_settings = {}

# User-specific media language settings for speech recognition
user_media_language_settings_file = 'user_media_language_settings.json'
user_media_language_settings = {}
if os.path.exists(user_media_language_settings_file):
    with open(user_media_language_settings_file, 'r') as f:
        try:
            user_media_language_settings = json.load(f)
        except json.JSONDecodeError:
            user_media_language_settings = {}

# --- NEW: User transcription counts for delayed subscription ---
user_transcription_counts_file = 'user_transcription_counts.json'
user_transcription_counts = {}
if os.path.exists(user_transcription_counts_file):
    with open(user_transcription_counts_file, 'r') as f:
        try:
            user_transcription_counts = json.load(f)
        except json.JSONDecodeError:
            user_transcription_counts = {}

def save_user_transcription_counts():
    with open(user_transcription_counts_file, 'w') as f:
        json.dump(user_transcription_counts, f, indent=4)

# --- NEW: TTS User settings and Voices ---
tts_users_db = 'tts_users.json'  # DB u gaar ah TTS
tts_users = {}
if os.path.exists(tts_users_db):
    try:
        with open(tts_users_db, "r") as f:
            tts_users = json.load(f)
    except json.JSONDecodeError:
        tts_users = {}

# --- NEW: User state for Text-to-Speech input mode ---
# {user_id: "en-US-AriaNeural" (chosen voice) ama None (ma jiro TTS mode)}
user_tts_mode = {}

# Group voices by language for better organization - Sida hore u qoran
TTS_VOICES_BY_LANGUAGE = {
    "English 🇬🇧": [
        "en-US-AriaNeural", "en-US-GuyNeural", "en-US-JennyNeural", "en-US-DavisNeural",
        "en-GB-LibbyNeural", "en-GB-RyanNeural", "en-GB-MiaNeural", "en-GB-ThomasNeural",
        "en-AU-NatashaNeural", "en-AU-WilliamNeural", "en-CA-LindaNeural", "en-CA-ClaraNeural",
        "en-IE-EmilyNeural", "en-IE-ConnorNeural", "en-IN-NeerjaNeural", "en-IN-PrabhatNeural"
    ],
    "Arabic 🇸🇦": [
        "ar-SA-HamedNeural", "ar-SA-ZariyahNeural", "ar-EG-SalmaNeural", "ar-EG-ShakirNeural",
        "ar-DZ-AminaNeural", "ar-DZ-IsmaelNeural", "ar-BH-LailaNeural", "ar-BH-AliNeural",
        "ar-IQ-RanaNeural", "ar-IQ-BasselNeural", "ar-KW-FahedNeural", "ar-KW-NouraNeural",
        "ar-OM-AishaNeural", "ar-OM-SamirNeural", "ar-QA-MoazNeural", "ar-QA-ZainabNeural",
        "ar-SY-AmiraNeural", "ar-SY-LaithNeural", "ar-AE-FatimaNeural", "ar-AE-HamdanNeural",
        "ar-YE-HamdanNeural", "ar-YE-SarimNeural"
    ],
    "Spanish 🇪🇸": [
        "es-ES-AlvaroNeural", "es-ES-ElviraNeural", "es-MX-DaliaNeural", "es-MX-JorgeNeural",
        "es-AR-ElenaNeural", "es-AR-TomasNeural", "es-CO-SalomeNeural", "es-CO-GonzaloNeural",
        "es-US-PalomaNeural", "es-US-JuanNeural", "es-CL-LorenzoNeural", "es-CL-CatalinaNeural",
        "es-PE-CamilaNeural", "es-PE-DiegoNeural", "es-VE-PaolaNeural", "es-VE-SebastianNeural",
        "es-CR-MariaNeural", "es-CR-JuanNeural",
        "es-DO-RamonaNeural", "es-DO-AntonioNeural"
    ],
    "Hindi 🇮🇳": [
        "hi-IN-SwaraNeural", "hi-IN-MadhurNeural"
    ],
    "French 🇫🇷": [
        "fr-FR-DeniseNeural", "fr-FR-HenriNeural", "fr-CA-SylvieNeural", "fr-CA-JeanNeural",
        "fr-CH-ArianeNeural", "fr-CH-FabriceNeural", "fr-CH-CharlineNeural", "fr-BE-CamilleNeural"
    ],
    "German 🇩🇪": [
        "de-DE-KatjaNeural", "de-DE-ConradNeural", "de-CH-LeniNeural", "de-CH-JanNeural",
        "de-AT-IngridNeural", "de-AT-JonasNeural"
    ],
    "Chinese 🇨🇳": [
        "zh-CN-XiaoxiaoNeural", "zh-CN-YunyangNeural", "zh-CN-YunjianNeural", "zh-CN-XiaoyunNeural",
        "zh-TW-HsiaoChenNeural", "zh-TW-YunJheNeural", "zh-HK-HiuMaanNeural", "zh-HK-WanLungNeural",
        "zh-SG-XiaoMinNeural", "zh-SG-YunJianNeural"
    ],
    "Japanese 🇯🇵": [
        "ja-JP-NanamiNeural", "ja-JP-KeitaNeural", "ja-JP-MayuNeural", "ja-JP-DaichiNeural"
    ],
    "Portuguese 🇧🇷": [
        "pt-BR-FranciscaNeural", "pt-BR-AntonioNeural", "pt-PT-RaquelNeural", "pt-PT-DuarteNeural"
    ],
    "Russian 🇷🇺": [
        "ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural", "ru-RU-LarisaNeural", "ru-RU-MaximNeural"
    ],
    "Turkish 🇹🇷": [
        "tr-TR-EmelNeural", "tr-TR-AhmetNeural"
    ],
    "Korean 🇰🇷": [
        "ko-KR-SunHiNeural", "ko-KR-InJoonNeural"
    ],
    "Italian 🇮🇹": [
        "it-IT-ElsaNeural", "it-IT-DiegoNeural"
    ],
    "Indonesian 🇮🇩": [
        "id-ID-GadisNeural", "id-ID-ArdiNeural"
    ],
    "Vietnamese 🇻🇳": [
        "vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"
    ],
    "Thai 🇹🇭": [
        "th-TH-PremwadeeNeural", "th-TH-NiwatNeural"
    ],
    "Dutch 🇳🇱": [
        "nl-NL-ColetteNeural", "nl-NL-MaartenNeural"
    ],
    "Polish 🇵🇱": [
        "pl-PL-ZofiaNeural", "pl-PL-MarekNeural"
    ],
    "Swedish 🇸🇪": [
        "sv-SE-SofieNeural", "sv-SE-MattiasNeural"
    ],
    "Filipino 🇵🇭": [
        "fil-PH-BlessicaNeural", "fil-PH-AngeloNeural"
    ],
    "Greek 🇬🇷": [
        "el-GR-AthinaNeural", "el-GR-NestorasNeural"
    ],
    "Hebrew 🇮🇱": [
        "he-IL-AvriNeural", "he-IL-HilaNeural"
    ],
    "Hungarian 🇭🇺": [
        "hu-HU-NoemiNeural", "hu-HU-AndrasNeural"
    ],
    "Czech 🇨🇿": [
        "cs-CZ-VlastaNeural", "cs-CZ-AntoninNeural"
    ],
    "Danish 🇩🇰": [
        "da-DK-ChristelNeural", "da-DK-JeppeNeural"
    ],
    "Finnish 🇫🇮": [
        "fi-FI-SelmaNeural", "fi-FI-HarriNeural"
    ],
    "Norwegian 🇳🇴": [
        "nb-NO-PernilleNeural", "nb-NO-FinnNeural"
    ],
    "Romanian 🇷🇴": [
        "ro-RO-AlinaNeural", "ro-RO-EmilNeural"
    ],
    "Slovak 🇸🇰": [
        "sk-SK-LukasNeural", "sk-SK-ViktoriaNeural"
    ],
    "Ukrainian 🇺🇦": [
        "uk-UA-PolinaNeural", "uk-UA-OstapNeural"
    ],
    "Malay 🇲🇾": [
        "ms-MY-YasminNeural", "ms-MY-OsmanNeural"
    ],
    "Bengali 🇧🇩": [
        "bn-BD-NabanitaNeural", "bn-BD-BasharNeural"
    ],
    "Tamil 🇮🇳": [
        "ta-IN-PallaviNeural", "ta-IN-ValluvarNeural"
    ],
    "Telugu 🇮🇳": [
        "te-IN-ShrutiNeural", "te-IN-RagavNeural"
    ],
    "Kannada 🇮🇳": [
        "kn-IN-SapnaNeural", "kn-IN-GaneshNeural"
    ],
    "Malayalam 🇮🇳": [
        "ml-IN-SobhanaNeural", "ml-IN-MidhunNeural"
    ],
    "Gujarati 🇮🇳": [
        "gu-IN-DhwaniNeural", "gu-IN-AvinashNeural"
    ],
    "Marathi 🇮🇳": [
        "mr-IN-AarohiNeural", "mr-IN-ManoharNeural"
    ],
    "Urdu 🇵🇰": [
        "ur-PK-AsmaNeural", "ur-PK-FaizanNeural"
    ],
    "Nepali 🇳🇵": [
        "ne-NP-SaritaNeural", "ne-NP-AbhisekhNeural"
    ],
    "Sinhala 🇱🇰": [
        "si-LK-SameeraNeural", "si-LK-ThiliniNeural"
    ],
    "Khmer 🇰🇭": [
        "km-KH-SreymomNeural", "km-KH-PannNeural"
    ],
    "Lao 🇱🇦": [
        "lo-LA-ChanthavongNeural", "lo-LA-KeomanyNeural"
    ],
    "Myanmar 🇲🇲": [
        "my-MM-NilarNeural", "my-MM-ThihaNeural"
    ],
    "Georgian 🇬🇪": [
        "ka-GE-EkaNeural", "ka-GE-GiorgiNeural"
    ],
    "Armenian 🇦🇲": [
        "hy-AM-AnahitNeural", "hy-AM-AraratNeural"
    ],
    "Azerbaijani 🇦🇿": [
        "az-AZ-BabekNeural", "az-AZ-BanuNeural"
    ],
    "Kazakh 🇰🇿": [
        "kk-KZ-AigulNeural", "kk-KZ-NurzhanNeural"
    ],
    "Uzbek 🇺🇿": [
        "uz-UZ-MadinaNeural", "uz-UZ-SuhrobNeural"
    ],
    "Serbian 🇷🇸": [
        "sr-RS-NikolaNeural", "sr-RS-SophieNeural"
    ],
    "Croatian 🇭🇷": [
        "hr-HR-GabrijelaNeural", "hr-HR-SreckoNeural"
    ],
    "Slovenian 🇸🇮": [
        "sl-SI-PetraNeural", "sl-SI-RokNeural"
    ],
    "Latvian 🇱🇻": [
        "lv-LV-EveritaNeural", "lv-LV-AnsisNeural"
    ],
    "Lithuanian 🇱🇹": [
        "lt-LT-OnaNeural", "lt-LT-LeonasNeural"
    ],
    "Estonian 🇪🇪": [
        "et-EE-LiisNeural", "et-EE-ErkiNeural"
    ],
    "Amharic 🇪🇹": [
        "am-ET-MekdesNeural", "am-ET-AbebeNeural"
    ],
    "Swahili 🇰🇪": [
        "sw-KE-ZuriNeural", "sw-KE-RafikiNeural"
    ],
    "Zulu 🇿🇦": [
        "zu-ZA-ThandoNeural", "zu-ZA-ThembaNeural"
    ],
    "Xhosa 🇿🇦": [
        "xh-ZA-NomusaNeural", "xh-ZA-DumisaNeural"
    ],
    "Afrikaans 🇿🇦": [
        "af-ZA-AdriNeural", "af-ZA-WillemNeural"
    ],
    "Somali 🇸🇴": [  # Ku dar Somali qaybtaan
        "so-SO-UbaxNeural", "so-SO-MuuseNeural",
    ],
}
# --- End of NEW TTS Voice Config ---

def save_tts_users():
    with open(tts_users_db, "w") as f:
        json.dump(tts_users, f, indent=2)

def get_tts_user_voice(uid):
    return tts_users.get(str(uid), "en-US-AriaNeural")

# In-memory chat history and transcription store
user_memory = {}
user_transcriptions = {}
processing_message_ids = {}  # To keep track of messages for which typing action is active

# Statistics counters (global variables)
total_files_processed = 0
total_audio_files = 0
total_voice_clips = 0
total_videos = 0
total_processing_time = 0
bot_start_time = datetime.now()

# Admin uptime message storage
admin_uptime_message = {}
admin_uptime_lock = threading.Lock()

GEMINI_API_KEY = "AIzaSyAto78yGVZobxOwPXnl8wCE9ZW8Do2R8HA"  # Bedel haddii loo baahdo

def ask_gemini(user_id, user_message):
    user_memory.setdefault(user_id, []).append({"role": "user", "text": user_message})
    history = user_memory[user_id][-10:]
    parts = [{"text": msg["text"]} for msg in history]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    resp = requests.post(url, headers={'Content-Type': 'application/json'}, json={"contents": [{"parts": parts}]})
    result = resp.json()
    if "candidates" in result:
        reply = result['candidates'][0]['content']['parts'][0]['text']
        user_memory[user_id].append({"role": "model", "text": reply})
        return reply
    return "Error: " + json.dumps(result)

FILE_SIZE_LIMIT = 20 * 1024 * 1024  # 20MB
admin_state = {}

def set_bot_info():
    commands = [
        telebot.types.BotCommand("start", "👋Get a welcome message and info"),
        telebot.types.BotCommand("status", "📊View Bot statistics"),
        telebot.types.BotCommand("language", "🌐Change preferred language for translate/summarize"),
        telebot.types.BotCommand("media_language", "📝Set language for media transcription"),
        telebot.types.BotCommand("text_to_speech", "🗣️Convert text to Ai voice"),
    ]
    bot.set_my_commands(commands)

    bot.set_my_short_description(
        "Got media files? Let this free bot transcribe, summarize, and translate them in seconds!"
    )

    bot.set_my_description(
        """This bot quickly transcribes voice messages, audio files, and videos using advanced AI, and can also convert text to speech!

     🔥Enjoy free usage and start now!👌🏻"""
    )

def update_user_activity(user_id):
    user_data[str(user_id)] = datetime.now().isoformat()
    save_user_data()

# Function to keep sending 'typing' action
def keep_typing(chat_id, stop_event):
    while not stop_event.is_set():
        try:
            bot.send_chat_action(chat_id, 'typing')
            time.sleep(4)
        except Exception as e:
            logging.error(f"Error sending typing action: {e}")
            break

# Function to keep sending 'recording' action
def keep_recording(chat_id, stop_event):
    while not stop_event.is_set():
        try:
            bot.send_chat_action(chat_id, 'record_audio')
            time.sleep(4)
        except Exception as e:
            logging.error(f"Error sending record_audio action: {e}")
            break

# Function to update uptime message
def update_uptime_message(chat_id, message_id):
    """
    Live-update the admin uptime message every second, showing days, hours, minutes and seconds.
    """
    while True:
        try:
            elapsed = datetime.now() - bot_start_time
            total_seconds = int(elapsed.total_seconds())
            days, rem = divmod(total_seconds, 86400)
            hours, rem = divmod(rem, 3600)
            minutes, seconds = divmod(rem, 60)

            uptime_text = (
                f"**Bot Uptime:**\n"
                f"{days} days, {hours:02d} hours, {minutes:02d} minutes, {seconds:02d} seconds"
            )

            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=uptime_text,
                parse_mode="Markdown"
            )
            time.sleep(1)

        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                logging.error(f"Error updating uptime message: {e}")
            break
        except Exception as e:
            logging.error(f"Unexpected error in uptime thread: {e}")
            break

# --- NEW: Check Channel Subscription with delayed enforcement ---
def check_subscription(user_id):
    if not REQUIRED_CHANNEL:
        return True  # If no required channel is set, always return True

    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Error checking subscription for user {user_id} in {REQUIRED_CHANNEL}: {e}")
        return False

def send_subscription_message(chat_id):
    if not REQUIRED_CHANNEL:
        return  # Do nothing if no required channel is set

    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(
        telebot.types.InlineKeyboardButton("Click here to join the channel", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}")
    )
    bot.send_message(
        chat_id,
        "😓Sorry …\n🔰 First join the channel @transcriberbo‼️ After joining, come back to continue using the bot.",
        reply_markup=markup,
        disable_web_page_preview=True
    )

def requires_subscription(user_id):
    """
    Return True if we need to enforce subscription: i.e., user has completed 5 or more transcriptions.
    """
    return user_transcription_counts.get(str(user_id), 0) >= 5

@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = str(message.from_user.id)
    update_user_activity(message.from_user.id)

    # Always add user to user_data on start
    if user_id not in user_data:
        user_data[user_id] = datetime.now().isoformat()
        save_user_data()

    # --- MODIFIED: Ensure TTS mode is OFF on start ---
    user_tts_mode[user_id] = None

    if message.from_user.id == ADMIN_ID:
        keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("Send Broadcast", "Total Users", "/status")
        sent_message = bot.send_message(message.chat.id, "Admin Panel and Uptime (updating live)...", reply_markup=keyboard)

        with admin_uptime_lock:
            if admin_uptime_message.get(ADMIN_ID) and admin_uptime_message[ADMIN_ID].get('thread') and admin_uptime_message[ADMIN_ID]['thread'].is_alive():
                pass

            admin_uptime_message[ADMIN_ID] = {'message_id': sent_message.message_id, 'chat_id': message.chat.id}
            uptime_thread = threading.Thread(target=update_uptime_message, args=(message.chat.id, sent_message.message_id))
            uptime_thread.daemon = True
            uptime_thread.start()
            admin_uptime_message[ADMIN_ID]['thread'] = uptime_thread

    else:
        # --- MODIFIED: Delay subscription prompt until after 5 transcriptions ---
        if requires_subscription(message.from_user.id) and not check_subscription(message.from_user.id):
            send_subscription_message(message.chat.id)
            return
        # --- End delayed subscription check ---

        # --- MODIFIED: Immediately prompt for media language selection on /start ---
        user_tts_mode[user_id] = None
        markup = generate_language_keyboard("set_media_lang")
        bot.send_message(
            message.chat.id,
            "Please choose the language of the audio files using the below buttons.",
            reply_markup=markup
        )

@bot.message_handler(commands=['help'])
def help_handler(message):
    user_id = str(message.from_user.id)
    update_user_activity(user_id)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(message.from_user.id) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF on help command ---
    user_tts_mode[user_id] = None

    help_text = (
        """ℹ️ Sida loo isticmaalo bot-kan:

Bot-kan waxa uu si **degdeg ah** u qoraa waxa codka ku jira, waxa war ka soo saarayaa, waxa u tarjumi karaa, sidoo kale waxa ugu beddeli karaa qoraalka cod!

1.  **Soo dir File si loogu qoro (transcribe):**
   * Soo dir voice message, audio file, video note, ama video file (e.g. .mp4).
   * **Xasuusnow**, ka hor inta aadan soo dirin media-ga, isticmaal `/media_language` si aad ii tilmaamto luqadda codka. Tani waxay hubinaysaa in qoraalka uu sax noqdo.
   * Bot-ku wuu ka soo saarayaa qoraalka, kadibna wuu kuu soo diri doonaa. Haddii qoraalka dheer yahay, wuu kuugu soo diri doonaa file text ah.
   * Markaad hesho qoraalka, waxaad heli doontaa badhamo inline ah oo leh **Translate** ama **Summarize**.

2.  **Beddel Qoraal (tekst) Cod (speech):**
   * Isticmaal amarka `/text_to_speech` si aad u doorato luqadda iyo codka.
   * Markaad doorato codka, waxaad u soo diri kartaa qoraal kasta, bot-kuna wuu kuu soo celin doonaa cod ahaan.

3.  **Amarka kale:**
   * `/start`: Hel soo dhawayn iyo faahfaahin. (Admin-ku wuxuu arkayaa waqtiga socda bot-ka)
   * `/status`: Arag tirakoobyada isticmaalka iyo howlaha bot-ka.
   * `/help`: Tus tilmaanaha isticmaalka.
   * `/language`: Beddel luqadda aad rabto in qoraalada lagu turjumo/jadwallo.
   * `/media_language`: Dejiso luqadda codka ee file-kaaga. Tani waa mid muhiim ah.
   * `/text_to_speech`: Dooro luqad iyo cod si qoraalka loogu beddelo cod.

Ku raaxeyso qorista, tarjumaadda, soo koobidda, iyo beddelidda qoraalka codka si **fiican**, 
"""
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['privacy'])
def privacy_notice_handler(message):
    user_id = str(message.from_user.id)
    update_user_activity(user_id)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(message.from_user.id) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF on privacy command ---
    user_tts_mode[user_id] = None

    privacy_text = (
        """**Privacy Notice**

Xogtaada aad ayaan u ilaalinaa. Waa kan sida bot-kan u maareeyo xogtaada:

1.  **Xogta aan ka shaqeyno & Nolosheeda:**
   * **Media Files (Voice, Audio, Video):** Markaad soo dirto media, waxay si **kumeelgaar ah** loogu soo dejinayaa server-ka si **qoraal** loo geliyo. Si **xoogan** ayaanu u tirtirnaa marka qoraalku dhamaado. Ma maamulno ama ma kaydinno media-gaaga.
   * **Qoraalka codka:** Markaad qoraal u soo dirto TTS, waxaa loo geeyaa maktabadda Microsoft si cod loo sameeyo, kadibna si **kumeelgaar ah** ayaa loo tirtiraa. Ma kaydinno codka la sameeyay.
   * **Transcriptions:** Qoraalka laga soo saaro codka waxa uu ku jiri karaa **xusuusta uu bot-ku leeyahay** muddo gaaban. Tani waxay u ogolaaneysaa codsiyo xiga sida turjumaad ama soo koobin. Ma kaydinno si joogto ah, waxayna tirtirmaa **7 maalmood** gudahood ama marka bot-ku dib u bilaabo.
   * **User IDs:** Waxaa kaydsanaada Telegram User ID-gaaga. Tani waxay naga caawineysaa inaan xasuusanno doorashooyinka luqadda, iyo inaan fahanno isticmaalka guud. ID-gaaga lama xidhiidhin macluumaadkaaga kale ee gaarka ah.
   * **Luqadaha aad doorato:** Luqadaha aad doorato ee tarjumida/jadwalintu waxay ahaadaan kuwo kaydsan si mar kasta aadan u dooran.

2.  **Sida xogtaada loo isticmaalo:**
   * In laga caawiyo adeegyada bot-ka: qorista, turjumaadda, soo koobidda, iyo beddelidda qoraalka codka.
   * In aan kor u qaadno waxqabadka bot-ka iyo inaan fahamno tirakoobyada isticmaalka (tusaale, tirada faylasha guud).
   * In aan xasuusanno doorashooyinkaaga luqadda iyo codka TTS, si waayo-aragnimadaadu u fududaato.

3.  **Sida xogta loo wadaago:**
   * **Ma wadaagno** xogtaada shakhsiyeed, media-gaaga, ama qoraaladaada cid saddexaad.
   * Tarjumida, soo koobidda, qoraalka ayaa loo isticmaalaa Google Gemini API; Text-to-Speech waxay isticmaashaa Microsoft Cognitive Services. Xogtaada waa mid khaas ah intay ku jirto bot-keena.

4.  **Keydinta xogta:**
   * **Media files iyo codka la sameeyay:** Waxaa si **kumeelgaar ah** loo tiriyaa isla markiiba.
   * **Transcriptions:** Waxaa ku jira bot-ku muddo gaaban (7 maalmood) ka dibna waa la tiriyaa ama marka cusub la keeno.
   * **User IDs iyo doorashooyinka luqadda/codka TTS:** Waxaa lagu kaydiyaa si aan u xasuusanno. Haddii aad rabto in aan tirtirno doorashooyinkaaga, jooji inaad bot-ka isticmaasho ama la xiriir maamulaha bot-ka si gaar ah.

Adigoo isticmaalaya bot-kan, waxaad ogoshahay **in aan si ammaan ah u maamulno xogtaada** sida halkan ku xusan.

Haddii su’aalo ama walaac ku saabsan asturnaantaada aad qabto, fadlan la xiriir maamulaha bot-ka.
"""
    )
    bot.send_message(message.chat.id, privacy_text, parse_mode="Markdown")

@bot.message_handler(commands=['status'])
def status_handler(message):
    user_id = str(message.from_user.id)
    update_user_activity(user_id)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(message.from_user.id) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF on status command ---
    user_tts_mode[user_id] = None

    uptime = datetime.now() - bot_start_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    today = datetime.now().date()
    active_today = sum(
        1 for timestamp in user_data.values()
        if datetime.fromisoformat(timestamp).date() == today
    )

    total_proc_seconds = int(total_processing_time)
    proc_hours = total_proc_seconds // 3600
    proc_minutes = (total_proc_seconds % 3600) // 60
    proc_seconds = total_proc_seconds % 60

    text = (
        "📊 Bot Statistics\n\n"
        "🟢 **Bot Status: Online**\n"
        f"⏱️ The last time we updated the bot was : {days} days, {hours} hours, {minutes} minutes, {seconds} seconds ago\n\n"
        "👥 User Statistics\n"
        f"▫️ Total Users Today: {active_today}\n"
        f"▫️ Total Registered Users: {len(user_data)}\n\n"
        "⚙️ Processing Statistics\n"
        f"▫️ Total Files Processed: {total_files_processed}\n"
        f"▫️ Audio Files: {total_audio_files}\n"
        f"▫️ Voice Clips: {total_voice_clips}\n"
        f"▫️ Videos: {total_videos}\n"
        f"⏱️ Total Processing Time: {proc_hours} hours {proc_minutes} minutes {proc_seconds} seconds\n\n"
        "⸻\n\n"
        "Thanks for using our service! 🙌"
    )

    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "Total Users" and m.from_user.id == ADMIN_ID)
def total_users(message):
    bot.send_message(message.chat.id, f"Total registered users: {len(user_data)}")

@bot.message_handler(func=lambda m: m.text == "Send Broadcast" and m.from_user.id == ADMIN_ID)
def send_broadcast(message):
    admin_state[message.from_user.id] = 'awaiting_broadcast'
    bot.send_message(message.chat.id, "Send the broadcast message now:")

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and admin_state.get(m.from_user.id) == 'awaiting_broadcast',
    content_types=['text', 'photo', 'video', 'audio', 'document']
)
def broadcast_message(message):
    admin_state[message.from_user.id] = None
    success = fail = 0
    for uid_key in user_data:
        uid = uid_key
        try:
            bot.copy_message(uid, message.chat.id, message.message_id)
            success += 1
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"Failed to send broadcast to {uid}: {e}")
            fail += 1
    bot.send_message(
        message.chat.id,
        f"Broadcast complete.\nSuccessful: {success}\nFailed: {fail}"
    )

# ────────────────────────────────────────────────────────────────────────────────────────────
#   M E D I A   H A N D L I N G  (voice, audio, video, video_note, **document** as video)
# ────────────────────────────────────────────────────────────────────────────────────────────

@bot.message_handler(content_types=['voice', 'audio', 'video', 'video_note', 'document'])
def handle_file(message):
    uid = str(message.from_user.id)
    update_user_activity(message.from_user.id)

    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(message.from_user.id) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return
    # --- End delayed subscription check ---

    # Haddii user-ka uusan dooran luqadda media, weydiiso
    if uid not in user_media_language_settings:
        bot.send_message(
            message.chat.id,
            "⚠️ Fadlan marka hore dooro luqadda audio/video-ga adigoo isticmaalaya /media_language ka hor inta aadan file-ka dirin."
        )
        return

    # Doorasho file sax ah
    file_obj = None
    is_document_video = False
    if message.voice:
        file_obj = message.voice
    elif message.audio:
        file_obj = message.audio
    elif message.video:
        file_obj = message.video
    elif message.video_note:
        file_obj = message.video_note
    elif message.document:
        mime = message.document.mime_type or ""
        if mime.startswith("video/") or mime.startswith("audio/"):
            file_obj = message.document
            is_document_video = True
        else:
            bot.send_message(
                message.chat.id,
                "❌ Faylka aad soo dirtay ma aha audio/video la taageerayo. Fadlan soo dir voice message, audio file, video note, ama video file (e.g. .mp4)."
            )
            return

    if not file_obj:
        bot.send_message(
            message.chat.id,
            "❌ Fadlan kaliya soo dir voice message, audio file, video note, ama video file."
        )
        return

    # Hubi cabirka faylka
    size = file_obj.file_size
    if size and size > FILE_SIZE_LIMIT:
        bot.send_message(message.chat.id, "😓 Dhib malahan, faylka aad soo dirtay waa weyn yahay (ugu badnaan waa 20MB).")
        return

    # Daah-furid "👀" falcelin
    try:
        bot.set_message_reaction(
            chat_id=message.chat.id,
            message_id=message.message_id,
            reaction=[{'type': 'emoji', 'emoji': '👀'}]
        )
    except Exception as e:
        logging.error(f"Error setting reaction: {e}")

    # Bilow tilmaamaha typing
    stop_typing = threading.Event()
    typing_thread = threading.Thread(target=keep_typing, args=(message.chat.id, stop_typing))
    typing_thread.daemon = True
    typing_thread.start()
    processing_message_ids[message.chat.id] = stop_typing  # Kaydi si aan u joojino mar dambe

    try:
        # Guddigelinta faylka si thread kale
        threading.Thread(
            target=process_media_file,
            args=(message, stop_typing, is_document_video)
        ).start()
    except Exception as e:
        logging.error(f"Error initiating file processing: {e}")
        stop_typing.set()
        try:
            bot.set_message_reaction(
                chat_id=message.chat.id,
                message_id=message.message_id,
                reaction=[]
            )
        except Exception as remove_e:
            logging.error(f"Error removing reaction on early error: {remove_e}")
        bot.send_message(message.chat.id, "😓 Waa ka xun tahay, qalad ayaa dhacay. Fadlan mar kale isku day.")

def process_media_file(message, stop_typing, is_document_video):
    """
    Download faylka media (voice/audio/video/document),
    u beddel WAV, ka dibna isticmaal SpeechRecognition si qoraal loo diyaariyo,
    ugu dambayn natiijada u soo dir user-ka.
    """
    global total_files_processed, total_audio_files, total_voice_clips, total_videos, total_processing_time

    uid = str(message.from_user.id)

    # Sidoo kale hel file_obj mar kale
    if message.voice:
        file_obj = message.voice
    elif message.audio:
        file_obj = message.audio
    elif message.video:
        file_obj = message.video
    elif message.video_note:
        file_obj = message.video_note
    else:  # is_document_video == True
        file_obj = message.document

    local_temp_file = None
    wav_audio_path = None

    try:
        info = bot.get_file(file_obj.file_id)

        # Go'aami extension
        if message.voice or message.video_note:
            file_extension = ".ogg"
        elif message.document:
            _, ext = os.path.splitext(message.document.file_name or info.file_path)
            file_extension = ext if ext else os.path.splitext(info.file_path)[1]
        else:
            file_extension = os.path.splitext(info.file_path)[1]  # .mp3, .wav, .mp4, iwm.

        # Soo dejinta faylka si kumeelgaar ah FFmpeg loogu badalo
        local_temp_file = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4()}{file_extension}")
        data = bot.download_file(info.file_path)
        with open(local_temp_file, 'wb') as f:
            f.write(data)

        processing_start_time = datetime.now()

        # U beddel WAV 16kHz mono
        wav_audio_path = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4()}.wav")
        try:
            command = [
                ffmpeg.get_ffmpeg_exe(),
                '-i', local_temp_file,
                '-vn',  # No video stream
                '-acodec', 'pcm_s16le',  # PCM 16-bit little-endian
                '-ar', '16000',  # 16 kHz sample rate
                '-ac', '1',  # Mono audio
                wav_audio_path
            ]
            subprocess.run(command, check=True, capture_output=True)
            if not os.path.exists(wav_audio_path) or os.path.getsize(wav_audio_path) == 0:
                raise Exception("FFmpeg conversion failed or resulted in an empty file.")
        except subprocess.CalledProcessError as e:
            logging.error(f"FFmpeg conversion failed: {e.stdout.decode()} {e.stderr.decode()}")
            try:
                bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id, reaction=[])
            except Exception as remove_e:
                logging.error(f"Error removing reaction on FFmpeg error: {remove_e}")
            bot.send_message(
                message.chat.id,
                "😓 Waa ka xunahay, waxaa dhibaato ka dhacday beddelidda faylkaaga si cod loo aqoonsado. Fadlan isku day file kale."
            )
            return
        except Exception as e:
            logging.error(f"FFmpeg conversion failed: {e}")
            try:
                bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id, reaction=[])
            except Exception as remove_e:
                logging.error(f"Error removing reaction on FFmpeg general error: {remove_e}")
            bot.send_message(
                message.chat.id,
                "😓 Waa ka xunahay, faylkaagu lama beddeli karo qaabka saxda ah ee aqoonsiga codka. Fadlan hubi inuu yahay fayl audio/video caadi ah."
            )
            return

        # --- NEW: Isticmaal SpeechRecognition si qoraal loo sameeyo ---
        media_lang_name = user_media_language_settings[uid]  # Tusaale: "English"
        media_lang_code = get_speech_recognition_lang_code(media_lang_name)  # Tusaale: "en-US"
        if not media_lang_code:
            try:
                bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id, reaction=[])
            except Exception as remove_e:
                logging.error(f"Error removing reaction on language code error: {remove_e}")
            bot.send_message(
                message.chat.id,
                f"❌ Luqadda *{media_lang_name}* ma laha code sax ah aqoonsiga codka. Fadlan dib u dooro luqadda adigoo isticmaalaya /media_language."
            )
            return

        transcription = transcribe_audio_with_speech_recognition(wav_audio_path, media_lang_code) or ""
        user_transcriptions.setdefault(uid, {})[message.message_id] = transcription

        # --- NEW: Kordhi tirada transcription-ka ee user-ka, kadibna kaydi ---
        prev_count = user_transcription_counts.get(uid, 0)
        user_transcription_counts[uid] = prev_count + 1
        save_user_transcription_counts()

        total_files_processed += 1
        if message.voice:
            total_voice_clips += 1
        elif message.audio:
            total_audio_files += 1
        else:
            total_videos += 1

        processing_time = (datetime.now() - processing_start_time).total_seconds()
        total_processing_time += processing_time

        # Dhis badhamada Translate / Summarize
        buttons = InlineKeyboardMarkup()
        buttons.add(
            InlineKeyboardButton("Translate", callback_data=f"btn_translate|{message.message_id}"),
            InlineKeyboardButton("Summarize", callback_data=f"btn_summarize|{message.message_id}")
        )

        # Ka saar "👀" falcelinta ka hor inta aan natiijada la dirin
        try:
            bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id, reaction=[])
        except Exception as e:
            logging.error(f"Error removing reaction before sending result: {e}")

        # Dir natiijada qoraalka (haddii dheer yahay, u dir file)
        if len(transcription) > 4000:
            fn = 'transcription.txt'
            with open(fn, 'w', encoding='utf-8') as f:
                f.write(transcription)
            bot.send_chat_action(message.chat.id, 'upload_document')
            with open(fn, 'rb') as doc:
                bot.send_document(
                    message.chat.id,
                    doc,
                    reply_to_message_id=message.message_id,
                    reply_markup=buttons,
                    caption="Halkan waa qoraalkaaga. Taabo badhanka hoose haddii aad rabto wax kale."
                )
            os.remove(fn)
        else:
            bot.reply_to(
                message,
                transcription,
                reply_markup=buttons
            )

    except Exception as e:
        logging.error(f"Error processing file for user {uid}: {e}")
        try:
            bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id, reaction=[])
        except Exception as remove_e:
            logging.error(f"Error removing reaction on general processing error: {remove_e}")
        bot.send_message(
            message.chat.id,
            """😓𝗪𝗮𝗮𝗻 𝗸𝗮 𝘅𝘂𝗻𝗮𝗵𝗮𝘆, 𝗴𝗮𝗹𝗮𝗱𝗮 𝗵𝗲𝗹𝗹𝗮𝗻 𝗵𝗼𝘀𝗮𝗵𝗶𝗿𝗮𝗱𝗮 𝘁𝗶𝗹𝗹𝗮𝗮𝗯𝗮:
- Codku wuu buuq badan yahay ama si xawaare sarreeya ayaa loo hadlay.
- Fadlan mar kale isku day adigoo hubinaya in file-ka aad dirayso iyo luqadda aad dooratay ay is waafaqsan yihiin."""
        )
    finally:
        # Jooji tilmaamaha typing
        stop_typing.set()
        if message.chat.id in processing_message_ids:
            del processing_message_ids[message.chat.id]

        # Nadiifi faylasha kumeelgaarka ah
        if local_temp_file and os.path.exists(local_temp_file):
            os.remove(local_temp_file)
            logging.info(f"Cleaned up {local_temp_file}")
        if wav_audio_path and os.path.exists(wav_audio_path):
            os.remove(wav_audio_path)
            logging.info(f"Cleaned up {wav_audio_path}")

# --- Hel code-ka luqadda ee SpeechRecognition (tusaale: "en" → "en-US") ---
def get_speech_recognition_lang_code(lang_name):
    # Liiska luqadaha iyo code-yaashooda ee SpeechRecognition (Google)
    # Waxaa lagu dari karaa ama laga saari karaa sida loo baahdo
    mapping = {
        "English": "en-US",
        "Arabic": "ar-SA",
        "Spanish": "es-ES",
        "Hindi": "hi-IN",
        "French": "fr-FR",
        "German": "de-DE",
        "Chinese": "zh",
        "Japanese": "ja-JP",
        "Portuguese": "pt-PT",
        "Russian": "ru-RU",
        "Turkish": "tr-TR",
        "Korean": "ko-KR",
        "Italian": "it-IT",
        "Indonesian": "id-ID",
        "Vietnamese": "vi-VN",
        "Thai": "th-TH",
        "Dutch": "nl-NL",
        "Polish": "pl-PL",
        "Swedish": "sv-SE",
        "Filipino": "tl-PH",
        "Greek": "el-GR",
        "Hebrew": "he-IL",
        "Hungarian": "hu-HU",
        "Czech": "cs-CZ",
        "Danish": "da-DK",
        "Finnish": "fi-FI",
        "Norwegian": "nb-NO",
        "Romanian": "ro-RO",
        "Slovak": "sk-SK",
        "Ukrainian": "uk-UA",
        "Malay": "ms-MY",
        "Bengali": "bn-BD",
        "Tamil": "ta-IN",
        "Telugu": "te-IN",
        "Kannada": "kn-IN",
        "Malayalam": "ml-IN",
        "Gujarati": "gu-IN",
        "Marathi": "mr-IN",
        "Urdu": "ur-PK",
        "Nepali": "ne-NP",
        "Sinhala": "si-LK",
        "Khmer": "km-KH",
        "Lao": "lo-LA",
        "Burmese": "my-MM",
        "Georgian": "ka-GE",
        "Armenian": "hy-AM",
        "Azerbaijani": "az-AZ",
        "Kazakh": "kk-KZ",
        "Uzbek": "uz-UZ",
        "Somali": "so-SO",  # Haddii Google aqoonsado Somali, haddii kale laga yaabo inuu fashilmo
    }
    return mapping.get(lang_name, None)

# --- NEW: Isticmaal SpeechRecognition si qoraal loo sameeyo ---
def transcribe_audio_with_speech_recognition(audio_path: str, lang_code: str) -> str | None:
    """
    Isticmaalo maktabadda SpeechRecognition (Google API) si qoraal loo sameeyo,
    iyadoo la adeegsanayo file-ka WAV (16kHz, mono) ee hore loo sameeyey.
    """
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(audio_path) as source:
            audio_data = recognizer.record(source)
        # Isticmaal Google Web Speech API
        text = recognizer.recognize_google(audio_data, language=lang_code)
        return text
    except sr.UnknownValueError:
        logging.error("Google Speech Recognition could not understand audio")
        return ""
    except sr.RequestError as e:
        logging.error(f"Could not request results from Google Speech Recognition service; {e}")
        return None
    except Exception as e:
        logging.error(f"SpeechRecognition transcription error: {e}")
        return None

# --- Language Selection and Saving ---
LANGUAGES = [
    {"name": "English", "flag": "🇬🇧", "code": "en"},
    {"name": "Arabic", "flag": "🇸🇦", "code": "ar"},
    {"name": "Spanish", "flag": "🇪🇸", "code": "es"},
    {"name": "Hindi", "flag": "🇮🇳", "code": "hi"},
    {"name": "French", "flag": "🇫🇷", "code": "fr"},
    {"name": "German", "flag": "🇩🇪", "code": "de"},
    {"name": "Chinese", "flag": "🇨🇳", "code": "zh"},
    {"name": "Japanese", "flag": "🇯🇵", "code": "ja"},
    {"name": "Portuguese", "flag": "🇵🇹", "code": "pt"},
    {"name": "Russian", "flag": "🇷🇺", "code": "ru"},
    {"name": "Turkish", "flag": "🇹🇷", "code": "tr"},
    {"name": "Korean", "flag": "🇰🇷", "code": "ko"},
    {"name": "Italian", "flag": "🇮🇹", "code": "it"},
    {"name": "Indonesian", "flag": "🇮🇩", "code": "id"},
    {"name": "Vietnamese", "flag": "🇻🇳", "code": "vi"},
    {"name": "Thai", "flag": "🇹🇭", "code": "th"},
    {"name": "Dutch", "flag": "🇳🇱", "code": "nl"},
    {"name": "Polish", "flag": "🇵🇱", "code": "pl"},
    {"name": "Swedish", "flag": "🇸🇪", "code": "sv"},
    {"name": "Filipino", "flag": "🇵🇭", "code": "tl"},
    {"name": "Greek", "flag": "🇬🇷", "code": "el"},
    {"name": "Hebrew", "flag": "🇮🇱", "code": "he"},
    {"name": "Hungarian", "flag": "🇭🇺", "code": "hu"},
    {"name": "Czech", "flag": "🇨🇿", "code": "cs"},
    {"name": "Danish", "flag": "🇩🇰", "code": "da"},
    {"name": "Finnish", "flag": "🇫🇮", "code": "fi"},
    {"name": "Norwegian", "flag": "🇳🇴", "code": "no"},
    {"name": "Romanian", "flag": "🇷🇴", "code": "ro"},
    {"name": "Slovak", "flag": "🇸🇰", "code": "sk"},
    {"name": "Ukrainian", "flag": "🇺🇦", "code": "uk"},
    {"name": "Malay", "flag": "🇲🇾", "code": "ms"},
    {"name": "Bengali", "flag": "🇧🇩", "code": "bn"},
    {"name": "Tamil", "flag": "🇮🇳", "code": "ta"},
    {"name": "Telugu", "flag": "🇮🇳", "code": "te"},
    {"name": "Kannada", "flag": "🇮🇳", "code": "kn"},
    {"name": "Malayalam", "flag": "🇮🇳", "code": "ml"},
    {"name": "Gujarati", "flag": "🇮🇳", "code": "gu"},
    {"name": "Marathi", "flag": "🇮🇳", "code": "mr"},
    {"name": "Urdu", "flag": "🇵🇰", "code": "ur"},
    {"name": "Nepali", "flag": "🇳🇵", "code": "ne"},
    {"name": "Sinhala", "flag": "🇱🇰", "code": "si"},
    {"name": "Khmer", "flag": "🇰🇭", "code": "km"},
    {"name": "Lao", "flag": "🇱🇦", "code": "lo"},
    {"name": "Burmese", "flag": "🇲🇲", "code": "my"},
    {"name": "Georgian", "flag": "🇬🇪", "code": "ka"},
    {"name": "Armenian", "flag": "🇦🇲", "code": "hy"},
    {"name": "Azerbaijani", "flag": "🇦🇿", "code": "az"},
    {"name": "Kazakh", "flag": "🇰🇿", "code": "kk"},
    {"name": "Uzbek", "flag": "🇺🇿", "code": "uz"},
    {"name": "Kyrgyz", "flag": "🇰🇬", "code": "ky"},
    {"name": "Tajik", "flag": "🇹🇯", "code": "tg"},
    {"name": "Turkmen", "flag": "🇹🇲", "code": "tk"},
    {"name": "Mongolian", "flag": "🇲🇳", "code": "mn"},
    {"name": "Estonian", "flag": "🇪🇪", "code": "et"},
    {"name": "Latvian", "flag": "🇱🇻", "code": "lv"},
    {"name": "Lithuanian", "flag": "🇱🇹", "code": "lt"},
    {"name": "Afrikaans", "flag": "🇿🇦", "code": "af"},
    {"name": "Albanian", "flag": "🇦🇱", "code": "sq"},
    {"name": "Bosnian", "flag": "🇧🇦", "code": "bs"},
    {"name": "Bulgarian", "flag": "🇧🇬", "code": "bg"},
    {"name": "Catalan", "flag": "🇪🇸", "code": "ca"},
    {"name": "Croatian", "flag": "🇭🇷", "code": "hr"},
    {"name": "Galician", "flag": "🇪🇸", "code": "gl"},
    {"name": "Icelandic", "flag": "🇮🇸", "code": "is"},
    {"name": "Irish", "flag": "🇮🇪", "code": "ga"},
    {"name": "Macedonian", "flag": "🇲🇰", "code": "mk"},
    {"name": "Maltese", "flag": "🇲🇹", "code": "mt"},
    {"name": "Serbian", "flag": "🇷🇸", "code": "sr"},
    {"name": "Slovenian", "flag": "🇸🇮", "code": "sl"},
    {"name": "Welsh", "flag": "🏴", "code": "cy"},
    {"name": "Zulu", "flag": "🇿🇦", "code": "zu"},
    {"name": "Somali", "flag": "🇸🇴", "code": "so"},
]

def get_lang_code(lang_name):
    for lang in LANGUAGES:
        if lang['name'].lower() == lang_name.lower():
            return lang['code']
    return None

def generate_language_keyboard(callback_prefix, message_id=None):
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    for lang in LANGUAGES:
        cb_data = f"{callback_prefix}|{lang['name']}"
        if message_id is not None:
            cb_data += f"|{message_id}"
        buttons.append(InlineKeyboardButton(f"{lang['name']} {lang['flag']}", callback_data=cb_data))
    for i in range(0, len(buttons), 3):
        markup.add(*buttons[i:i+3])
    return markup

# --- NEW: Language and Voice selection for Text-to-Speech ---
def make_tts_language_keyboard():
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    for lang_name in TTS_VOICES_BY_LANGUAGE.keys():
        buttons.append(InlineKeyboardButton(lang_name, callback_data=f"tts_lang|{lang_name}"))
    for i in range(0, len(buttons), 3):
        markup.add(*buttons[i:i+3])
    return markup

def make_tts_voice_keyboard_for_language(lang_name):
    markup = InlineKeyboardMarkup(row_width=2)
    voices = TTS_VOICES_BY_LANGUAGE.get(lang_name, [])
    for voice in voices:
        markup.add(InlineKeyboardButton(voice, callback_data=f"tts_voice|{voice}"))
    markup.add(InlineKeyboardButton("⬅️ Back to Languages", callback_data="tts_back_to_languages"))
    return markup

@bot.message_handler(commands=['text_to_speech'])
def cmd_text_to_speech(message):
    user_id = str(message.from_user.id)
    update_user_activity(user_id)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(message.from_user.id) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: On TTS command, set TTS mode to active but don't set a voice yet ---
    user_tts_mode[user_id] = None
    bot.send_message(message.chat.id, "🎙️ Dooro luqadda text-to-speech:", reply_markup=make_tts_language_keyboard())

@bot.callback_query_handler(lambda c: c.data.startswith("tts_lang|"))
def on_tts_language_select(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(call.from_user.id) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    _, lang_name = call.data.split("|", 1)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"🎙️ Dooro codka {lang_name}:",
        reply_markup=make_tts_voice_keyboard_for_language(lang_name)
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(lambda c: c.data.startswith("tts_voice|"))
def on_tts_voice_change(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(call.from_user.id) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    _, voice = call.data.split("|", 1)
    tts_users[uid] = voice
    save_tts_users()

    # --- MODIFIED: Store the chosen voice in user_tts_mode to indicate readiness ---
    user_tts_mode[uid] = voice

    bot.answer_callback_query(call.id, f"✔️ Codka waa la beddelay: {voice}")
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"🔊 Hadda waa la isticmaalayaa: *{voice}*. Waxaad bilaabi kartaa inaad qoraal iigu soo dirto si cod loogu badelo.",
        parse_mode="Markdown"
    )

@bot.callback_query_handler(lambda c: c.data == "tts_back_to_languages")
def on_tts_back_to_languages(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(call.from_user.id) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    # --- MODIFIED: When going back, reset user_tts_mode as voice is no longer selected ---
    user_tts_mode[uid] = None

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="🎙️ Dooro luqadda text-to-speech:",
        reply_markup=make_tts_language_keyboard()
    )
    bot.answer_callback_query(call.id)

async def synth_and_send_tts(chat_id, user_id, text):
    voice = get_tts_user_voice(user_id)
    filename = os.path.join(DOWNLOAD_DIR, f"tts_{user_id}_{uuid.uuid4()}.mp3")

    stop_recording = threading.Event()
    recording_thread = threading.Thread(target=keep_recording, args=(chat_id, stop_recording))
    recording_thread.daemon = True
    recording_thread.start()

    try:
        mss = MSSpeech()
        await mss.set_voice(voice)
        await mss.set_rate(0)
        await mss.set_pitch(0)
        await mss.set_volume(1.0)

        await mss.synthesize(text, filename)

        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            bot.send_message(chat_id, "❌ MP3 file lama soo saarin ama waa faaruq. Fadlan mar kale isku day.")
            return

        with open(filename, "rb") as f:
            bot.send_audio(chat_id, f, caption=f"🎤 Cod: {voice}")
    except MSSpeechError as e:
        logging.error(f"TTS error: {e}")
        bot.send_message(chat_id, f"❌ Qalad ayaa ka dhacay synthesis: {e}")
    except Exception as e:
        logging.exception("TTS error")
        bot.send_message(chat_id, "❌ Qalad lama filaan ah ayaa ka dhacay text-to-speech. Fadlan mar kale isku day.")
    finally:
        stop_recording.set()
        if os.path.exists(filename):
            os.remove(filename)

@bot.message_handler(commands=['language'])
def select_language_command(message):
    uid = str(message.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(message.from_user.id) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF on language command ---
    user_tts_mode[uid] = None

    markup = generate_language_keyboard("set_lang")
    bot.send_message(
        message.chat.id,
        "Fadlan dooro luqadda aad rabto in qoraalada lagu turjumo/soo koobto mustaqbalka:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("set_lang|"))
def callback_set_language(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(call.from_user.id) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF when setting language ---
    user_tts_mode[uid] = None

    _, lang = call.data.split("|", 1)
    user_language_settings[uid] = lang
    save_user_language_settings()
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"✅ Luqadda turjumaadda iyo soo koobidda waa la dejiyey: **{lang}**",
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id, text=f"Luqadda waa la dejiyey: {lang}")

@bot.message_handler(commands=['media_language'])
def select_media_language_command(message):
    uid = str(message.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(message.from_user.id) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF on media_language command ---
    user_tts_mode[uid] = None

    markup = generate_language_keyboard("set_media_lang")
    bot.send_message(
        message.chat.id,
        "Fadlan dooro luqadda codka file-kaaga si aan u hubino qoraal sax ah.",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("set_media_lang|"))
def callback_set_media_language(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(call.from_user.id) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF when setting media language ---
    user_tts_mode[uid] = None

    _, lang = call.data.split("|", 1)
    user_media_language_settings[uid] = lang
    save_user_media_language_settings()
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=(
            f"✅ Luqada transcription-ka media-gaaga waa la dejiyey: **{lang}**\n\n"
            "Hadda waxaad soo diri kartaa voice message, audio file, video note, ama video file, aniguna waan qori doonaa. Waxaan taageersan nahay ilaa 20MB."
        ),
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id, text=f"Luqadda transcription waa la dejiyey: {lang}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("btn_translate|"))
def button_translate_handler(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(call.from_user.id) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF when using translate button ---
    user_tts_mode[uid] = None

    _, message_id_str = call.data.split("|", 1)
    message_id = int(message_id_str)

    if uid not in user_transcriptions or message_id not in user_transcriptions[uid]:
        bot.answer_callback_query(call.id, "❌ Qoraal transcription kuma jiro farriintan.")
        return

    preferred_lang = user_language_settings.get(uid)
    if preferred_lang:
        bot.answer_callback_query(call.id, "Turjumaad ayaa lagu sameynayaa luqaddaad dooratay...")
        threading.Thread(target=do_translate_with_saved_lang, args=(call.message, uid, preferred_lang, message_id)).start()
    else:
        markup = generate_language_keyboard("translate_to", message_id)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Fadlan dooro luqadda aad rabto in qoraalka lagu turjumo:",
            reply_markup=markup
        )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("btn_summarize|"))
def button_summarize_handler(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(call.from_user.id) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF when using summarize button ---
    user_tts_mode[uid] = None

    _, message_id_str = call.data.split("|", 1)
    message_id = int(message_id_str)

    if uid not in user_transcriptions or message_id not in user_transcriptions[uid]:
        bot.answer_callback_query(call.id, "❌ Qoraal transcription kuma jiro farriintan.")
        return

    preferred_lang = user_language_settings.get(uid)
    if preferred_lang:
        bot.answer_callback_query(call.id, "Soo koobid ayaa lagu sameynayaa luqaddaad dooratay...")
        threading.Thread(target=do_summarize_with_saved_lang, args=(call.message, uid, preferred_lang, message_id)).start()
    else:
        markup = generate_language_keyboard("summarize_in", message_id)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Fadlan dooro luqadda aad rabto in qoraalka lagu soo koobo:",
            reply_markup=markup
        )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("translate_to|"))
def callback_translate_to(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(call.from_user.id) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF when using translate_to callback ---
    user_tts_mode[uid] = None

    parts = call.data.split("|")
    lang = parts[1]
    message_id = int(parts[2]) if len(parts) > 2 else None

    user_language_settings[uid] = lang
    save_user_language_settings()

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"Turjumaad waxaa lagu samayn doonaa **{lang}**...",
        parse_mode="Markdown"
    )

    if message_id:
        threading.Thread(target=do_translate_with_saved_lang, args=(call.message, uid, lang, message_id)).start()
    else:
        if uid in user_transcriptions and call.message.reply_to_message and call.message.reply_to_message.message_id in user_transcriptions[uid]:
            threading.Thread(target=do_translate_with_saved_lang, args=(call.message, uid, lang, call.message.reply_to_message.message_id)).start()
        else:
            bot.send_message(call.message.chat.id, "❌ Qoraal transcription kuma jiro farriintan si loo turjumo. Fadlan isticmaal badhamada inline ee transcription-ka.")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("summarize_in|"))
def callback_summarize_in(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(call.from_user.id) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF when using summarize_in callback ---
    user_tts_mode[uid] = None

    parts = call.data.split("|")
    lang = parts[1]
    message_id = int(parts[2]) if len(parts) > 2 else None

    user_language_settings[uid] = lang
    save_user_language_settings()

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"Soo koobid waxaa lagu samayn doonaa **{lang}**...",
        parse_mode="Markdown"
    )

    if message_id:
        threading.Thread(target=do_summarize_with_saved_lang, args=(call.message, uid, lang, message_id)).start()
    else:
        if uid in user_transcriptions and call.message.reply_to_message and call.message.reply_to_message.message_id in user_transcriptions[uid]:
            threading.Thread(target=do_summarize_with_saved_lang, args=(call.message, uid, lang, call.message.reply_to_message.message_id)).start()
        else:
            bot.send_message(call.message.chat.id, "❌ Qoraal transcription kuma jiro farriintan si loo soo koobo. Fadlan isticmaal badhamada inline ee transcription-ka.")
    bot.answer_callback_query(call.id)

def do_translate_with_saved_lang(message, uid, lang, message_id):
    original = user_transcriptions.get(uid, {}).get(message_id, "")
    if not original:
        bot.send_message(message.chat.id, "❌ Qoraal transcription kuma jiro fariintan si loo turjumo.")
        return

    prompt = f"Translate the following text into {lang}. Provide only the translated text, with no additional notes, explanations, or introductory/concluding remarks:\n\n{original}"

    bot.send_chat_action(message.chat.id, 'typing')
    translated = ask_gemini(uid, prompt)

    if translated.startswith("Error:"):
        bot.send_message(message.chat.id, f"😓 Waa ka xunahay, qalad ayaa dhacay intii lagu turjumayay: {translated}. Fadlan mar kale isku day.")
        return

    if len(translated) > 4000:
        fn = 'translation.txt'
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(translated)
        bot.send_chat_action(message.chat.id, 'upload_document')
        with open(fn, 'rb') as doc:
            bot.send_document(message.chat.id, doc, caption=f"Turjumaad luqadda {lang}", reply_to_message_id=message_id)
        os.remove(fn)
    else:
        bot.send_message(message.chat.id, translated, reply_to_message_id=message_id)

def do_summarize_with_saved_lang(message, uid, lang, message_id):
    original = user_transcriptions.get(uid, {}).get(message_id, "")
    if not original:
        bot.send_message(message.chat.id, "❌ Qoraal transcription kuma jiro fariintan si loo soo koobo.")
        return

    prompt = f"Summarize the following text in {lang}. Provide only the summarized text, with no additional notes, explanations, or different versions:\n\n{original}"

    bot.send_chat_action(message.chat.id, 'typing')
    summary = ask_gemini(uid, prompt)

    if summary.startswith("Error:"):
        bot.send_message(message.chat.id, f"😓 Waa ka xunahay, qalad ayaa dhacay intii lagu soo koobayay: {summary}. Fadlan mar kale isku day.")
        return

    if len(summary) > 4000:
        fn = 'summary.txt'
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(summary)
        bot.send_chat_action(message.chat.id, 'upload_document')
        with open(fn, 'rb') as doc:
            bot.send_document(message.chat.id, doc, caption=f"Soo koobid luqadda {lang}", reply_to_message_id=message_id)
        os.remove(fn)
    else:
        bot.send_message(message.chat.id, summary, reply_to_message_id=message_id)

@bot.message_handler(commands=['translate'])
def handle_translate(message):
    uid = str(message.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(message.from_user.id) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF on translate command ---
    user_tts_mode[uid] = None

    if not message.reply_to_message or uid not in user_transcriptions or message.reply_to_message.message_id not in user_transcriptions[uid]:
        return bot.send_message(message.chat.id, "❌ Fadlan ku jawaab fariin transcription si aad u turjumo.")

    transcription_message_id = message.reply_to_message.message_id
    preferred_lang = user_language_settings.get(uid)
    if preferred_lang:
        threading.Thread(target=do_translate_with_saved_lang, args=(message, uid, preferred_lang, transcription_message_id)).start()
    else:
        markup = generate_language_keyboard("translate_to", transcription_message_id)
        bot.send_message(
            message.chat.id,
            "Fadlan dooro luqadda aad rabto in qoraalka lagu turjumo:",
            reply_markup=markup
        )

@bot.message_handler(commands=['summarize'])
def handle_summarize(message):
    uid = str(message.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Delay subscription prompt ---
    if requires_subscription(message.from_user.id) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF on summarize command ---
    user_tts_mode[uid] = None

    if not message.reply_to_message or uid not in user_transcriptions or message.reply_to_message.message_id not in user_transcriptions[uid]:
        return bot.send_message(message.chat.id, "❌ Fadlan ku jawaab fariin transcription si aad u soo koobin.")

    transcription_message_id = message.reply_to_message.message_id
    preferred_lang = user_language_settings.get(uid)
    if preferred_lang:
        threading.Thread(target=do_summarize_with_saved_lang, args=(message, uid, preferred_lang, transcription_message_id)).start()
    else:
        markup = generate_language_keyboard("summarize_in", transcription_message_id)
        bot.send_message(
            message.chat.id,
            "Fadlan dooro luqadda aad rabto in qoraalka lagu soo koobo:",
            reply_markup=markup
        )

# --- Memory Cleanup Function ---
def cleanup_old_data():
    """Qaadista user_transcriptions iyo user_memory ka weyn 7 maalmood."""
    seven_days_ago = datetime.now() - timedelta(days=7)

    keys_to_delete_transcriptions = []
    for user_id, transcriptions in user_transcriptions.items():
        if user_id in user_data:
            last_activity = datetime.fromisoformat(user_data[user_id])
            if last_activity < seven_days_ago:
                keys_to_delete_transcriptions.append(user_id)
        else:
            keys_to_delete_transcriptions.append(user_id)

    for user_id in keys_to_delete_transcriptions:
        if user_id in user_transcriptions:
            del user_transcriptions[user_id]
            logging.info(f"Cleaned up old transcriptions for user {user_id}")

    keys_to_delete_memory = []
    for user_id in user_memory:
        if user_id in user_data:
            last_activity = datetime.fromisoformat(user_data[user_id])
            if last_activity < seven_days_ago:
                keys_to_delete_memory.append(user_id)
        else:
            keys_to_delete_memory.append(user_id)

    for user_id in keys_to_delete_memory:
        if user_id in user_memory:
            del user_memory[user_id]
            logging.info(f"Cleaned up old chat memory for user {user_id}")

    # --- NEW: Also clean up TTS user preferences if user is inactive ---
    keys_to_delete_tts_users = []
    for user_id in tts_users:
        if user_id in user_data:
            last_activity = datetime.fromisoformat(user_data[user_id])
            if last_activity < seven_days_ago:
                keys_to_delete_tts_users.append(user_id)
        else:
            keys_to_delete_tts_users.append(user_id)

    for user_id in keys_to_delete_tts_users:
        if user_id in tts_users:
            del tts_users[user_id]
            if user_id in user_tts_mode:
                del user_tts_mode[user_id]
            logging.info(f"Cleaned up old TTS preferences for user {user_id}")
    save_tts_users()  # Save updated TTS user data
    # --- End of NEW cleanup ---

    threading.Timer(24 * 60 * 60, cleanup_old_data).start()  # Run every 24 hours

# --- NEW: Handle all text messages for TTS after command selection ---
@bot.message_handler(func=lambda message: message.content_type == 'text' and not message.text.startswith('/'))
def handle_text_for_tts_or_fallback(message):
    uid = str(message.from_user.id)
    update_user_activity(uid)

    # --- NEW: Delay subscription prompt ---
    if requires_subscription(message.from_user.id) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return
    # --- End NEW check ---

    # --- MODIFIED: Check if a voice is set in user_tts_mode (it will be the voice name if set) ---
    if user_tts_mode.get(uid):  # Haddii user-ka uu horey u doortay cod TTS
        threading.Thread(
            target=lambda: asyncio.run(synth_and_send_tts(message.chat.id, uid, message.text))
        ).start()
    elif uid in tts_users:  # User-ku wuxuu leeyahay cod kaydsan, balse ma bilowin /text_to_speech
        user_tts_mode[uid] = tts_users[uid]  # Dib u dhaqaaji TTS mode isticmaalo codka kaydsan
        threading.Thread(
            target=lambda: asyncio.run(synth_and_send_tts(message.chat.id, uid, message.text))
        ).start()
    else:  # User-ku weli cod ma dooranin TTS
        bot.send_message(
            message.chat.id,
            "Waxaan kaliya qoraal u beddelaa cod haddii aad isticmaasho /text_to_speech marka hore."
        )

@bot.message_handler(func=lambda m: True, content_types=['photo', 'sticker', 'document'])
def fallback_non_text_or_media(message):
    uid = str(message.from_user.id)
    update_user_activity(uid)
    # --- NEW: Delay subscription prompt ---
    if requires_subscription(message.from_user.id) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return
    # --- End NEW check ---

    # --- MODIFIED: Ensure TTS mode is OFF when a non-text/non-media message is sent ---
    user_tts_mode[uid] = None
    # --- END MODIFIED ---
    bot.send_message(
        message.chat.id,
        "Fadlan kaliya soo dir voice message, audio file, video note, ama video file si loogu qoro, ama isticmaal `/text_to_speech` qoraal si cod loogu beddelo."
    )

@app.route("/", methods=["GET", "POST", "HEAD"])
def webhook():
    # 1) Health‐check (GET or HEAD) → return 200 OK
    if request.method in ("GET", "HEAD"):
        return "OK", 200

    # 2) Telegram webhook (POST with JSON)
    if request.method == "POST":
        content_type = request.headers.get("Content-Type", "")
        if content_type and content_type.startswith("application/json"):
            update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
            bot.process_new_updates([update])
            return "", 200

    return abort(403)

@app.route("/set_webhook", methods=["GET", "POST"])
def set_webhook_route():
    try:
        bot.set_webhook(url=WEBHOOK_URL)
        return f"Webhook set to {WEBHOOK_URL}", 200
    except Exception as e:
        logging.error(f"Failed to set webhook: {e}")
        return f"Failed to set webhook: {e}", 500

@app.route("/delete_webhook", methods=["GET", "POST"])
def delete_webhook_route():
    try:
        bot.delete_webhook()
        return "Webhook deleted.", 200
    except Exception as e:
        logging.error(f"Failed to delete webhook: {e}")
        return f"Failed to delete webhook: {e}", 500

def set_webhook_on_startup():
    try:
        bot.set_webhook(url=WEBHOOK_URL)
        logging.info(f"Webhook set successfully to {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Failed to set webhook on startup: {e}")

if __name__ == "__main__":
    set_bot_info()
    cleanup_old_data()  # Bilaaw nadiifinta xogta duugga ah
    set_webhook_on_startup()  # Dejiso webhook marka app-ku bilaabmo
    # Hubi in Flask app-ku ku socdo port-ka Render (badanaa 8080)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
