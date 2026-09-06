from flask import Flask, jsonify

app = Flask(__name__)

API_NAME = "Football Intelligence API"
VERSION = "1.0.0"


@app.route("/")
def home():
    return jsonify({
        "api": API_NAME,
        "version": VERSION,
        "status": "online",
        "mode": "pre-match",
        "message": "API própria de inteligência e análise de futebol"
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "version": VERSION
    })


@app.route("/api/v1/info")
def info():
    return jsonify({
        "api": API_NAME,
        "version": VERSION,
        "project": "Analisador pré-jogo de futebol",
        "markets": [
            "gols",
            "escanteios",
            "finalizacoes",
            "chutes_no_gol",
            "cartoes",
            "faltas"
        ],
        "samples": [
            "ultimos_5",
            "ultimos_10",
            "casa_fora"
        ],
        "analysis": [
            "produzido_x_cedido",
            "frequencias_reais",
            "confidence_score",
            "jogadores",
            "arbitro",
            "contexto"
        ],
        "integrity": {
            "missing_data": "null",
            "invent_missing_values": False,
            "calculate_hit_rates_from_match_data": True
        }
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )
