import argparse
from pathlib import Path
from time import sleep
from threading import Thread
from flask import Flask, request, jsonify, send_file, Response, stream_with_context
from flask_cors import CORS

from src.downloader import YouTubeDownloader
from src.separator import AudioSeparator
from src.vocal_refiner import VocalRefiner
from src.models.model_manager import ModelManager
from src.utils.logger import setup_logger
from src.utils.file_utils import safe_filename

app = Flask(__name__)

# Progresso por jobId
PROGRESS = {}

# CORS (ajuste as origens conforme seu front)
CORS(
    app,
    resources={r"/api/*": {"origins": ["http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:3000", "http://127.0.0.1:3000"]}},
    supports_credentials=True,
    methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

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

# ------------------------------------------------------------
# Health
# ------------------------------------------------------------
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'device': model_manager.device,
        'model_loaded': model_manager.model is not None
    })

# ------------------------------------------------------------
# SSE de progresso
# GET /api/progress/<job_id>
# ------------------------------------------------------------
@app.route("/api/progress/<job_id>")
def progress(job_id):
    def gen():
        last = -1
        while True:
            p = PROGRESS.get(job_id, 0)
            if p != last:
                # Envia tanto o valor numérico quanto um objeto JSON
                yield f"data: {p}\n\n"
                yield f"event: progress\ndata: {{\"percent\": {p}}}\n\n"
                last = p
            if p >= 100:
                yield "event: complete\ndata: {\"status\": \"completed\"}\n\n"
                break
            sleep(0.4)
        # Limpa o progresso após completar
        if job_id in PROGRESS:
            del PROGRESS[job_id]
    return Response(stream_with_context(gen()), mimetype="text/event-stream")

# ------------------------------------------------------------
# Separação principal
# POST /api/separate
# body: { youtube_url: string, refine_vocals?: bool, jobId?: string }
# ------------------------------------------------------------
@app.route('/api/separate', methods=['POST'])
def separate_audio():
    try:
        data = request.json or {}
        youtube_url = data.get('youtube_url')
        refine = bool(data.get('refine_vocals', False))
        job_id = data.get('jobId', 'default')

        if not youtube_url:
            return jsonify({'error': 'URL do YouTube não fornecida'}), 400

        # Inicializa o progresso
        if job_id:
            PROGRESS[job_id] = 0

        logger.info(f"[{job_id}] Baixando áudio… URL: {youtube_url}")
        
        # Função para atualizar progresso durante o download
        def download_progress_hook(progress):
            if job_id:
                # Mapeia o progresso do download (0-100) para 0-30 do progresso total
                PROGRESS[job_id] = progress * 0.3
                logger.info(f"[{job_id}] Progresso do download: {progress}%")
        
        audio_file = downloader.download_audio(youtube_url, progress_callback=download_progress_hook)
        if not audio_file:
            if job_id:
                PROGRESS[job_id] = 100
            return jsonify({'error': 'Falha ao baixar áudio do YouTube'}), 500

        # Atualiza progresso após download
        if job_id:
            PROGRESS[job_id] = 30

        logger.info(f"[{job_id}] Separando stems…")

        # Função para atualizar progresso durante a separação
        def separation_progress_hook(demucs_progress):
            if job_id:
                # O progresso do Demucs já está em 0-100%, mapeamos para 30-80% do progresso total
                total_progress = 30 + (demucs_progress * 0.5)
                PROGRESS[job_id] = total_progress
                logger.info(f"[{job_id}] Progresso do Demucs: {demucs_progress}% -> Progresso total: {total_progress:.1f}%")

        separated_files = separator.separate(audio_file, progress_callback=separation_progress_hook)

        if job_id:
            PROGRESS[job_id] = 80

        # No seu pipeline, 'other' é a faixa de voz
        vocals_path = Path(separated_files['other'])

        if refine:
            logger.info(f"[{job_id}] Refinando vocais…")
            
            # Função para atualizar progresso durante o refinamento
            def refinement_progress_hook(progress):
                if job_id:
                    # Mapeia o progresso do refinamento (0-100) para 80-100 do progresso total
                    PROGRESS[job_id] = 80 + (progress * 0.2)
                    logger.info(f"[{job_id}] Progresso do refinamento: {progress}%")
            
            refined_vocals = vocal_refiner.full_refinement_pipeline(
                vocals_path, 
                progress_callback=refinement_progress_hook
            )
            separated_files['vocals_refined'] = refined_vocals
            vocals_display = str(refined_vocals)
        else:
            vocals_display = str(vocals_path)

        if job_id:
            PROGRESS[job_id] = 100

        response = {
            'original': str(audio_file),
            'separated': {k: str(v) for k, v in separated_files.items()},
            'vocals': vocals_display,
            'instrumental': str(separated_files.get('drums', ''))
        }
        return jsonify(response)

    except Exception as e:
        logger.error(f"Erro no processamento: {e}")
        # Garante o fim da SSE
        try:
            if 'job_id' in locals() and job_id:
                PROGRESS[job_id] = 100
        except Exception:
            pass
        return jsonify({'error': str(e)}), 500

# ------------------------------------------------------------
# Refinamento posterior (opcional)
# ------------------------------------------------------------
@app.route('/api/refine', methods=['POST'])
def refine_vocals():
    try:
        data = request.json or {}
        vocals_path = data.get('vocals_path')
        job_id = data.get('jobId', 'default')
        
        if not vocals_path:
            return jsonify({'error': 'Caminho do vocal não fornecido'}), 400

        # Inicializa o progresso
        if job_id:
            PROGRESS[job_id] = 0
            
        # Função para atualizar progresso durante o refinamento
        def refinement_progress_hook(progress):
            if job_id:
                PROGRESS[job_id] = progress
                logger.info(f"[{job_id}] Progresso do refinamento: {progress}%")

        refined_path = vocal_refiner.full_refinement_pipeline(
            Path(vocals_path), 
            progress_callback=refinement_progress_hook
        )
        
        if job_id:
            PROGRESS[job_id] = 100
            
        return jsonify({
            'original': vocals_path,
            'refined': str(refined_path),
            'download_url': f'/api/download/{Path(refined_path).name}'
        })

    except Exception as e:
        logger.error(f"Erro no refinamento: {e}")
        # Garante o fim da SSE
        try:
            if 'job_id' in locals() and job_id:
                PROGRESS[job_id] = 100
        except Exception:
            pass
        return jsonify({'error': str(e)}), 500

# ------------------------------------------------------------
# Download por nome de arquivo
# GET /api/download/<filename>
# ------------------------------------------------------------
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

# ------------------------------------------------------------
# Limpar progresso (útil para desenvolvimento)
# ------------------------------------------------------------
@app.route('/api/clear-progress', methods=['POST'])
def clear_progress():
    global PROGRESS
    PROGRESS = {}
    return jsonify({'status': 'progress cleared'})

# ------------------------------------------------------------
# CLI (opcional)
# ------------------------------------------------------------
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
            logger.info("Refinando vocais…")
            vocals_path = Path(separated_files['other'])
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