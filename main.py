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

# --- REPLACE: Import SpeechRecognition instead of FasterWhisper ---
import speech_recognition as sr

# --- KEEP: MSSpeech for Text-to-Speech ---
from msspeech import MSSpeech, MSSpeechError

# Configure logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- BOT CONFIGURATION (Using Media Transcriber Bot's Token and Webhook) ---
TOKEN = "7790991731:AAH4rt8He_PABDa28xgcY3dIQwmtuQD-qiM"  # Replace with your actual bot token
ADMIN_ID = 5978150981  # Replace with your actual Admin ID
# Webhook URL - Replace with your actual Render URL
WEBHOOK_URL = "https://speech-recognition-9j3f.onrender.com"

# --- REQUIRED CHANNEL CONFIGURATION ---
REQUIRED_CHANNEL = "@transcriberbo"  # Replace with your actual channel username

bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

# Download directory (still used for intermediate WAV, but aiming for in-memory)
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
    with open(user_media_language_settings_file, 'r') as f:  # Corrected variable name here
        try:
            user_media_language_settings = json.load(f)
        except json.JSONDecodeError:
            user_media_language_settings = {}

# --- NEW: TTS User settings and Voices ---
tts_users_db = 'tts_users.json'  # Separate DB for TTS user preferences
tts_users = {}
if os.path.exists(tts_users_db):
    try:
        with open(tts_users_db, "r") as f:
            tts_users = json.load(f)
    except json.JSONDecodeError:
        tts_users = {}

# --- NEW: User state for Text-to-Speech input mode ---
# {user_id: "en-US-AriaNeural" (chosen voice) or None (not in TTS mode)}
user_tts_mode = {}

# Group voices by language for better organization - Ordered as requested for buttons
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
    "Somali 🇸🇴": [  # Added Somali to the main list for popular languages
        "so-SO-UbaxNeural", "so-SO-MuuseNeural",
    ],
}
# --- End of NEW TTS Voice Config ---

# Remove FasterWhisper model loading; no longer needed

def save_user_data():
    with open(users_file, 'w') as f:
        json.dump(user_data, f, indent=4)

def save_user_language_settings():
    with open(user_language_settings_file, 'w') as f:
        json.dump(user_language_settings, f, indent=4)

def save_user_media_language_settings():
    with open(user_media_language_settings_file, 'w') as f:
        json.dump(user_media_language_settings, f, indent=4)

# --- NEW: Save TTS user settings ---
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

GEMINI_API_KEY = "AIzaSyAto78yGVZobxOwPXnl8wCE9ZW8Do2R8HA"  # Replace with your actual Gemini API Key

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
        telebot.types.BotCommand("text_to_speech", "🗣️Convert text to speech"),
    ]
    bot.set_my_commands(commands)

    bot.set_my_short_description(
        "Got media files? Let this free bot transcribe, summarize, and translate them in seconds!"
    )

    bot.set_my_description(
        """This bot quickly transcribes, summarizes, and translates voice messages, audio files, and videos for free!
Also, it can convert your text into speech in various languages!

     🔥Enjoy free usage and start now!👌🏻"""
    )

def update_user_activity(user_id):
    user_data.setdefault(str(user_id), {}) # Ensure user_id exists as a dict
    user_data[str(user_id)]['last_active'] = datetime.now().isoformat()
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

# --- NEW: Check Channel Subscription - MODIFIED TO BE CONDITIONAL ---
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
        "😓Sorry …\n🔰 To continue using this bot next time First join the channel @transcriberbo ‼️ After joining, come back to continue using the bot.",
        reply_markup=markup,
        disable_web_page_preview=True
    )

@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = str(message.from_user.id)
    update_user_activity(message.from_user.id)

    # Always add user to user_data on start, initialize transcription_count
    if user_id not in user_data:
        user_data[user_id] = {'last_active': datetime.now().isoformat(), 'transcription_count': 0}
        save_user_data()
    elif 'transcription_count' not in user_data[user_id]: # Handle existing users without the new field
        user_data[user_id]['transcription_count'] = 0
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
        # --- MODIFIED: Send media language selection directly on /start ---
        markup = generate_language_keyboard("set_media_lang")
        bot.send_message(
            message.chat.id,
            "Please choose the language of the audio files using the below buttons.",
            reply_markup=markup
        )
        # --- END MODIFIED ---

