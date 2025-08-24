import yt_dlp
from pathlib import Path
from typing import Optional
from .utils.logger import setup_logger
import subprocess
import os

logger = setup_logger(__name__)

FFMPEG_PATH = r"C:\Users\Rennan\tools\ffmpeg-master-latest-win64-gpl\ffmpeg-master-latest-win64-gpl\bin"
os.environ['PATH'] = FFMPEG_PATH + ';' + os.environ['PATH']

class YouTubeDownloader:
    
    def __init__(self, output_dir: Path = Path("downloads")):
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)
    
    def download_audio(self, youtube_url: str) -> Optional[Path]:
    
        try:
            try:
                return self._download_and_convert(youtube_url)
            except Exception as e:
                logger.warning(f"Tentativa 1 falhou: {e}")
            
            try:
                return self._download_direct(youtube_url)
            except Exception as e:
                logger.warning(f"Tentativa 2 falhou: {e}")
                raise Exception("Todas as tentativas de download falharam")
                
        except Exception as e:
            logger.error(f"Erro no download: {e}")
            return None
    
    def _download_and_convert(self, youtube_url: str) -> Path:
        try:
            output_base = self.output_dir / "audio_temp"
            
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]',
                'outtmpl': str(output_base) + '.%(ext)s',
                'restrictfilenames': True,
                'quiet': False,
            }
            
            logger.info(f"Baixando áudio como M4A: {youtube_url}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
                m4a_path = Path(ydl.prepare_filename(info))
            
            wav_path = m4a_path.with_suffix('.wav')
            logger.info(f"Convertendo {m4a_path} para WAV...")
            
            ffmpeg_exe = os.path.join(FFMPEG_PATH, "ffmpeg.exe")
            
            cmd = [
                ffmpeg_exe,
                '-i', str(m4a_path),
                '-ac', '2',
                '-ar', '44100',
                '-y',
                str(wav_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                raise Exception(f"FFmpeg falhou: {result.stderr}")
            
            if m4a_path.exists():
                m4a_path.unlink()
            
            logger.info(f"Conversão concluída: {wav_path}")
            return wav_path
            
        except Exception as e:
            self.cleanup_temp_files()
            raise e
    
    def _download_direct(self, youtube_url: str) -> Path:
        try:
            output_path = self.output_dir / "audio_direct.%(ext)s"
            
            ydl_opts = {
                'format': 'bestaudio',
                'outtmpl': str(output_path),
                'restrictfilenames': True,
                'quiet': False,
            }
            
            logger.info(f"Baixando áudio direto: {youtube_url}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
                audio_path = Path(ydl.prepare_filename(info))
            
            logger.info(f"Download direto concluído: {audio_path}")
            return audio_path
            
        except Exception as e:
            raise e
    
    def cleanup_temp_files(self):
        temp_patterns = ['audio_temp.*', 'audio_direct.*', '*.part', '*.ytdl']
        
        for pattern in temp_patterns:
            for temp_file in self.output_dir.glob(pattern):
                try:
                    temp_file.unlink()
                    logger.info(f"Arquivo temporário removido: {temp_file}")
                except:
                    pass

try:
    ffmpeg_test = os.path.join(FFMPEG_PATH, "ffmpeg.exe")
    if os.path.exists(ffmpeg_test):
        logger.info("FFmpeg encontrado com sucesso!")
    else:
        logger.warning("FFmpeg não encontrado no caminho especificado")
except Exception as e:
    logger.error(f"Erro ao verificar FFmpeg: {e}")