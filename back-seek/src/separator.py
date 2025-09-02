import torch
from demucs.apply import apply_model
from pathlib import Path
from typing import Dict, Callable
from .utils.logger import setup_logger
from .models.model_manager import ModelManager
import soundfile as sf
import numpy as np
import torchaudio
import time
import re
import sys
from io import StringIO

logger = setup_logger(__name__)

class DemucsProgressCapture(StringIO):
    """Captura a saída do Demucs e extrai o progresso real"""
    def __init__(self, progress_callback=None):
        super().__init__()
        self.progress_callback = progress_callback
        self.buffer = ""
        
    def write(self, text):
        self.buffer += text
        # Processa o buffer para encontrar o progresso
        self._process_buffer()
        
    def _process_buffer(self):
        """Processa o buffer para extrair o progresso da barra do Demucs"""
        lines = self.buffer.split('\r')
        if lines:
            last_line = lines[-1].strip()
            
            # Padrão da barra de progresso do Demucs: "XX%|█████| XXX/XXX [XX:XX<XX:XX, X.XXs/it]"
            progress_match = re.search(r'(\d+)%\|', last_line)
            if progress_match:
                progress = int(progress_match.group(1))
                if self.progress_callback:
                    self.progress_callback(progress)
            
            # Também loga a linha completa
            if last_line and '%|' in last_line:
                logger.info(f"Demucs: {last_line}")
                
        # Limpa o buffer se ficar muito grande
        if len(self.buffer) > 1000:
            self.buffer = ""

class AudioSeparator:
    
    def __init__(self, model_manager: ModelManager, output_dir: Path = Path("separated")):
        self.model_manager = model_manager
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)
    
    def _load_audio(self, audio_path: Path):
        try:
            logger.info(f"Carregando áudio: {audio_path}")
            
            try:
                data, sr = sf.read(str(audio_path))
                logger.info(f"Soundfile carregou: {data.shape}, SR: {sr}")
            except Exception as e:
                logger.warning(f"Soundfile falhou: {e}, tentando torchaudio")
                wav, sr = torchaudio.load(str(audio_path))
                data = wav.numpy().squeeze()
            
            if data.ndim == 1:
                logger.info("Convertendo mono para estéreo")
                data = np.stack([data, data], axis=1)  # [samples, 2]
            elif data.ndim == 2 and data.shape[1] == 2:
                logger.info("Áudio já é estéreo - mantendo")
            elif data.ndim == 2 and data.shape[1] > 2:
                logger.info(f"Convertendo {data.shape[1]} canais para estéreo")
                data = data.mean(axis=1, keepdims=True)  # Primeiro converte para mono
                data = np.repeat(data, 2, axis=1)  # Depois converte para estéreo
            
            data = data.astype(np.float32)
            
            # Converte para tensor do PyTorch no formato [canais, samples]
            wav = torch.from_numpy(data).float().transpose(0, 1)  # [2, samples]
            
            # Resample se necessário
            model = self.model_manager.get_model()
            if sr != model.samplerate:
                from torchaudio.transforms import Resample
                resampler = Resample(sr, model.samplerate)
                wav = resampler(wav)
            
            logger.info(f"Áudio carregado: {wav.shape}, SR: {model.samplerate}")
            return wav
            
        except Exception as e:
            logger.error(f"Erro ao carregar áudio: {e}")
            raise
    
    def separate(self, audio_path: Path, progress_callback: Callable = None) -> Dict[str, Path]:
        """
        Separa o áudio em componentes (vocals, drums, bass, other)
        """
        try:
            # Carregar áudio
            wav = self._load_audio(audio_path)
            model = self.model_manager.get_model()
            
            # Aplicar modelo com captura de progresso
            logger.info("Iniciando separação de áudio...")
            start_time = time.time()
            
            # Configura captura de progresso
            progress_capture = DemucsProgressCapture(progress_callback)
            original_stdout = sys.stdout
            
            with torch.no_grad():
                # Redireciona a saída padrão para capturar o progresso
                sys.stdout = progress_capture
                try:
                    sources = apply_model(
                        model, 
                        wav.unsqueeze(0),  # Adiciona dimensão batch [1, 2, samples]
                        device=self.model_manager.device,
                        progress=True
                    )
                finally:
                    # Restaura a saída padrão
                    sys.stdout = original_stdout
            
            separation_time = time.time() - start_time
            logger.info(f"Separação concluída em {separation_time:.2f} segundos")
            
            if progress_callback:
                progress_callback(100)  # 100% após separação completa
            
            # Salvar resultados
            stem_names = ['vocals', 'drums', 'bass', 'other']
            result_files = {}
            
            for i, stem in enumerate(stem_names):
                output_file = self.output_dir / f"{audio_path.stem}_{stem}.mp3"
                
                # Pega o áudio e converte para [samples, canais] para soundfile
                audio_data = sources[0, i].cpu().numpy()  # [2, samples]
                audio_data = audio_data.transpose(1, 0)  # [samples, 2]
                
                sf.write(str(output_file), audio_data, model.samplerate)
                
                result_files[stem] = output_file
                logger.info(f"Componente '{stem}' salvo: {output_file}")
            
            return result_files
            
        except Exception as e:
            # Garante que a saída padrão seja restaurada mesmo em caso de erro
            if 'original_stdout' in locals():
                sys.stdout = original_stdout
            logger.error(f"Erro na separação de áudio: {e}")
            raise