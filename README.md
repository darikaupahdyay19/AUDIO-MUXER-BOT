# AudioMuxer Pro Bot

AudioMuxer Pro Bot is a versatile Telegram bot for muxing audio and video files using FFmpeg. It is designed to handle multiple audio tracks and provide asynchronous processing with progress tracking.

## Features
- Mux audio tracks into video files seamlessly.
- Support for multiple audio tracks and custom language tagging.
- Asynchronous processing with detailed progress bars.
- Simple, user-friendly Telegram interface.

## Prerequisites
- **Python 3.11+**
- **FFmpeg**: Must be installed and accessible in your system PATH.

## Telegram Bot Setup
1. Talk to [@BotFather](https://t.me/botfather) on Telegram to create a new bot and obtain your API Token.
2. (Optional but recommended) If you need to handle files larger than 50MB (up to 2GB), you must set up a Local Telegram Bot API server.

## Installation

### Local Setup
1. Clone this repository.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` (or create a `.env` file) and fill in your variables:
   - `BOT_TOKEN`: From BotFather
   - `API_ID`: From my.telegram.org
   - `API_HASH`: From my.telegram.org
   - `OWNER_ID`: Your Telegram User ID
4. Run the bot:
   ```bash
   python -m src.main
   ```

### Docker Setup
1. Ensure Docker and Docker Compose are installed on your machine.
2. Create and configure your `.env` file as described in the Local Setup.
3. Start the services using Docker Compose:
   ```bash
   docker-compose up -d --build
   ```

## Usage Examples
1. Start a chat with your bot and send `/start`.
2. Send a video file to the bot.
3. Reply to the video file or follow the prompts to send the audio track(s) you wish to mux.
4. The bot will download the files, perform the muxing operation using FFmpeg, and upload the resulting video back to you.

## Troubleshooting
- **Files too large**: By default, Telegram bots are restricted to a 50MB limit for downloads and uploads. To process larger files (up to 2GB), configure the Local Bot API Server in your `docker-compose.yml`.
- **FFmpeg not found**: Ensure FFmpeg is installed and the executable is in your system PATH. On Debian/Ubuntu, use `apt install ffmpeg`. On Windows, download the binaries and add them to your Environment Variables.
- **Bot not responding**: Check the console logs or Docker logs (`docker logs audiomuxer_bot`) for any API errors or missing environment variables.