@bot.message_handler(commands=['help'])
def help_handler(message):
    user_id = str(message.from_user.id)
    update_user_activity(user_id)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(user_id, {}).get('transcription_count', 0) >= 5 and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF on help command ---
    user_tts_mode[user_id] = None

    help_text = (
        """ℹ️ How to use this bot:

This bot transcribes voice messages, audio files, and videos using advanced AI, and can also convert text to speech!

1.  **Send a File for Transcription:**
    * Send a voice message, audio file, video note, or a video file (e.g. .mp4) as a document/attachment.
    * **Crucially**, before sending your media, use the `/media_language` command to tell the bot the language of the audio. This ensures the most accurate transcription possible.
    * The bot will then process your media and send back the transcribed text. If the transcription is very long, it will be sent as a text file for easier reading.
    * After receiving the transcription, you'll see inline buttons with options to **Translate** or **Summarize** the text.

2.  **Convert Text to Speech:**
    * Use the command `/text_to_speech` to choose a language and voice.
    * After selecting your preferred voice, simply send any text message, and the bot will convert it into an audio file for you.

3.  **Commands:**
    * `/start`: Get a welcome message and info about the bot. (Admins see a live uptime panel).
    * `/status`: View detailed statistics about the bot's performance and usage.
    * `/help`: Display these instructions on how to use the bot.
    * `/language`: Change your preferred language for translations and summaries. This setting applies to text outputs, not the original media.
    * `/media_language`: Set the language of the audio in your media files for transcription. This is vital for accuracy.
    * `/text_to_speech`: Choose a language and voice for the text-to-speech feature.
    * `/privacy`: Read the bot's privacy notice to understand how your data is handled.

Enjoy transcribing, translating, summarizing, and converting text to speech quickly and easily!
"""
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['privacy'])
def privacy_notice_handler(message):
    user_id = str(message.from_user.id)
    update_user_activity(user_id)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(user_id, {}).get('transcription_count', 0) >= 5 and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF on privacy command ---
    user_tts_mode[user_id] = None

    privacy_text = (
        """**Privacy Notice**

Your privacy is paramount. Here's a transparent look at how this bot handles your data in real-time:

1.  **Data We Process & Its Lifecycle:**
    * **Media Files (Voice, Audio, Video):** When you send a media file (voice, audio, video note, or a video file as a document), it's temporarily downloaded for **immediate transcription**. Crucially, these files are **deleted instantly** from our servers once the transcription is complete. We do not store your media content.
    * **Text for Speech Synthesis:** When you send text for conversion to speech, it is processed to generate the audio and then **not stored**. The generated audio file is also temporary and deleted after sending.
    * **Transcriptions:** The text generated from your media is held **temporarily in the bot's memory** for a limited period. This allows for follow-up actions like translation or summarization. This data is not permanently stored on our servers and is cleared regularly (e.g., when new media is processed or the bot restarts, or after 7 days as per cleanup).
    * **User IDs:** Your Telegram User ID is stored. This helps us remember your language preferences and track basic, aggregated activity (like when you last used the bot) to improve service and understand overall usage patterns. This ID is not linked to any personal identifying information outside of Telegram.
    * **Language Preferences:** Your chosen languages for translations/summaries and media transcription are saved. Your chosen voice for text-to-speech is also saved. This ensures you don't need to re-select them for every interaction, making your experience smoother.

2.  **How Your Data is Used:**
    * To deliver the bot's core services: transcribing, translating, summarizing your media, and converting text to speech.
    * To enhance bot performance and gain insights into general usage trends through anonymous, collective statistics (e.g., total files processed).
    * To maintain your personalized language settings and voice preferences across sessions.

3.  **Data Sharing Policy:**
    * We **do not share** your personal data, media files, or transcriptions with any third parties.
    * Transcription, translation, and summarization are facilitated by integrating with advanced AI models (specifically, the Google Speech-to-Text API for transcription and the Gemini API for translation/summarization). Text-to-speech uses the Microsoft Cognitive Services Speech API. Your input sent to these models is governed by their respective privacy policies, but we ensure that your data is **not stored by us** after processing by these services.

4.  **Data Retention:**
    * **Media files and generated audio files:** Deleted immediately post-processing.
    * **Transcriptions:** Held temporarily in the bot's active memory for immediate use and cleared after 7 days or when superseded.
    * **User IDs and language/voice preferences:** Retained to support your settings and for anonymous usage statistics. If you wish to have your stored preferences removed, you can cease using the bot or contact the bot administrator for explicit data deletion.

By using this bot, you acknowledge and agree to the data practices outlined in this Privacy Notice.

Should you have any questions or concerns regarding your privacy, please feel free to contact the bot administrator.
"""
    )
    bot.send_message(message.chat.id, privacy_text, parse_mode="Markdown")

