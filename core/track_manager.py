from models.schemas import AudioTrack
from core.ffmpeg_engine import FFmpegEngine

class TrackManager:
    def __init__(self, ffmpeg_engine: 'FFmpegEngine'):
        self.engine = ffmpeg_engine
    
    async def list_audio_tracks(self, file_path: str) -> list['AudioTrack']:
        """List all audio tracks with metadata."""
        probe_data = await self.engine.probe(file_path)
        tracks = []
        for i, stream in enumerate(probe_data.get('streams', [])):
            if stream.get('codec_type') == 'audio':
                tags = stream.get('tags', {})
                disposition = stream.get('disposition', {})
                tracks.append(AudioTrack(
                    index=stream.get('index', i),
                    codec=stream.get('codec_name', 'unknown'),
                    channels=stream.get('channels', 2),
                    language=tags.get('language', 'und'),
                    title=tags.get('title'),
                    is_default=bool(disposition.get('default', 0))
                ))
        return tracks
    
    async def set_default_track(self, file_path: str, output_path: str, track_index: int) -> bool:
        """Set a specific audio track as the default."""
        tracks = await self.list_audio_tracks(file_path)
        cmd = [self.engine.ffmpeg, '-y', '-i', file_path, '-map', '0', '-c', 'copy']
        
        # We need to map to output stream indices. Audio streams start from 0 among audio streams.
        # But ffmpeg metadata/disposition indexing works on the stream type.
        for t in tracks:
            # t.index is the absolute stream index in the file. 
            # To set disposition we can use -disposition:a:N
            a_idx = next(i for i, tr in enumerate(tracks) if tr.index == t.index)
            if t.index == track_index:
                cmd.extend([f'-disposition:a:{a_idx}', 'default'])
            else:
                cmd.extend([f'-disposition:a:{a_idx}', '0'])
                
        cmd.append(output_path)
        ok, _ = await self.engine._run(cmd)
        return ok
    
    async def reorder_tracks(self, file_path: str, output_path: str, new_order: list[int]) -> bool:
        """Reorder audio tracks by specifying new index order."""
        # Map video and subtitle streams first
        cmd = [self.engine.ffmpeg, '-y', '-i', file_path]
        
        probe_data = await self.engine.probe(file_path)
        streams = probe_data.get('streams', [])
        
        # map video/subtitle streams
        for s in streams:
            if s.get('codec_type') != 'audio':
                cmd.extend(['-map', f"0:{s['index']}"])
                
        # map audio streams in new order
        for idx in new_order:
            cmd.extend(['-map', f"0:{idx}"])
            
        cmd.extend(['-c', 'copy', output_path])
        ok, _ = await self.engine._run(cmd)
        return ok
    
    async def label_track(self, file_path: str, output_path: str, track_index: int, title: str | None = None, language: str | None = None) -> bool:
        """Set title and/or language metadata for a specific audio track."""
        tracks = await self.list_audio_tracks(file_path)
        
        try:
            a_idx = next(i for i, t in enumerate(tracks) if t.index == track_index)
        except StopIteration:
            return False
            
        cmd = [self.engine.ffmpeg, '-y', '-i', file_path, '-map', '0', '-c', 'copy']
        if title is not None:
            cmd.extend([f'-metadata:s:a:{a_idx}', f'title={title}'])
        if language is not None:
            cmd.extend([f'-metadata:s:a:{a_idx}', f'language={language}'])
            
        cmd.append(output_path)
        ok, _ = await self.engine._run(cmd)
        return ok
    
    async def duplicate_track(self, file_path: str, output_path: str, track_index: int) -> bool:
        """Duplicate a specific audio track."""
        cmd = [self.engine.ffmpeg, '-y', '-i', file_path, '-map', '0', '-map', f'0:{track_index}', '-c', 'copy', output_path]
        ok, _ = await self.engine._run(cmd)
        return ok
