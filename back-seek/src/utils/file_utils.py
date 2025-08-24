import os
import re
from pathlib import Path
from typing import List

def safe_filename(filename: str) -> str:
    """Remove caracteres inválidos de nomes de arquivo"""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

def ensure_directory(directory_path: Path) -> None:
    """Garante que um diretório existe"""
    directory_path.mkdir(parents=True, exist_ok=True)

def get_audio_files(directory: Path, extensions: List[str] = None) -> List[Path]:
    """Retorna lista de arquivos de áudio em um diretório"""
    if extensions is None:
        extensions = ['.wav', '.mp3', '.flac', '.m4a']
    
    return [f for f in directory.iterdir() if f.is_file() and f.suffix.lower() in extensions]