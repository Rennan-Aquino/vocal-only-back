import soundfile as sf
import numpy as np
import noisereduce as nr
from pathlib import Path
from .utils.logger import setup_logger
import subprocess
import os
import shutil
import time  # 🆕 IMPORT DO TEMPO

logger = setup_logger(__name__)

class VocalRefiner:
    """Refina vocais separados para melhor qualidade - VERSÃO RÁPIDA"""
    
    def __init__(self, ffmpeg_path: str = None):
        self.ffmpeg_path = ffmpeg_path or r"C:\Users\Rennan\tools\ffmpeg-master-latest-win64-gpl\ffmpeg-master-latest-win64-gpl\bin"
    
    def refine_with_ffmpeg(self, input_path: Path, output_path: Path):
        """Refina vocais usando FFmpeg - VERSÃO RÁPIDA E CONFIÁVEL"""
        try:
            ffmpeg_exe = os.path.join(self.ffmpeg_path, "ffmpeg.exe")
            
            # FILTROS SIMPLES, RÁPIDOS E COMPATÍVEIS
            filter_chain = (
                "highpass=60,"      # Remove graves
                "lowpass=8500,"      # Remove agudos extremos
                "compand=attacks=0.1:decays=0.3:points=-80/-80|-30/-10|0/0"  # Compressão
            )
            
            cmd = [
                ffmpeg_exe,
                '-i', str(input_path),
                '-af', filter_chain,
                '-y', str(output_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                raise Exception(f"FFmpeg refinement failed: {result.stderr}")
            
            logger.info(f"Vocais refinados com FFmpeg: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erro no refinamento FFmpeg: {e}")
            return False
    
    def refine_with_noisereduce(self, input_path: Path, output_path: Path):
        """Refina vocais usando noise reduction - VERSÃO CONFIÁVEL"""
        try:
            # Carrega o áudio
            data, sr = sf.read(input_path)
            
            # Verifica se o áudio é válido
            if len(data) < 1024:
                logger.warning(f"Áudio muito curto ({len(data)} amostras). Pulando noise reduction.")
                sf.write(output_path, data, sr)
                return True
            
            # Garante que é mono
            if data.ndim > 1:
                data = data.mean(axis=1)
            
            # Aplica noise reduction
            reduced_noise = nr.reduce_noise(
                y=data, 
                sr=sr,
                stationary=True,
                prop_decrease=0.9  # Redução moderada de ruído
            )
            
            # Salva o resultado
            sf.write(output_path, reduced_noise, sr)
            
            logger.info(f"Noise reduction aplicado: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erro no noise reduction: {e}")
            # Fallback: copia o arquivo original
            shutil.copy2(input_path, output_path)
            return True
    
    def full_refinement_pipeline(self, input_path: Path, output_dir: Path = None):
        """Pipeline completo de refinamento vocal - COM TIMING"""
        start_time = time.time()  # 🆕 MARCA TEMPO INICIAL
        
        try:
            if output_dir is None:
                output_dir = input_path.parent
            
            # Nome do arquivo de saída
            stem = input_path.stem
            output_path = output_dir / f"{stem}_refined.wav"
            
            logger.info(f"🚀 Iniciando refinamento de: {input_path.name}")
            
            # Primeiro noise reduction
            temp_path = output_dir / "temp_refined.wav"
            
            nr_start = time.time()
            if self.refine_with_noisereduce(input_path, temp_path):
                nr_time = time.time() - nr_start
                logger.info(f"✅ Noise reduction concluído em {nr_time:.2f}s")
                
                # Depois processamento com FFmpeg
                ffmpeg_start = time.time()
                if self.refine_with_ffmpeg(temp_path, output_path):
                    ffmpeg_time = time.time() - ffmpeg_start
                    logger.info(f"✅ FFmpeg processing concluído em {ffmpeg_time:.2f}s")
                    
                    # Remove arquivo temporário
                    if temp_path.exists():
                        temp_path.unlink()
                    
                    total_time = time.time() - start_time
                    logger.info(f"🎉 REFINAMENTO CONCLUÍDO! Tempo total: {total_time:.2f}s")
                    logger.info(f"📁 Arquivo final: {output_path}")
                    
                    return output_path
            
            # Fallback: copia o original se falhar
            shutil.copy2(input_path, output_path)
            total_time = time.time() - start_time
            logger.warning(f"⚠️  Fallback usado. Tempo total: {total_time:.2f}s")
            return output_path
            
        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"💥 Erro no pipeline após {total_time:.2f}s: {e}")
            # Fallback extremo
            return input_path

# Verificação do FFmpeg
try:
    ffmpeg_test = os.path.join(r"C:\Users\Rennan\tools\ffmpeg-master-latest-win64-gpl\ffmpeg-master-latest-win64-gpl\bin", "ffmpeg.exe")
    if os.path.exists(ffmpeg_test):
        logger.info("✅ FFmpeg encontrado com sucesso!")
    else:
        logger.warning("⚠️  FFmpeg não encontrado no caminho especificado")
except Exception as e:
    logger.error(f"💥 Erro ao verificar FFmpeg: {e}")