@bot.message_handler(commands=['status'])
def status_handler(message):
    user_id = str(message.from_user.id)
    update_user_activity(user_id)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(user_id, {}).get('transcription_count', 0) >= 5 and not check_subscription(message.from_user.id):
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
        1 for user_info in user_data.values()
        if 'last_active' in user_info and datetime.fromisoformat(user_info['last_active']).date() == today
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

    # --- MODIFIED: Check subscription only if transcription count is met ---
    user_transcription_count = user_data.get(uid, {}).get('transcription_count', 0)
    if user_transcription_count >= 5 and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    # --- End NEW check ---

    # If user hasn't chosen a media_language yet, prompt them
    if uid not in user_media_language_settings:
        bot.send_message(
            message.chat.id,
            "⚠️ Please first select the language of the audio/video file using /media_language before sending the file."
        )
        return

    # Determine which file object to use:
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
        # Only accept the document if it's an audio/video file
        mime = message.document.mime_type or ""
        if mime.startswith("video/") or mime.startswith("audio/"):
            file_obj = message.document
            is_document_video = True
        else:
            # Not a supported media document: ask user to send a voice/audio/video
            bot.send_message(
                message.chat.id,
                "❌ The file you sent is not a supported audio/video format. "
                "Please send a voice message, audio file, video note, or video file (e.g. .mp4)."
            )
            return

    if not file_obj:
        # If somehow none of the above matched, bail out
        bot.send_message(
            message.chat.id,
            "❌ Please send only voice messages, audio files, video notes, or video files."
        )
        return

    # Check file size
    size = file_obj.file_size
    if size and size > FILE_SIZE_LIMIT:
        bot.send_message(message.chat.id, "😓 Sorry, the file size you uploaded is too large (max allowed is 20MB).")
        return

    # ─── Directly send "👀" reaction ────────────────────────────────────────────
    try:
        bot.set_message_reaction(
            chat_id=message.chat.id,
            message_id=message.message_id,
            reaction=[{'type': 'emoji', 'emoji': '👀'}]
        )
    except Exception as e:
        logging.error(f"Error setting reaction: {e}")
    # ──────────────────────────────────────────────────────────────────────────────

    # Start typing indicator
    stop_typing = threading.Event()
    typing_thread = threading.Thread(target=keep_typing, args=(message.chat.id, stop_typing))
    typing_thread.daemon = True
    typing_thread.start()
    processing_message_ids[message.chat.id] = stop_typing  # Store for cleanup

    try:
        # Process the file in a separate thread
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
        bot.send_message(message.chat.id, "😓 Sorry, an unexpected error occurred. Please try again.")

