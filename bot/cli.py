import argparse
import asyncio
import sys
import os
from bot.config import ensure_directories, DB_PATH
from models.database import init_db
from core.ffmpeg_engine import FFmpegEngine
from core.track_manager import TrackManager
from core.sync_detector import SyncDetector
from core.trimmer import Trimmer

def setup_parser():
    parser = argparse.ArgumentParser(description="AudioMuxer Pro Bot CLI")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    # info
    info_p = subparsers.add_parser("info", help="Show file info")
    info_p.add_argument("-i", "--input", required=True, help="Input file path")

    # extract-audio
    extract_p = subparsers.add_parser("extract-audio", help="Extract audio from video")
    extract_p.add_argument("-i", "--input", required=True)
    extract_p.add_argument("-o", "--output", required=True)
    extract_p.add_argument("-t", "--track", type=int, default=0)
    extract_p.add_argument("--codec", default="copy")
    extract_p.add_argument("--bitrate", default="192k")

    # add-audio
    add_p = subparsers.add_parser("add-audio", help="Add audio to video")
    add_p.add_argument("-i", "--input", required=True)
    add_p.add_argument("-a", "--audio", required=True)
    add_p.add_argument("-o", "--output", required=True)
    add_p.add_argument("-l", "--language", default="eng")
    add_p.add_argument("--label")
    add_p.add_argument("--default", action="store_true")

    # replace-audio
    replace_p = subparsers.add_parser("replace-audio", help="Replace audio track")
    replace_p.add_argument("-i", "--input", required=True)
    replace_p.add_argument("-a", "--audio", required=True)
    replace_p.add_argument("-o", "--output", required=True)
    replace_p.add_argument("-t", "--track", type=int, default=0)

    # remove-audio
    remove_p = subparsers.add_parser("remove-audio", help="Remove audio track")
    remove_p.add_argument("-i", "--input", required=True)
    remove_p.add_argument("-o", "--output", required=True)
    remove_p.add_argument("-t", "--track", type=int, required=True)

    # list-tracks
    list_p = subparsers.add_parser("list-tracks", help="List tracks")
    list_p.add_argument("-i", "--input", required=True)

    # sync-detect
    sync_d_p = subparsers.add_parser("sync-detect", help="Detect offset")
    sync_d_p.add_argument("-r", "--reference", required=True)
    sync_d_p.add_argument("-t", "--target", required=True)

    # sync-fix
    sync_f_p = subparsers.add_parser("sync-fix", help="Auto-fix sync")
    sync_f_p.add_argument("-r", "--reference", required=True)
    sync_f_p.add_argument("-t", "--target", required=True)
    sync_f_p.add_argument("-o", "--output", required=True)
    sync_f_p.add_argument("--method", choices=["cross_correlation", "waveform"], default="cross_correlation")

    # trim
    trim_p = subparsers.add_parser("trim", help="Trim file")
    trim_p.add_argument("-i", "--input", required=True)
    trim_p.add_argument("-o", "--output", required=True)
    trim_p.add_argument("-s", "--start", type=float, required=True)
    trim_p.add_argument("-e", "--end", type=float, required=True)

    # remove-silence
    rs_p = subparsers.add_parser("remove-silence", help="Remove silence")
    rs_p.add_argument("-i", "--input", required=True)
    rs_p.add_argument("-o", "--output", required=True)
    rs_p.add_argument("--threshold", type=float, default=-40.0)
    rs_p.add_argument("--min-duration", type=float, default=0.5)

    # convert
    conv_p = subparsers.add_parser("convert", help="Convert audio")
    conv_p.add_argument("-i", "--input", required=True)
    conv_p.add_argument("-o", "--output", required=True)
    conv_p.add_argument("--bitrate", default="192k")
    conv_p.add_argument("--sample-rate", type=int, default=48000)

    # normalize
    norm_p = subparsers.add_parser("normalize", help="Normalize audio")
    norm_p.add_argument("-i", "--input", required=True)
    norm_p.add_argument("-o", "--output", required=True)
    norm_p.add_argument("--target", type=float, default=-16.0)

    # volume
    vol_p = subparsers.add_parser("volume", help="Adjust volume")
    vol_p.add_argument("-i", "--input", required=True)
    vol_p.add_argument("-o", "--output", required=True)
    vol_p.add_argument("--gain", type=float, required=True)

    return parser

async def run_command(args):
    ensure_directories()
    await init_db(DB_PATH)
    
    engine = FFmpegEngine()
    track_manager = TrackManager(engine)
    sync_detector = SyncDetector(engine)
    trimmer = Trimmer(engine)
    
    ok, _ = await engine.check_installation()
    if not ok:
        print("❌ FFmpeg not found!")
        sys.exit(1)
        
    def progress_callback(progress: float):
        bar_len = 30
        filled = int(bar_len * progress / 100)
        bar = '█' * filled + '-' * (bar_len - filled)
        sys.stdout.write(f'\r🔄 Processing: [{bar}] {progress:.1f}%')
        sys.stdout.flush()

    try:
        cmd = args.command
        if cmd == "info":
            # Just print info
            print(f"ℹ️ Getting info for {args.input}")
            # Mock print for now
            print("Done")
        elif cmd == "extract-audio":
            await engine.extract_audio(args.input, args.output, progress_callback=progress_callback)
            print(f"\n✅ Extracted audio to {args.output}")
        elif cmd == "add-audio":
            await track_manager.add_audio_track(args.input, args.audio, args.output, args.language, args.label, args.default, progress_callback)
            print(f"\n✅ Added audio to {args.output}")
        elif cmd == "replace-audio":
            await track_manager.replace_audio_track(args.input, args.audio, args.output, args.track, progress_callback)
            print(f"\n✅ Replaced audio to {args.output}")
        elif cmd == "remove-audio":
            await track_manager.remove_audio_track(args.input, args.output, args.track, progress_callback)
            print(f"\n✅ Removed audio track {args.track}")
        elif cmd == "list-tracks":
            print(f"📋 Listing tracks for {args.input}")
        elif cmd == "sync-detect":
            offset = await sync_detector.detect_offset(args.reference, args.target)
            print(f"\n✅ Detected offset: {offset} ms")
        elif cmd == "sync-fix":
            await sync_detector.auto_fix_sync(args.target, args.output, reference_path=args.reference, method=args.method, progress_callback=progress_callback)
            print(f"\n✅ Synced output saved to {args.output}")
        elif cmd == "trim":
            await trimmer.trim_media(args.input, args.output, args.start, args.end, progress_callback)
            print(f"\n✅ Trimmed media saved to {args.output}")
        elif cmd == "remove-silence":
            await trimmer.remove_silence(args.input, args.output, args.threshold, args.min_duration, progress_callback)
            print(f"\n✅ Media saved to {args.output}")
        elif cmd == "convert":
            await engine.convert_audio(args.input, args.output, args.bitrate, args.sample_rate, progress_callback)
            print(f"\n✅ Converted media saved to {args.output}")
        elif cmd == "normalize":
            await engine.normalize_audio(args.input, args.output, args.target, progress_callback)
            print(f"\n✅ Normalized media saved to {args.output}")
        elif cmd == "volume":
            await engine.adjust_volume(args.input, args.output, args.gain, progress_callback)
            print(f"\n✅ Adjusted volume media saved to {args.output}")
        else:
            print("❌ Unknown command")
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        sys.exit(1)

def cli_main():
    parser = setup_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
        
    asyncio.run(run_command(args))

if __name__ == "__main__":
    cli_main()
