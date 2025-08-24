import argparse
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from src.downloader import YouTubeDownloader
from src.separator import AudioSeparator
from src.vocal_refiner import VocalRefiner
from src.models.model_manager import ModelManager
from src.utils.logger import setup_logger
from src.utils.file_utils import safe_filename

app = Flask(__name__)
CORS(app)
logger = setup_logger(__name__)

model_manager = ModelManager()
downloader = YouTubeDownloader()
separator = AudioSeparator(model_manager)
vocal_refiner = VocalRefiner()

try:
    model_manager.load_model()
    logger.info("Aplicação inicializada com sucesso!")
except Exception as e:
    logger.error(f"Falha ao inicializar aplicação: {e}")
    exit(1)

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'device': model_manager.device,
        'model_loaded': model_manager.model is not None
    })

@app.route('/api/separate', methods=['POST'])
def separate_audio():
    try:
        data = request.json
        if not data or 'youtube_url' not in data:
            return jsonify({'error': 'URL do YouTube não fornecida'}), 400
        
        youtube_url = data['youtube_url']
        logger.info(f"Processando URL: {youtube_url}")
        
        audio_file = downloader.download_audio(youtube_url)
        if not audio_file:
            return jsonify({'error': 'Falha ao baixar áudio do YouTube'}), 500
        
        separated_files = separator.separate(audio_file)
        
        refine = data.get('refine_vocals', False)
        vocals_path = Path(separated_files['vocals'])
        
        if refine:
            logger.info("Refinando vocais...")
            refined_vocals = vocal_refiner.full_refinement_pipeline(vocals_path)
            separated_files['vocals_refined'] = refined_vocals
            vocals_display = str(refined_vocals)
        else:
            vocals_display = str(vocals_path)
        
        response = {
            'original': str(audio_file),
            'separated': {k: str(v) for k, v in separated_files.items()},
            'vocals': vocals_display,
            'instrumental': str(separated_files['drums'])
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Erro no processamento: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/refine', methods=['POST'])
def refine_vocals():
    try:
        data = request.json
        vocals_path = data.get('vocals_path')
        
        if not vocals_path:
            return jsonify({'error': 'Caminho do vocal não fornecido'}), 400
        
        refined_path = vocal_refiner.full_refinement_pipeline(Path(vocals_path))
        
        return jsonify({
            'original': vocals_path,
            'refined': str(refined_path),
            'download_url': f'/api/download/{refined_path.name}'
        })
        
    except Exception as e:
        logger.error(f"Erro no refinamento: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<path:filename>', methods=['GET'])
def download_file(filename):
    try:
        safe_name = safe_filename(filename)
        file_path = Path(safe_name)
        
        if not file_path.exists():
            for subdir in ['downloads', 'separated']:
                potential_path = Path(subdir) / safe_name
                if potential_path.exists():
                    file_path = potential_path
                    break
            
            if not file_path.exists():
                return jsonify({'error': 'Arquivo não encontrado'}), 404
        
        return send_file(file_path, as_attachment=True)
        
    except Exception as e:
        logger.error(f"Erro no download: {e}")
        return jsonify({'error': str(e)}), 500

def cli_handler():
    parser = argparse.ArgumentParser(description='Separar áudio do YouTube usando Demucs')
    parser.add_argument('youtube_url', help='URL do vídeo do YouTube')
    parser.add_argument('--output', '-o', default='separated', help='Diretório de saída')
    parser.add_argument('--refine', '-r', action='store_true', help='Refinar vocais')
    
    args = parser.parse_args()
    
    try:
        audio_file = downloader.download_audio(args.youtube_url)
        if not audio_file:
            logger.error("Falha no download do áudio")
            return
        
        separated_files = separator.separate(audio_file)
        
        if args.refine:
            logger.info("Refinando vocais...")
            vocals_path = Path(separated_files['vocals'])
            refined_vocals = vocal_refiner.full_refinement_pipeline(vocals_path)
            separated_files['vocals_refined'] = refined_vocals
        
        print("Processamento concluído com sucesso!")
        print(f"Arquivo original: {audio_file}")
        print("Arquivos separados:")
        for stem, path in separated_files.items():
            print(f"  {stem}: {path}")
            
    except Exception as e:
        logger.error(f"Erro: {e}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        cli_handler()
    else:
        app.run(host='0.0.0.0', port=5000, debug=True)