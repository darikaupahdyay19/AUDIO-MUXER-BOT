import asyncio
import logging
import os
import tempfile
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
from telegram.request import HTTPXRequest

from bot.config import (
    TELEGRAM_BOT_TOKEN, LOCAL_API_SERVER, LOCAL_MODE, TEMP_DIR,
    DB_PATH, MAX_CONCURRENT_JOBS, VIDEO_FORMATS, AUDIO_FORMATS,
    LANGUAGE_CODES, QUALITY_PRESETS, ensure_directories,
    SILENCE_THRESHOLD_DB, SILENCE_MIN_DURATION
)
from core.ffmpeg_engine import FFmpegEngine
from core.file_validator import FileValidator
from core.track_manager import TrackManager
from core.sync_detector import SyncDetector
from core.trimmer import Trimmer
from core.audio_analyzer import AudioAnalyzer
from models.database import JobRepository, init_db
from models.schemas import JobStatus, Operation
from utils.helpers import (
    format_duration, format_file_size, generate_job_id,
    format_progress_bar, format_media_info
)
from utils.cleanup import start_cleanup_daemon

logger = logging.getLogger(__name__)

# Conversation states
(STATE_MAIN_MENU, STATE_WAITING_VIDEO, STATE_WAITING_AUDIO,
 STATE_VIDEO_OPTIONS, STATE_AUDIO_OPTIONS, STATE_SYNC_OPTIONS,
 STATE_TRIM_OPTIONS, STATE_TRACK_OPTIONS, STATE_WAITING_LANGUAGE,
 STATE_WAITING_LABEL, STATE_WAITING_TRIM_TIMES,
 STATE_WAITING_MANUAL_OFFSET, STATE_CONFIRM) = range(13)

