import torch
from demucs.pretrained import get_model
from ..utils.logger import setup_logger

logger = setup_logger(__name__)

class ModelManager:
    """Gerencia o carregamento e uso do modelo Demucs"""
    
    def __init__(self):
        self.model = None
        self.device = self._get_device()
        logger.info(f"Dispositivo selecionado: {self.device}")
    
    def _get_device(self) -> str:
        """Determina o melhor dispositivo disponível (CUDA, MPS ou CPU)"""
        if torch.cuda.is_available():
            return "cuda"
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return "mps"
        else:
            return "cpu"
    
    def load_model(self, model_name: str = 'htdemucs') -> None:
        """Carrega o modelo Demucs especificado"""
        try:
            logger.info(f"Carregando modelo: {model_name}")
            self.model = get_model(model_name)
            self.model.to(self.device)
            logger.info("Modelo carregado com sucesso!")
        except Exception as e:
            logger.error(f"Erro ao carregar modelo: {e}")
            raise
    
    def get_model(self):
        """Retorna o modelo carregado"""
        if self.model is None:
            raise ValueError("Modelo não foi carregado. Chame load_model() primeiro.")
        return self.model