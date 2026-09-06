from flask import Flask, jsonify, request
from collector import (
    get_competitions,
    get_matches,
    analyze_match,
    analyze_team_history,
    analyze_prematch
)
from collector_2627 import (
    collector_2627_status
)
import requests

app = Flask(__name__)

API_NAME = "Football Intelligence API"
VERSION = "1.4.0"


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return jsonify({
        "api": API_NAME,
        "version": VERSION,
        "status": "online",
        "mode": "pre-match",
        "seasons": {
            "historical": "StatsBomb Open Data",
            "2026_27": "collector_2627"
        },
        "message": (
            "API própria de inteligência "
            "e análise de futebol"
        )
    })


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "version": VERSION
    })


# =========================================================
# INFORMAÇÕES DA API
# =========================================================

@app.route("/api/v1/info")
def info():
    return jsonify({
        "api": API_NAME,
        "version": VERSION,

        "markets": [
            "gols",
            "xg",
            "escanteios",
            "finalizacoes",
            "chutes_no_gol",
            "cartoes",
            "faltas"
        ],

        "modules": [
            "partida",
            "historico",
            "ultimos_5",
            "ultimos_10",
            "casa_fora",
            "frequencias",
            "produzido_x_cedido",
            "pre_match",
            "confidence_score",
            "ranking_oportunidades",
            "temporada_2026_27"
        ],

        "future_modules": [
            "jogadores",
            "arbitro",
            "contexto"
        ],

        "integrity": {
            "missing_data": None,
            "invent_missing_values": False,
            "hit_rates_require_match_data": True,
            "cross_average_is_hit_rate": False,
            "minimum_valid_games": 4,
            "minimum_coverage": 0.80
        }
    })


# =========================================================
# STATUS 2026/27
# =========================================================

@app.route("/api/v1/2627/status")
def status_2627():
    try:
        result = collector_2627_status()

        return jsonify({
            "api": API_NAME,
            "version": VERSION,
            **result
        })

    except Exception as error:
        return jsonify({
            "status": "error",
            "season": "2026/27",
            "error": str(error)
        }), 500


# =========================================================
# COMPETIÇÕES HISTÓRICAS
# =========================================================

@app.route("/api/v1/competitions")
def competitions():
    try:
        data = get_competitions()

        result = []

        for item in data:
            result.append({
                "competition_id":
                    item.get("competition_id"),

                "competition":
                    item.get("competition_name"),

                "country":
                    item.get("country_name"),

                "season_id":
                    item.get("season_id"),

                "season":
                    item.get("season_name")
            })

        return jsonify({
            "status": "ok",
            "total": len(result),
            "competitions": result
        })

    except requests.exceptions.RequestException as error:
        return jsonify({
            "status": "source_error",
            "error": str(error)
        }), 502

    except Exception as error:
        return jsonify({
            "status": "error",
            "error": str(error)
        }), 500


# =========================================================
# PARTIDAS HISTÓRICAS
# =========================================================

@app.route(
    "/api/v1/competitions/"
    "<int:competition_id>/seasons/"
    "<int:season_id>/matches"
)
def matches(competition_id, season_id):
    try:
        data = get_matches(
            competition_id,
            season_id
        )

        result = []

        for match in data:
            home = match.get(
                "home_team", {}
            )

            away = match.get(
                "away_team", {}
            )

            competition = match.get(
                "competition", {}
            )

            season = match.get(
                "season", {}
            )

            result.append({
                "match_id":
                    match.get("match_id"),

                "date":
                    match.get("match_date"),

                "kick_off":
                    match.get("kick_off"),

                "competition":
                    competition.get(
                        "competition_name"
                    ),

                "season":
                    season.get(
                        "season_name"
                    ),

                "home":
                    home.get(
                        "home_team_name"
                    ),

                "away":
                    away.get(
                        "away_team_name"
                    ),

                "home_score":
                    match.get("home_score"),

                "away_score":
                    match.get("away_score")
            })

        return jsonify({
            "status": "ok",
            "competition_id":
                competition_id,
            "season_id":
                season_id,
            "total":
                len(result),
            "matches":
                result
        })

    except requests.exceptions.RequestException as error:
        return jsonify({
            "status": "source_error",
            "error": str(error)
        }), 502

    except Exception as error:
        return jsonify({
            "status": "error",
            "error": str(error)
        }), 500