def process_media_file(message, stop_typing, is_document_video):
    """
    Download the media (voice/audio/video/document),
    convert it to WAV, run SpeechRecognition transcription,
    and send back the result.
    """
    global total_files_processed, total_audio_files, total_voice_clips, total_videos, total_processing_time

    uid = str(message.from_user.id)

    # Determine file_obj again (could be voice, audio, video, video_note, or document)
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

        # Decide extension:
        if message.voice or message.video_note:
            file_extension = ".ogg"
        elif message.document:
            # Use the original filename extension if available, else fallback to what get_file returns
            _, ext = os.path.splitext(message.document.file_name or info.file_path)
            file_extension = ext if ext else os.path.splitext(info.file_path)[1]
        else:
            file_extension = os.path.splitext(info.file_path)[1]  # .mp3, .wav, .mp4, etc.

        # Download file to a temporary location for ffmpeg processing
        local_temp_file = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4()}{file_extension}")
        data = bot.download_file(info.file_path)
        with open(local_temp_file, 'wb') as f:
            f.write(data)

        processing_start_time = datetime.now()

        # Convert whatever we downloaded into a 16kHz, mono WAV for SpeechRecognition
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
                "😓 Sorry, there was an issue converting your audio/video to the correct format. "
                "Please try again with a different file."
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
                "😓 Sorry, your file cannot be converted to the correct voice recognition format. "
                "Please ensure it's a standard audio/video file."
            )
            return

        # --- NEW: Transcribe using SpeechRecognition ---
        media_lang_name = user_media_language_settings[uid]  # e.g. "English"
        media_lang_code = get_lang_code(media_lang_name)     # e.g. "en"
        if not media_lang_code:
            try:
                bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id, reaction=[])
            except Exception as remove_e:
                logging.error(f"Error removing reaction on language code error: {remove_e}")
            bot.send_message(
                message.chat.id,
                f"❌ The language *{media_lang_name}* does not have a valid code for transcription. "
                "Please re-select the language using /media_language."
            )
            return

        transcription = transcribe_audio_with_speech_recognition(wav_audio_path, media_lang_code) or ""
        user_transcriptions.setdefault(uid, {})[message.message_id] = transcription

        total_files_processed += 1
        if message.voice:
            total_voice_clips += 1
        elif message.audio:
            total_audio_files += 1
        else:
            # Either video, video_note, or document.
            total_videos += 1

        processing_time = (datetime.now() - processing_start_time).total_seconds()
        total_processing_time += processing_time

        # --- MODIFIED: Increment transcription count for the user ---
        user_data[uid]['transcription_count'] = user_data[uid].get('transcription_count', 0) + 1
        save_user_data()
        # --- END MODIFIED ---

        # Build inline buttons for Translate / Summarize
        buttons = InlineKeyboardMarkup()
        buttons.add(
            InlineKeyboardButton("Translate", callback_data=f"btn_translate|{message.message_id}"),
            InlineKeyboardButton("Summarize", callback_data=f"btn_summarize|{message.message_id}")
        )

        # ─── Remove the "👀" reaction before sending the result ──────────────────────────
        try:
            bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id, reaction=[])
        except Exception as e:
            logging.error(f"Error removing reaction before sending result: {e}")

        # Send transcription result (either as a long file or inline text)
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
                    caption="Here’s your transcription. Tap a button below for more options."
                )
            os.remove(fn)
        else:
            bot.reply_to(
                message,
                transcription,
                reply_markup=buttons
            )

        # --- MODIFIED: Check and send subscription message AFTER successful transcription ---
        if user_data[uid]['transcription_count'] == 5 and not check_subscription(message.from_user.id):
            send_subscription_message(message.chat.id)
        # --- END MODIFIED ---

    except Exception as e:
        logging.error(f"Error processing file for user {uid}: {e}")
        try:
            bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id, reaction=[])
        except Exception as remove_e:
            logging.error(f"Error removing reaction on general processing error: {remove_e}")
        bot.send_message(
            message.chat.id,
            "😓𝗪𝗲’𝗿𝗲 𝘀𝗼𝗿𝗿𝘆, 𝗮𝗻 𝗲𝗿𝗿𝗼𝗿 𝗼𝗰𝗰𝘂𝗿𝗿𝗲𝗱 𝗱𝘂𝗿𝗶𝗻𝗴 𝘁𝗿𝗮𝗻𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻.\n"
            "The audio might be noisy or spoken too quickly.\n"
            "Please try again or upload a different file.\n"
            "Make sure the file you’re sending and the selected language match — otherwise, an error may occur."
        )
    finally:
        # Stop the typing indicator
        stop_typing.set()
        if message.chat.id in processing_message_ids:
            del processing_message_ids[message.chat.id]

        # Clean up the downloaded temp files
        if local_temp_file and os.path.exists(local_temp_file):
            os.remove(local_temp_file)
            logging.info(f"Cleaned up {local_temp_file}")
        if wav_audio_path and os.path.exists(wav_audio_path):
            os.remove(wav_audio_path)
            logging.info(f"Cleaned up {wav_audio_path}")

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
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(user_id, {}).get('transcription_count', 0) >= 5 and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: On TTS command, set TTS mode to active but don't set a voice yet ---
    user_tts_mode[user_id] = None
    bot.send_message(message.chat.id, "🎙️ Choose a language for text-to-speech:", reply_markup=make_tts_language_keyboard())