class AudioMuxerBot:
    def __init__(self):
        self.engine = FFmpegEngine()
        self.validator = FileValidator(self.engine)
        self.track_manager = TrackManager(self.engine)
        self.sync_detector = SyncDetector(self.engine)
        self.trimmer = Trimmer(self.engine)
        self.analyzer = AudioAnalyzer(self.engine)
        self.job_repo = JobRepository(DB_PATH)
        self.job_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
    
    def build_application(self) -> Application:
        """Build and configure the Telegram Application."""
        builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
        
        if LOCAL_MODE:
            request = HTTPXRequest(connect_timeout=60, read_timeout=1200, write_timeout=1200, pool_timeout=60)
            builder = (builder
                .base_url(f'{LOCAL_API_SERVER}')
                .base_file_url(f'{LOCAL_API_SERVER.replace("/bot", "/file/bot")}')
                .local_mode(True)
                .request(request))
        
        app = builder.build()
        self._register_handlers(app)
        return app
    
    def _register_handlers(self, app: Application):
        """Register all command and callback handlers."""
        app.add_handler(CommandHandler('start', self.cmd_start))
        app.add_handler(CommandHandler('help', self.cmd_help))
        app.add_handler(CommandHandler('status', self.cmd_status))
        app.add_handler(CommandHandler('cancel', self.cmd_cancel))
        app.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO | filters.Document.ALL, self.handle_file))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main menu with all operation categories."""
        keyboard = [
            [InlineKeyboardButton('🎬 Video Operations', callback_data='menu_video'),
             InlineKeyboardButton('🎵 Audio Operations', callback_data='menu_audio')],
            [InlineKeyboardButton('🔄 Sync Operations', callback_data='menu_sync'),
             InlineKeyboardButton('✂️ Trim Operations', callback_data='menu_trim')],
            [InlineKeyboardButton('🌍 Language & Tracks', callback_data='menu_tracks')],
            [InlineKeyboardButton('ℹ️ Help', callback_data='help'),
             InlineKeyboardButton('📊 Status', callback_data='status')],
        ]
        text = (
            '🎵 *AudioMuxer Pro Bot*\n\n'
            'Welcome! I can help you with:\n'
            '• Extract, add, replace audio tracks\n'
            '• Auto-detect and fix audio sync issues\n'
            '• Trim video/audio and remove silence\n'
            '• Manage multi-language audio tracks\n\n'
            'Send me a video or audio file, or choose an operation:'
        )
        if update.message:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = "🤖 *AudioMuxer Help*\n\nSupported Video Formats: mp4, mkv, avi, mov\nSupported Audio Formats: mp3, aac, wav, flac, ogg\n\nSend a file to get started!"
        if update.message:
            await update.message.reply_text(text, parse_mode='Markdown')
        else:
            await update.callback_query.edit_message_text(text, parse_mode='Markdown')
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        jobs = await self.job_repo.get_user_jobs(user_id, limit=5)
        if not jobs:
            msg = "No recent jobs found."
        else:
            status_text = "📊 *Recent Jobs*\n\n"
            for j in jobs:
                status_text += f"ID: `{j.id}`\nOp: {j.operation}\nStatus: {j.status}\n\n"
            msg = status_text
        if update.message:
            await update.message.reply_text(msg, parse_mode='Markdown')
        else:
            await update.callback_query.edit_message_text(msg, parse_mode='Markdown')
    
    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.clear()
        if update.message:
            await update.message.reply_text('❌ Operation cancelled. Send /start to begin again.')
    
    async def handle_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        document = message.document or message.video or message.audio
        if not document:
            return
        
        file_id = document.file_id
        file_name = getattr(document, 'file_name', f'file_{file_id}')
        
        await message.reply_text(f"⬇️ Downloading {file_name}...")
        
        new_file = await context.bot.get_file(file_id)
        file_path = os.path.join(TEMP_DIR, file_name)
        await new_file.download_to_drive(file_path)
        
        # Determine file type
        ext = os.path.splitext(file_name)[1].lower().strip('.')
        is_video = ext in VIDEO_FORMATS
        is_audio = ext in AUDIO_FORMATS
        
        if not (is_video or is_audio):
            await message.reply_text(f"❌ Unsupported format: {ext}")
            return
            
        media_info = await self.validator.validate_file(file_path)
        if not media_info:
            await message.reply_text("❌ Failed to parse media file.")
            return
            
        info_text = format_media_info(media_info)
        
        if is_video:
            context.user_data['video_path'] = file_path
            keyboard = [
                [InlineKeyboardButton('🎵 Extract Audio', callback_data='op_extract_audio'),
                 InlineKeyboardButton('➕ Add Audio Track', callback_data='op_add_audio')],
                [InlineKeyboardButton('🔄 Replace Audio', callback_data='op_replace_audio'),
                 InlineKeyboardButton('🔄 Sync Fix', callback_data='op_sync_fix')],
                [InlineKeyboardButton('✂️ Trim Video', callback_data='op_trim_time'),
                 InlineKeyboardButton('📋 List Tracks', callback_data='op_list_tracks')],
                [InlineKeyboardButton('❌ Cancel', callback_data='confirm_no')],
            ]
        else:
            context.user_data['audio_path'] = file_path
            keyboard = [
                [InlineKeyboardButton('🔄 Convert Format', callback_data='op_convert'),
                 InlineKeyboardButton('🎚️ Adjust Volume', callback_data='op_volume')],
                [InlineKeyboardButton('🔇 Remove Silence', callback_data='op_remove_silence'),
                 InlineKeyboardButton('✂️ Trim Audio', callback_data='op_trim_audio')],
                [InlineKeyboardButton('❌ Cancel', callback_data='confirm_no')],
            ]
        
        await message.reply_text(f"✅ File analyzed!\n\n{info_text}\n\nWhat would you like to do?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        
        if data.startswith('menu_'):
            await self._show_submenu(query, context, data)
        elif data.startswith('op_'):
            await self._handle_operation(query, context, data)
        elif data.startswith('lang_'):
            await self._handle_language_select(query, context, data)
        elif data.startswith('preset_'):
            await self._handle_preset_select(query, context, data)
        elif data.startswith('fmt_'):
            await self._handle_format_select(query, context, data)
        elif data == 'confirm_yes':
            await self._execute_operation(query, context)
        elif data == 'confirm_no':
            await query.edit_message_text('❌ Operation cancelled.')
            context.user_data.clear()
        elif data == 'back_main':
            await self._show_main_menu(query, context)
        elif data == 'help':
            await self.cmd_help(update, context)
        elif data == 'status':
            await self.cmd_status(update, context)
    
    async def _show_submenu(self, query, context, data):
        menu_type = data.replace('menu_', '')
        if menu_type == 'video':
            keyboard = [
                [InlineKeyboardButton('📤 Send Video File', callback_data='op_send_video')],
                [InlineKeyboardButton('🎵 Extract Audio', callback_data='op_extract_audio'),
                 InlineKeyboardButton('➕ Add Audio Track', callback_data='op_add_audio')],
                [InlineKeyboardButton('🔄 Replace Audio', callback_data='op_replace_audio'),
                 InlineKeyboardButton('📋 List Audio Tracks', callback_data='op_list_tracks')],
                [InlineKeyboardButton('⬅️ Back', callback_data='back_main')],
            ]
            await query.edit_message_text('🎬 *Video Operations*\nChoose an operation or send a video file:', reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        elif menu_type == 'audio':
            keyboard = [
                [InlineKeyboardButton('📤 Send Audio File', callback_data='op_send_audio')],
                [InlineKeyboardButton('🎚️ Adjust Volume', callback_data='op_volume'),
                 InlineKeyboardButton('🔄 Convert Format', callback_data='op_convert')],
                [InlineKeyboardButton('📏 Normalize', callback_data='op_normalize'),
                 InlineKeyboardButton('✂️ Trim Audio', callback_data='op_trim_audio')],
                [InlineKeyboardButton('⬅️ Back', callback_data='back_main')],
            ]
            await query.edit_message_text('🎵 *Audio Operations*\nChoose an operation or send an audio file:', reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        elif menu_type == 'sync':
            keyboard = [
                [InlineKeyboardButton('🔍 Auto-Detect Sync', callback_data='op_sync_detect')],
                [InlineKeyboardButton('⚡ Quick Sync (Auto-fix)', callback_data='op_sync_fix')],
                [InlineKeyboardButton('🎯 Manual Sync', callback_data='op_sync_manual')],
                [InlineKeyboardButton('📊 Sync Report', callback_data='op_sync_report')],
                [InlineKeyboardButton('⬅️ Back', callback_data='back_main')],
            ]
            await query.edit_message_text('🔄 *Sync Operations*\nChoose a sync operation:', reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        elif menu_type == 'trim':
            keyboard = [
                [InlineKeyboardButton('⏱️ Trim by Time', callback_data='op_trim_time')],
                [InlineKeyboardButton('🔇 Remove Silence', callback_data='op_remove_silence')],
                [InlineKeyboardButton('🎯 Smart Trim', callback_data='op_smart_trim')],
                [InlineKeyboardButton('📐 Trim to Match', callback_data='op_trim_match')],
                [InlineKeyboardButton('⬅️ Back', callback_data='back_main')],
            ]
            await query.edit_message_text('✂️ *Trim Operations*\nChoose a trim operation:', reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        elif menu_type == 'tracks':
            keyboard = [
                [InlineKeyboardButton('➕ Add Language Track', callback_data='op_add_lang_track')],
                [InlineKeyboardButton('🏷️ Label Audio Track', callback_data='op_label_track'),
                 InlineKeyboardButton('📝 Set Default Track', callback_data='op_set_default')],
                [InlineKeyboardButton('🔀 Reorder Tracks', callback_data='op_reorder_tracks')],
                [InlineKeyboardButton('⬅️ Back', callback_data='back_main')],
            ]
            await query.edit_message_text('🌍 *Language & Tracks*\nManage audio tracks:', reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    async def _handle_operation(self, query, context, data):
        op = data.replace('op_', '')
        context.user_data['operation'] = op
        
        video_ops = ('send_video', 'extract_audio', 'add_audio', 'replace_audio', 'list_tracks',
                  'sync_detect', 'sync_fix', 'sync_manual', 'sync_report',
                  'trim_time', 'remove_silence', 'smart_trim', 'trim_match',
                  'add_lang_track', 'label_track', 'set_default', 'reorder_tracks')
        
        audio_ops = ('send_audio', 'volume', 'convert', 'normalize', 'trim_audio')
        
        if op in video_ops:
            if 'video_path' not in context.user_data:
                await query.edit_message_text('📤 Please send me the video file to process.')
                context.user_data['waiting_for'] = 'video'
                return
        
        if op in audio_ops:
            if 'audio_path' not in context.user_data:
                await query.edit_message_text('📤 Please send me the audio file to process.')
                context.user_data['waiting_for'] = 'audio'
                return
        
        await self._proceed_with_operation(query, context, op)
    
    async def _proceed_with_operation(self, query_or_msg, context, op):
        if op == 'extract_audio':
            keyboard = [[InlineKeyboardButton(fmt.upper(), callback_data=f'fmt_{fmt}') for fmt in ['mp3', 'aac', 'wav']]]
            keyboard.append([InlineKeyboardButton('❌ Cancel', callback_data='confirm_no')])
            await query_or_msg.edit_message_text('Select output format:', reply_markup=InlineKeyboardMarkup(keyboard))
        elif op == 'trim_time':
            context.user_data['waiting_for'] = 'trim_times'
            await query_or_msg.edit_message_text('Reply with start and end times in seconds separated by comma (e.g. 10,25):')
        elif op == 'volume':
            context.user_data['waiting_for'] = 'volume_gain'
            await query_or_msg.edit_message_text('Reply with volume gain in dB (e.g. 5 or -3):')
        else:
            keyboard = [
                [InlineKeyboardButton('✅ Confirm', callback_data='confirm_yes')],
                [InlineKeyboardButton('❌ Cancel', callback_data='confirm_no')]
            ]
            await query_or_msg.edit_message_text(f'Proceed with operation: {op}?', reply_markup=InlineKeyboardMarkup(keyboard))

    async def _handle_format_select(self, query, context, data):
        fmt = data.replace('fmt_', '')
        context.user_data['output_format'] = fmt
        await self._execute_operation(query, context)
        
    async def _handle_language_select(self, query, context, data):
        lang = data.replace('lang_', '')
        context.user_data['language'] = lang
        await self._execute_operation(query, context)
        
    async def _handle_preset_select(self, query, context, data):
        preset = data.replace('preset_', '')
        context.user_data['preset'] = preset
        await self._execute_operation(query, context)
    
    async def _execute_operation(self, query, context):
        op = context.user_data.get('operation', '')
        job_id = generate_job_id()
        user_id = str(query.from_user.id)
        chat_id = str(query.message.chat_id)
        
        await self.job_repo.create_job(job_id, user_id, chat_id, op, context.user_data)
        
        msg = await query.edit_message_text(f'⏳ Processing... {format_progress_bar(0)}')
        
        async def progress_callback(progress: float):
            try:
                await msg.edit_text(f'⏳ Processing... {format_progress_bar(progress)}')
            except Exception:
                pass
        
        try:
            async with self.job_semaphore:
                await self.job_repo.update_progress(job_id, 'PROCESSING', 0)
                output_path = await self._run_operation(context, progress_callback)
                await self.job_repo.complete_job(job_id, output_path)
            
            keyboard = [[InlineKeyboardButton('🔙 Main Menu', callback_data='back_main')]]
            await msg.edit_text(f'✅ Processing complete!', reply_markup=InlineKeyboardMarkup(keyboard))
            
            if output_path and os.path.exists(output_path):
                await context.bot.send_document(chat_id=chat_id, document=open(output_path, 'rb'), filename=Path(output_path).name)
        except Exception as e:
            logger.exception(f'Job {job_id} failed')
            await self.job_repo.fail_job(job_id, str(e))
            await msg.edit_text(f'❌ Processing failed: {e}')
        finally:
            context.user_data.clear()
    
    async def _run_operation(self, context, progress_callback) -> str:
        op = context.user_data['operation']
        output_dir = tempfile.mkdtemp(dir=TEMP_DIR)
        
        if op == 'extract_audio':
            video_path = context.user_data['video_path']
            fmt = context.user_data.get('output_format', 'mp3')
            output_path = os.path.join(output_dir, f'extracted.{fmt}')
            await self.engine.extract_audio(video_path, output_path, progress_callback=progress_callback)
            return output_path
        elif op == 'trim_time':
            video_path = context.user_data['video_path']
            start_time, end_time = context.user_data['trim_times']
            output_path = os.path.join(output_dir, f'trimmed.mp4')
            await self.trimmer.trim_media(video_path, output_path, start_time, end_time, progress_callback=progress_callback)
            return output_path
        elif op == 'volume':
            audio_path = context.user_data['audio_path']
            gain = context.user_data['volume_gain']
            output_path = os.path.join(output_dir, f'vol_adjusted.mp3')
            await self.engine.adjust_volume(audio_path, output_path, gain, progress_callback=progress_callback)
            return output_path
        elif op == 'sync_fix':
            video_path = context.user_data['video_path']
            output_path = os.path.join(output_dir, f'synced.mp4')
            await self.sync_detector.auto_fix_sync(video_path, output_path, progress_callback=progress_callback)
            return output_path
            
        raise NotImplementedError(f"Operation {op} not fully implemented in bot yet.")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        waiting_for = context.user_data.get('waiting_for', '')
        text = update.message.text
        
        if waiting_for == 'trim_times':
            try:
                parts = text.split(',')
                start = float(parts[0].strip())
                end = float(parts[1].strip())
                context.user_data['trim_times'] = (start, end)
                
                keyboard = [
                    [InlineKeyboardButton('✅ Confirm', callback_data='confirm_yes')],
                    [InlineKeyboardButton('❌ Cancel', callback_data='confirm_no')]
                ]
                await update.message.reply_text(f'Trim from {start}s to {end}s?', reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception:
                await update.message.reply_text('Invalid format. Please send like: 10,25')
        elif waiting_for == 'volume_gain':
            try:
                gain = float(text.strip())
                context.user_data['volume_gain'] = gain
                keyboard = [
                    [InlineKeyboardButton('✅ Confirm', callback_data='confirm_yes')],
                    [InlineKeyboardButton('❌ Cancel', callback_data='confirm_no')]
                ]
                await update.message.reply_text(f'Adjust volume by {gain}dB?', reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception:
                await update.message.reply_text('Invalid format. Please send a number like 5 or -3')
        else:
            await update.message.reply_text('Send /start to begin, or send a video/audio file.')
    
    async def _show_main_menu(self, query, context):
        context.user_data.clear()
        keyboard = [
            [InlineKeyboardButton('🎬 Video Operations', callback_data='menu_video'),
             InlineKeyboardButton('🎵 Audio Operations', callback_data='menu_audio')],
            [InlineKeyboardButton('🔄 Sync Operations', callback_data='menu_sync'),
             InlineKeyboardButton('✂️ Trim Operations', callback_data='menu_trim')],
            [InlineKeyboardButton('🌍 Language & Tracks', callback_data='menu_tracks')],
        ]
        await query.edit_message_text('🎵 *AudioMuxer Pro Bot*\nChoose an operation:', reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def run_bot():
    """Initialize and run the Telegram bot."""
    ensure_directories()
    await init_db(DB_PATH)
    
    bot = AudioMuxerBot()
    ok, version = await bot.engine.check_installation()
    if not ok:
        logger.error('FFmpeg not found! Please install FFmpeg.')
        return
    logger.info(f'FFmpeg found: {version}')
    
    await start_cleanup_daemon(TEMP_DIR)
    
    app = bot.build_application()
    logger.info('AudioMuxer Pro Bot starting...')
    await app.run_polling(drop_pending_updates=True)
