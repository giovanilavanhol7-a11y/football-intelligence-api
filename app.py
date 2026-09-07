from flask import Flask, jsonify, request
from collector import (
    get_competitions,
    get_matches,
    analyze_match,
    analyze_team_history,
    analyze_prematch
)
from collector_2627 import (
    collector_2627_status,
    fixtures_2627_by_date,
    get_sportmonks_fixture,
    analyze_fixture_2627,
    analyze_team_history_2627,
    match_coverage
)
import requests


app = Flask(__name__)

API_NAME = "Football Intelligence API"
VERSION = "1.8.0"


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
            "2026_27": "Sportmonks"
        },
        "message": "API própria de inteligência e análise de futebol"
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
# INFO
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
            "temporada_2026_27",
            "fixtures_2026_27",
            "fixture_raw_2026_27",
            "fixture_stats_2026_27",
            "team_history_2026_27"
        ],

        "future_modules": [
            "prematch_2026_27",
            "jogadores",
            "arbitro",
            "contexto",
            "storage_2026_27"
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
# FIXTURES 2026/27 POR DATA
# =========================================================

@app.route("/api/v1/2627/fixtures")
def fixtures_2627():
    try:
        date = request.args.get(
            "date",
            type=str
        )

        if not date:
            return jsonify({
                "status": "invalid_request",
                "error": "date é obrigatório. Use YYYY-MM-DD."
            }), 400

        result = fixtures_2627_by_date(
            date
        )

        return jsonify({
            "status": "ok",
            **result
        })

    except ValueError as error:
        return jsonify({
            "status": "invalid_request",
            "error": str(error)
        }), 400

    except requests.exceptions.RequestException as error:
        return jsonify({
            "status": "source_error",
            "source": "Sportmonks",
            "error": str(error)
        }), 502

    except Exception as error:
        return jsonify({
            "status": "error",
            "error": str(error)
        }), 500


# =========================================================
# FIXTURE BRUTA 2026/27
# =========================================================

@app.route("/api/v1/2627/fixture/<int:fixture_id>/raw")
def fixture_2627_raw(fixture_id):
    try:
        fixture = get_sportmonks_fixture(
            fixture_id
        )

        if not fixture:
            return jsonify({
                "status": "not_found",
                "fixture_id": fixture_id
            }), 404

        return jsonify({
            "status": "ok",
            "season": "2026/27",
            "source": "Sportmonks",
            "fixture_id": fixture_id,
            "fixture": fixture
        })

    except requests.exceptions.RequestException as error:
        return jsonify({
            "status": "source_error",
            "source": "Sportmonks",
            "fixture_id": fixture_id,
            "error": str(error)
        }), 502

    except Exception as error:
        return jsonify({
            "status": "error",
            "fixture_id": fixture_id,
            "error": str(error)
        }), 500


# =========================================================
# ESTATÍSTICAS NORMALIZADAS 2026/27
# =========================================================

@app.route("/api/v1/2627/fixture/<int:fixture_id>/stats")
def fixture_2627_stats(fixture_id):
    try:
        result = analyze_fixture_2627(
            fixture_id
        )

        if not result:
            return jsonify({
                "status": "not_found",
                "fixture_id": fixture_id
            }), 404

        coverage = match_coverage(
            result
        )

        return jsonify({
            "status": "ok",
            "api": API_NAME,
            "version": VERSION,
            "season": "2026/27",
            "source": "Sportmonks",
            "fixture_id": fixture_id,

            "match": {
                "name": result.get("name"),
                "date": result.get("date"),
                "kick_off": result.get("kick_off"),
                "status": result.get("status"),
                "league_id": result.get("league_id"),
                "season_id": result.get("season_id")
            },

            "teams": result.get(
                "teams",
                {}
            ),

            "coverage": coverage,

            "integrity": {
                "missing_values_invented": False,
                "null_means_missing": True,
                "zero_means_confirmed_zero": True,
                "hit_rates_inferred_from_averages": False
            },

            "parser": result.get(
                "stat_parser",
                {}
            )
        })

    except requests.exceptions.RequestException as error:
        return jsonify({
            "status": "source_error",
            "source": "Sportmonks",
            "fixture_id": fixture_id,
            "error": str(error)
        }), 502

    except Exception as error:
        return jsonify({
            "status": "error",
            "fixture_id": fixture_id,
            "error": str(error)
        }), 500


# =========================================================
# HISTÓRICO REAL 2026/27 POR TIME
# =========================================================

@app.route("/api/v1/2627/team/<int:team_id>/history")
def team_history_2627(team_id):
    try:
        season_id = request.args.get(
            "season_id",
            type=int
        )

        limit = request.args.get(
            "limit",
            default=5,
            type=int
        )

        venue = request.args.get(
            "venue",
            default="all",
            type=str
        )

        before_date = request.args.get(
            "before_date",
            default=None,
            type=str
        )

        if season_id is None:
            return jsonify({
                "status": "invalid_request",
                "error": "season_id é obrigatório"
            }), 400

        if limit not in [5, 10]:
            return jsonify({
                "status": "invalid_request",
                "error": "limit deve ser 5 ou 10"
            }), 400

        if venue not in [
            "all",
            "home",
            "away"
        ]:
            return jsonify({
                "status": "invalid_request",
                "error": "venue deve ser all, home ou away"
            }), 400

        result = analyze_team_history_2627(
            team_id=team_id,
            season_id=season_id,
            limit=limit,
            venue=venue,
            before_date=before_date
        )

        return jsonify({
            "status": "ok",
            "api": API_NAME,
            "version": VERSION,
            **result
        })

    except ValueError as error:
        return jsonify({
            "status": "invalid_request",
            "error": str(error)
        }), 400

    except requests.exceptions.RequestException as error:
        return jsonify({
            "status": "source_error",
            "source": "Sportmonks",
            "team_id": team_id,
            "error": str(error)
        }), 502

    except Exception as error:
        return jsonify({
            "status": "error",
            "team_id": team_id,
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
                "home_team",
                {}
            )

            away = match.get(
                "away_team",
                {}
            )

            competition = match.get(
                "competition",
                {}
            )

            season = match.get(
                "season",
                {}
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
                    match.get(
                        "home_score"
                    ),

                "away_score":
                    match.get(
                        "away_score"
                    )
            })

        return jsonify({
            "status": "ok",
            "competition_id": competition_id,
            "season_id": season_id,
            "total": len(result),
            "matches": result
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
# ESTATÍSTICAS HISTÓRICAS
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
                "error": "Partida não encontrada na fonte."
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
# HISTÓRICO DO TIME — STATSBOMB
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
                "error": "competition_id é obrigatório"
            }), 400

        if season_id is None:
            return jsonify({
                "status": "invalid_request",
                "error": "season_id é obrigatório"
            }), 400

        if not team:
            return jsonify({
                "status": "invalid_request",
                "error": "team é obrigatório"
            }), 400

        if limit not in [5, 10]:
            return jsonify({
                "status": "invalid_request",
                "error": "limit deve ser 5 ou 10"
            }), 400

        if venue not in [
            "all",
            "home",
            "away"
        ]:
            return jsonify({
                "status": "invalid_request",
                "error": "venue deve ser all, home ou away"
            }), 400

        result = analyze_team_history(
            competition_id=competition_id,
            season_id=season_id,
            team_name=team,
            limit=limit,
            venue=venue
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
# PRÉ-JOGO HISTÓRICO
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
                "error": "competition_id é obrigatório"
            }), 400

        if season_id is None:
            return jsonify({
                "status": "invalid_request",
                "error": "season_id é obrigatório"
            }), 400

        if not home_team:
            return jsonify({
                "status": "invalid_request",
                "error": "home é obrigatório"
            }), 400

        if not away_team:
            return jsonify({
                "status": "invalid_request",
                "error": "away é obrigatório"
            }), 400

        if limit not in [5, 10]:
            return jsonify({
                "status": "invalid_request",
                "error": "limit deve ser 5 ou 10"
            }), 400

        result = analyze_prematch(
            competition_id=competition_id,
            season_id=season_id,
            home_team=home_team,
            away_team=away_team,
            limit=limit
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