@bot.callback_query_handler(lambda c: c.data.startswith("tts_lang|"))
def on_tts_language_select(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(call.from_user.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    _, lang_name = call.data.split("|", 1)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"🎙️ Choose a voice for {lang_name}:",
        reply_markup=make_tts_voice_keyboard_for_language(lang_name)
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(lambda c: c.data.startswith("tts_voice|"))
def on_tts_voice_change(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(call.from_user.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    _, voice = call.data.split("|", 1)
    tts_users[uid] = voice
    save_tts_users()

    # --- MODIFIED: Store the chosen voice in user_tts_mode to indicate readiness ---
    user_tts_mode[uid] = voice

    bot.answer_callback_query(call.id, f"✔️ Voice changed to {voice}")
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"🔊 Now using: *{voice}*. You can start sending text messages to convert them to speech.",
        parse_mode="Markdown"
    )

@bot.callback_query_handler(lambda c: c.data == "tts_back_to_languages")
def on_tts_back_to_languages(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(call.from_user.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    # --- MODIFIED: When going back, reset user_tts_mode as voice is no longer selected ---
    user_tts_mode[uid] = None

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="🎙️ Choose a language for text-to-speech:",
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
            bot.send_message(chat_id, "❌ MP3 file not generated or empty. Please try again.")
            return

        with open(filename, "rb") as f:
            bot.send_audio(chat_id, f, caption=f"🎤 Voice: {voice}")
    except MSSpeechError as e:
        logging.error(f"TTS error: {e}")
        bot.send_message(chat_id, f"❌ An error occurred with the voice synthesis: {e}")
    except Exception as e:
        logging.exception("TTS error")
        bot.send_message(chat_id, "❌ An unexpected error occurred during text-to-speech conversion. Please try again.")
    finally:
        stop_recording.set()
        if os.path.exists(filename):
            os.remove(filename)

@bot.message_handler(commands=['language'])
def select_language_command(message):
    uid = str(message.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF on language command ---
    user_tts_mode[uid] = None

    markup = generate_language_keyboard("set_lang")
    bot.send_message(
        message.chat.id,
        "Please select your preferred language for future **translations and summaries**:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("set_lang|"))
def callback_set_language(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(call.from_user.id):
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
        text=f"✅ Your preferred language for translations and summaries has been set to: **{lang}**",
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id, text=f"Language set to {lang}")

@bot.message_handler(commands=['media_language'])
def select_media_language_command(message):
    uid = str(message.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF on media_language command ---
    user_tts_mode[uid] = None

    markup = generate_language_keyboard("set_media_lang")
    bot.send_message(
        message.chat.id,
        "Please choose the language of the audio files that you need me to transcribe. This helps ensure accurate reading.",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("set_media_lang|"))
def callback_set_media_language(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(call.from_user.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF when setting media language ---
    user_tts_mode[uid] = None

    _, lang = call.data.split("|", 1)
    user_media_language_settings[uid] = lang
    save_user_media_language_settings()
    
    # --- MODIFIED: Send the instruction to send media files after language selection ---
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"✅ The transcription language for your media is set to: **{lang}**\n\n"
             "Now, please send your voice message, audio file, video note, or video file "
             "for me to transcribe. I support media files up to 20MB in size.",
        parse_mode="Markdown"
    )
    # --- END MODIFIED ---
    bot.answer_callback_query(call.id, text=f"Media language set to {lang}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("btn_translate|"))
def button_translate_handler(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(call.from_user.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF when using translate button ---
    user_tts_mode[uid] = None

    _, message_id_str = call.data.split("|", 1)
    message_id = int(message_id_str)

    if uid not in user_transcriptions or message_id not in user_transcriptions[uid]:
        bot.answer_callback_query(call.id, "❌ No transcription found for this message.")
        return

    preferred_lang = user_language_settings.get(uid)
    if preferred_lang:
        bot.answer_callback_query(call.id, "Translating with your preferred language...")
        threading.Thread(target=do_translate_with_saved_lang, args=(call.message, uid, preferred_lang, message_id)).start()
    else:
        markup = generate_language_keyboard("translate_to", message_id)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Please select the language you want to translate into:",
            reply_markup=markup
        )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("btn_summarize|"))
def button_summarize_handler(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(call.from_user.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF when using summarize button ---
    user_tts_mode[uid] = None

    _, message_id_str = call.data.split("|", 1)
    message_id = int(message_id_str)

    if uid not in user_transcriptions or message_id not in user_transcriptions[uid]:
        bot.answer_callback_query(call.id, "❌ No transcription found for this message.")
        return

    preferred_lang = user_language_settings.get(uid)
    if preferred_lang:
        bot.answer_callback_query(call.id, "Summarizing with your preferred language...")
        threading.Thread(target=do_summarize_with_saved_lang, args=(call.message, uid, preferred_lang, message_id)).start()
    else:
        markup = generate_language_keyboard("summarize_in", message_id)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Please select the language you want the summary in:",
            reply_markup=markup
        )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("translate_to|"))
def callback_translate_to(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(call.from_user.id):
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
        text=f"Translating to **{lang}**...",
        parse_mode="Markdown"
    )

    if message_id:
        threading.Thread(target=do_translate_with_saved_lang, args=(call.message, uid, lang, message_id)).start()
    else:
        if uid in user_transcriptions and call.message.reply_to_message and call.message.reply_to_message.message_id in user_transcriptions[uid]:
            threading.Thread(target=do_translate_with_saved_lang, args=(call.message, uid, lang, call.message.reply_to_message.message_id)).start()
        else:
            bot.send_message(call.message.chat.id, "❌ No transcription found for this message to translate. Please use the inline buttons on the transcription.")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("summarize_in|"))
def callback_summarize_in(call):
    uid = str(call.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(call.from_user.id):
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
        text=f"Summarizing in **{lang}**...",
        parse_mode="Markdown"
    )

    if message_id:
        threading.Thread(target=do_summarize_with_saved_lang, args=(call.message, uid, lang, message_id)).start()
    else:
        if uid in user_transcriptions and call.message.reply_to_message and call.message.reply_to_message.message_id in user_transcriptions[uid]:
            threading.Thread(target=do_summarize_with_saved_lang, args=(call.message, uid, lang, call.message.reply_to_message.message_id)).start()
        else:
            bot.send_message(call.message.chat.id, "❌ No transcription found for this message to summarize. Please use the inline buttons on the transcription.")
    bot.answer_callback_query(call.id)

def do_translate_with_saved_lang(message, uid, lang, message_id):
    original = user_transcriptions.get(uid, {}).get(message_id, "")
    if not original:
        bot.send_message(message.chat.id, "❌ No transcription available for this specific message to translate.")
        return

    prompt = f"Translate the following text into {lang}. Provide only the translated text, with no additional notes, explanations, or introductory/concluding remarks:\n\n{original}"

    bot.send_chat_action(message.chat.id, 'typing')
    translated = ask_gemini(uid, prompt)

    if translated.startswith("Error:"):
        bot.send_message(message.chat.id, f"😓 Sorry, an error occurred during translation: {translated}. Please try again later.")
        return

    if len(translated) > 4000:
        fn = 'translation.txt'
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(translated)
        bot.send_chat_action(message.chat.id, 'upload_document')
        with open(fn, 'rb') as doc:
            bot.send_document(message.chat.id, doc, caption=f"Translation to {lang}", reply_to_message_id=message_id)
        os.remove(fn)
    else:
        bot.send_message(message.chat.id, translated, reply_to_message_id=message_id)

def do_summarize_with_saved_lang(message, uid, lang, message_id):
    original = user_transcriptions.get(uid, {}).get(message_id, "")
    if not original:
        bot.send_message(message.chat.id, "❌ No transcription available for this specific message to summarize.")
        return

    prompt = f"Summarize the following text in {lang}. Provide only the summarized text, with no additional notes, explanations, or different versions:\n\n{original}"

    bot.send_chat_action(message.chat.id, 'typing')
    summary = ask_gemini(uid, prompt)

    if summary.startswith("Error:"):
        bot.send_message(chat_id=message.chat.id, text=f"😓 Sorry, an error occurred during summarization: {summary}. Please try again later.")
        return

    if len(summary) > 4000:
        fn = 'summary.txt'
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(summary)
        bot.send_chat_action(message.chat.id, 'upload_document')
        with open(fn, 'rb') as doc:
            bot.send_document(message.chat.id, doc, caption=f"Summary in {lang}", reply_to_message_id=message_id)
        os.remove(fn)
    else:
        bot.send_message(message.chat.id, summary, reply_to_message_id=message_id)

@bot.message_handler(commands=['translate'])
def handle_translate(message):
    uid = str(message.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF on translate command ---
    user_tts_mode[uid] = None

    if not message.reply_to_message or uid not in user_transcriptions or message.reply_to_message.message_id not in user_transcriptions[uid]:
        return bot.send_message(message.chat.id, "❌ Please reply to a transcription message to translate it.")

    transcription_message_id = message.reply_to_message.message_id
    preferred_lang = user_language_settings.get(uid)
    if preferred_lang:
        threading.Thread(target=do_translate_with_saved_lang, args=(message, uid, preferred_lang, transcription_message_id)).start()
    else:
        markup = generate_language_keyboard("translate_to", transcription_message_id)
        bot.send_message(
            message.chat.id,
            "Please select the language you want to translate into:",
            reply_markup=markup
        )

@bot.message_handler(commands=['summarize'])
def handle_summarize(message):
    uid = str(message.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    # --- MODIFIED: Ensure TTS mode is OFF on summarize command ---
    user_tts_mode[uid] = None

    if not message.reply_to_message or uid not in user_transcriptions or message.reply_to_message.message_id not in user_transcriptions[uid]:
        return bot.send_message(message.chat.id, "❌ Please reply to a transcription message to summarize it.")

    transcription_message_id = message.reply_to_message.message_id
    preferred_lang = user_language_settings.get(uid)
    if preferred_lang:
        threading.Thread(target=do_summarize_with_saved_lang, args=(message, uid, preferred_lang, transcription_message_id)).start()
    else:
        markup = generate_language_keyboard("summarize_in", transcription_message_id)
        bot.send_message(
            message.chat.id,
            "Please select the language you want the summary in:",
            reply_markup=markup
        )

# --- NEW: Function to transcribe audio using SpeechRecognition ---
def transcribe_audio_with_speech_recognition(audio_path: str, lang_code: str) -> str | None:
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(audio_path) as source:
            audio_data = recognizer.record(source)
        # Google Web Speech API (free recognition) with language parameter
        # If necessary, adjust language to BCP-47. Here we pass just lang_code.
        text = recognizer.recognize_google(audio_data, language=lang_code)
        return text
    except sr.UnknownValueError:
        logging.error("Speech Recognition could not understand audio")
        return ""
    except sr.RequestError as e:
        logging.error(f"Could not request results from Speech Recognition service; {e}")
        return None
    except Exception as e:
        logging.error(f"Speech Recognition error: {e}")
        return None

# --- Memory Cleanup Function ---
def cleanup_old_data():
    """Cleans up user_transcriptions and user_memory older than 7 days."""
    seven_days_ago = datetime.now() - timedelta(days=7)

    keys_to_delete_transcriptions = []
    for user_id, transcriptions in user_transcriptions.items():
        if user_id in user_data and 'last_active' in user_data[user_id]:
            last_activity = datetime.fromisoformat(user_data[user_id]['last_active'])
            if last_activity < seven_days_ago:
                keys_to_delete_transcriptions.append(user_id)
        else: # If user_data doesn't have an entry or last_active, clean up if old
            keys_to_delete_transcriptions.append(user_id) # Consider old if no activity data

    for user_id in keys_to_delete_transcriptions:
        if user_id in user_transcriptions:
            del user_transcriptions[user_id]
            logging.info(f"Cleaned up old transcriptions for user {user_id}")

    keys_to_delete_memory = []
    for user_id in user_memory:
        if user_id in user_data and 'last_active' in user_data[user_id]:
            last_activity = datetime.fromisoformat(user_data[user_id]['last_active'])
            if last_activity < seven_days_ago:
                keys_to_delete_memory.append(user_id)
        else: # If user_data doesn't have an entry or last_active, clean up if old
            keys_to_delete_memory.append(user_id) # Consider old if no activity data

    for user_id in keys_to_delete_memory:
        if user_id in user_memory:
            del user_memory[user_id]
            logging.info(f"Cleaned up old chat memory for user {user_id}")

    # --- NEW: Also clean up TTS user preferences if user is inactive ---
    keys_to_delete_tts_users = []
    for user_id in tts_users:
        if user_id in user_data and 'last_active' in user_data[user_id]:
            last_activity = datetime.fromisoformat(user_data[user_id]['last_active'])
            if last_activity < seven_days_ago:
                keys_to_delete_tts_users.append(user_id)
        else: # If user_data doesn't have an entry or last_active, clean up if old
            keys_to_delete_tts_users.append(user_id) # Consider old if no activity data

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

    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    # --- End NEW check ---

    # --- MODIFIED: Check if a voice is set in user_tts_mode (it will be the voice name if set) ---
    if user_tts_mode.get(uid):  # If user has a voice selected for TTS
        threading.Thread(
            target=lambda: asyncio.run(synth_and_send_tts(message.chat.id, uid, message.text))
        ).start()
    elif uid in tts_users:  # User has a voice saved, but maybe didn't start with /text_to_speech
        user_tts_mode[uid] = tts_users[uid]  # Reactivate TTS mode with the saved voice
        threading.Thread(
            target=lambda: asyncio.run(synth_and_send_tts(message.chat.id, uid, message.text))
        ).start()
    else:  # User hasn't selected a voice yet for TTS
        bot.send_message(
            message.chat.id,
            "I only transcribe voice messages, audio, video, or video files. "
            "To convert text to speech, use the /text_to_speech command first."
        )

@bot.message_handler(func=lambda m: True, content_types=['photo', 'sticker', 'document'])
def fallback_non_text_or_media(message):
    uid = str(message.from_user.id)
    update_user_activity(uid)
    # --- MODIFIED: Check subscription only if transcription count is met ---
    if user_data.get(uid, {}).get('transcription_count', 0) >= 5 and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    # --- End NEW check ---

    # --- MODIFIED: Ensure TTS mode is OFF when a non-text/non-media message is sent ---
    user_tts_mode[uid] = None
    # --- END MODIFIED ---
    bot.send_message(
        message.chat.id,
        "Please send only voice messages, audio files, video notes, or video files for transcription, "
        "or use `/text_to_speech` for text to speech."
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
    cleanup_old_data()  # Start the cleanup timer
    set_webhook_on_startup()  # Set webhook when the application starts
    # Ensure Flask app runs on the port specified by Render (usually 8080)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