# =========================================================
# ESTATÍSTICAS DE UMA PARTIDA
# =========================================================

@app.route("/api/v1/match/<int:match_id>/stats")
def match_stats(match_id):
    try:
        result = analyze_match(
            match_id
        )

        return jsonify({
            "status": "ok",
            **result
        })

    except requests.exceptions.HTTPError as error:
        status_code = (
            error.response.status_code
            if error.response is not None
            else None
        )

        if status_code == 404:
            return jsonify({
                "status": "not_found",
                "match_id": match_id,
                "error":
                    "Partida não encontrada na fonte."
            }), 404

        return jsonify({
            "status": "source_error",
            "match_id": match_id,
            "error": str(error)
        }), 502

    except requests.exceptions.RequestException as error:
        return jsonify({
            "status": "source_error",
            "match_id": match_id,
            "error": str(error)
        }), 502

    except Exception as error:
        return jsonify({
            "status": "error",
            "match_id": match_id,
            "error": str(error)
        }), 500


# =========================================================
# HISTÓRICO DO TIME
# =========================================================

@app.route("/api/v1/team/history")
def team_history():
    try:
        competition_id = request.args.get(
            "competition_id",
            type=int
        )

        season_id = request.args.get(
            "season_id",
            type=int
        )

        team = request.args.get(
            "team",
            type=str
        )

        limit = request.args.get(
            "limit",
            default=10,
            type=int
        )

        venue = request.args.get(
            "venue",
            default="all",
            type=str
        )

        if competition_id is None:
            return jsonify({
                "status": "invalid_request",
                "error":
                    "competition_id é obrigatório"
            }), 400

        if season_id is None:
            return jsonify({
                "status": "invalid_request",
                "error":
                    "season_id é obrigatório"
            }), 400

        if not team:
            return jsonify({
                "status": "invalid_request",
                "error":
                    "team é obrigatório"
            }), 400

        if limit not in [5, 10]:
            return jsonify({
                "status": "invalid_request",
                "error":
                    "limit deve ser 5 ou 10"
            }), 400

        if venue not in [
            "all",
            "home",
            "away"
        ]:
            return jsonify({
                "status": "invalid_request",
                "error":
                    "venue deve ser all, home ou away"
            }), 400

        result = analyze_team_history(
            competition_id=
                competition_id,

            season_id=
                season_id,

            team_name=
                team,

            limit=
                limit,

            venue=
                venue
        )

        return jsonify({
            "status": "ok",
            **result
        })

    except requests.exceptions.RequestException as error:
        return jsonify({
            "status": "source_error",
            "error": str(error)
        }), 502

    except Exception as error:
        return jsonify({
            "status": "error",
            "error": str(error)
        }), 500


# =========================================================
# ANÁLISE PRÉ-JOGO
# =========================================================

@app.route("/api/v1/prematch")
def prematch():
    try:
        competition_id = request.args.get(
            "competition_id",
            type=int
        )

        season_id = request.args.get(
            "season_id",
            type=int
        )

        home_team = request.args.get(
            "home",
            type=str
        )

        away_team = request.args.get(
            "away",
            type=str
        )

        limit = request.args.get(
            "limit",
            default=5,
            type=int
        )

        if competition_id is None:
            return jsonify({
                "status": "invalid_request",
                "error":
                    "competition_id é obrigatório"
            }), 400

        if season_id is None:
            return jsonify({
                "status": "invalid_request",
                "error":
                    "season_id é obrigatório"
            }), 400

        if not home_team:
            return jsonify({
                "status": "invalid_request",
                "error":
                    "home é obrigatório"
            }), 400

        if not away_team:
            return jsonify({
                "status": "invalid_request",
                "error":
                    "away é obrigatório"
            }), 400

        if limit not in [5, 10]:
            return jsonify({
                "status": "invalid_request",
                "error":
                    "limit deve ser 5 ou 10"
            }), 400

        result = analyze_prematch(
            competition_id=
                competition_id,

            season_id=
                season_id,

            home_team=
                home_team,

            away_team=
                away_team,

            limit=
                limit
        )

        return jsonify({
            "status": "ok",
            **result
        })

    except requests.exceptions.RequestException as error:
        return jsonify({
            "status": "source_error",
            "error": str(error)
        }), 502

    except Exception as error:
        return jsonify({
            "status": "error",
            "error": str(error)
        }), 500


# =========================================================
# EXECUÇÃO LOCAL
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )
