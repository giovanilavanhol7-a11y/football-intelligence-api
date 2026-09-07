import os
import requests
from datetime import datetime

SPORTMONKS_BASE_URL = "https://api.sportmonks.com/v3/football"
SPORTMONKS_API_TOKEN = os.getenv("SPORTMONKS_API_TOKEN")

TIMEOUT = 25
SEASON = "2026/27"

MIN_VALID_SAMPLE = 4
MIN_COVERAGE = 0.80

INTEGRITY_NOTE_2627 = (
    "Dados 2026/27 somente entram na Football Intelligence API "
    "quando confirmados pela fonte. Valores ausentes permanecem null. "
    "Frequências X/5/X/10 não são criadas a partir de médias."
)

STAT_FIELDS = [
    "goals",
    "xg",
    "shots",
    "shots_on_target",
    "corners",
    "fouls_committed",
    "yellow_cards",
    "red_cards"
]


# =========================================================
# UTILIDADES
# =========================================================

def is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def normalize_number(value):
    if value is None:
        return None

    if is_number(value):
        return value

    try:
        text = str(value).strip()

        if not text:
            return None

        number = float(
            text.replace(",", ".")
        )

        if number.is_integer():
            return int(number)

        return round(number, 3)

    except (TypeError, ValueError):
        return None


def empty_stats():
    return {
        "goals": None,
        "xg": None,
        "shots": None,
        "shots_on_target": None,
        "corners": None,
        "fouls_committed": None,
        "yellow_cards": None,
        "red_cards": None
    }


def normalize_stats(stats):
    if not isinstance(stats, dict):
        stats = {}

    result = empty_stats()

    for field in STAT_FIELDS:
        result[field] = normalize_number(
            stats.get(field)
        )

    return result


# =========================================================
# SPORTMONKS
# =========================================================

def sportmonks_request(endpoint, params=None):
    if not SPORTMONKS_API_TOKEN:
        raise RuntimeError(
            "SPORTMONKS_API_TOKEN não configurado no servidor."
        )

    query = dict(params or {})

    query["api_token"] = SPORTMONKS_API_TOKEN

    url = (
        f"{SPORTMONKS_BASE_URL}/"
        f"{endpoint.lstrip('/')}"
    )

    response = requests.get(
        url,
        params=query,
        timeout=TIMEOUT
    )

    # Nunca devolvemos o token ao cliente.
    if response.status_code == 401:
        raise RuntimeError(
            "Sportmonks recusou o token (HTTP 401)."
        )

    if response.status_code == 403:
        raise RuntimeError(
            "Sportmonks bloqueou o recurso para este plano (HTTP 403)."
        )

    response.raise_for_status()

    return response.json()


# =========================================================
# TESTE REAL DA CONEXÃO
# =========================================================

def test_sportmonks_connection():
    if not SPORTMONKS_API_TOKEN:
        return {
            "connected": False,
            "authenticated": False,
            "reason": "token_not_configured"
        }

    try:
        payload = sportmonks_request(
            "fixtures",
            {
                "per_page": 1
            }
        )

        data = payload.get("data", [])

        if not isinstance(data, list):
            return {
                "connected": True,
                "authenticated": True,
                "response_valid": False,
                "fixtures_received": 0
            }

        return {
            "connected": True,
            "authenticated": True,
            "response_valid": True,
            "fixtures_received": len(data)
        }

    except requests.exceptions.HTTPError as error:
        status_code = (
            error.response.status_code
            if error.response is not None
            else None
        )

        return {
            "connected": False,
            "authenticated": False,
            "http_status": status_code,
            "reason": "sportmonks_http_error"
        }

    except requests.exceptions.RequestException as error:
        return {
            "connected": False,
            "authenticated": False,
            "reason": "network_error",
            "error": str(error)
        }

    except Exception as error:
        return {
            "connected": False,
            "authenticated": False,
            "reason": "connection_error",
            "error": str(error)
        }


# =========================================================
# FIXTURES SPORTMONKS
# =========================================================

def get_sportmonks_fixtures_by_date(date):
    try:
        datetime.strptime(
            date,
            "%Y-%m-%d"
        )
    except (TypeError, ValueError):
        raise ValueError(
            "Data deve estar no formato YYYY-MM-DD."
        )

    payload = sportmonks_request(
        f"fixtures/date/{date}",
        {
            "include": "participants;state"
        }
    )

    data = payload.get("data", [])

    if not isinstance(data, list):
        return []

    return data


def get_sportmonks_fixture(fixture_id):
    payload = sportmonks_request(
        f"fixtures/{fixture_id}",
        {
            "include": (
                "participants;"
                "state;"
                "scores;"
                "statistics.type"
            )
        }
    )

    return payload.get("data")


# =========================================================
# PARTICIPANTES
# =========================================================

def extract_participants(fixture):
    home = None
    away = None

    participants = fixture.get(
        "participants",
        []
    )

    for participant in participants:
        meta = participant.get(
            "meta",
            {}
        )

        location = meta.get(
            "location"
        )

        item = {
            "id": participant.get("id"),
            "name": participant.get("name"),
            "short_code": participant.get(
                "short_code"
            )
        }

        if location == "home":
            home = item

        elif location == "away":
            away = item

    return home, away


# =========================================================
# NORMALIZAÇÃO DE FIXTURE
# =========================================================

def normalize_sportmonks_fixture(fixture):
    if not isinstance(fixture, dict):
        return None

    home, away = extract_participants(
        fixture
    )

    state = fixture.get(
        "state",
        {}
    )

    return {
        "match_id": fixture.get("id"),

        "source_match_id":
            fixture.get("id"),

        "source":
            "Sportmonks",

        "season":
            SEASON,

        "league_id":
            fixture.get("league_id"),

        "season_id":
            fixture.get("season_id"),

        "date":
            (
                fixture.get(
                    "starting_at",
                    ""
                )[:10]
                if fixture.get(
                    "starting_at"
                )
                else None
            ),

        "kick_off":
            fixture.get(
                "starting_at"
            ),

        "status":
            state.get("state")
            if isinstance(state, dict)
            else None,

        "name":
            fixture.get("name"),

        "home_team":
            home,

        "away_team":
            away,

        "result_info":
            fixture.get(
                "result_info"
            )
    }


# =========================================================
# FIXTURES POR DATA NORMALIZADAS
# =========================================================

def fixtures_2627_by_date(date):
    raw_fixtures = (
        get_sportmonks_fixtures_by_date(
            date
        )
    )

    fixtures = []

    for raw in raw_fixtures:
        normalized = (
            normalize_sportmonks_fixture(
                raw
            )
        )

        if normalized:
            fixtures.append(
                normalized
            )

    return {
        "season": SEASON,
        "date": date,
        "source": "Sportmonks",
        "total": len(fixtures),
        "fixtures": fixtures
    }


# =========================================================
# COBERTURA
# =========================================================

def stats_coverage(stats):
    if not isinstance(stats, dict):
        stats = {}

    available = sum(
        1
        for field in STAT_FIELDS
        if is_number(
            stats.get(field)
        )
    )

    total = len(STAT_FIELDS)

    return {
        "available": available,
        "total": total,
        "coverage": round(
            available / total * 100,
            1
        )
    }


def sample_quality(actual, requested):
    if (
        not isinstance(actual, int)
        or not isinstance(requested, int)
        or requested <= 0
    ):
        return {
            "valid": False,
            "coverage": None,
            "status": "insufficient_data"
        }

    coverage_ratio = (
        actual / requested
    )

    valid = (
        actual >= MIN_VALID_SAMPLE
        and
        coverage_ratio >= MIN_COVERAGE
    )

    return {
        "valid": valid,
        "matches": actual,
        "requested": requested,
        "coverage": round(
            coverage_ratio * 100,
            1
        ),
        "status": (
            "valid"
            if valid
            else "insufficient_data"
        )
    }


# =========================================================
# STATUS 2026/27
# =========================================================

def collector_2627_status():
    connection = (
        test_sportmonks_connection()
    )

    return {
        "status": (
            "ready"
            if connection.get(
                "connected"
            )
            else "source_not_connected"
        ),

        "season": SEASON,

        "mode": "2026_27",

        "data_source":
            "Sportmonks",

        "data_source_connected":
            connection.get(
                "connected",
                False
            ),

        "authenticated":
            connection.get(
                "authenticated",
                False
            ),

        "storage_connected":
            False,

        "supported_stats":
            STAT_FIELDS,

        "connection_test":
            connection,

        "integrity": {
            "missing_values_invented":
                False,

            "zero_is_missing":
                False,

            "null_is_missing":
                True,

            "minimum_valid_games":
                MIN_VALID_SAMPLE,

            "minimum_coverage":
                MIN_COVERAGE,

            "integrity_note":
                INTEGRITY_NOTE_2627
        },

        "next_step": (
            "Validar fixtures reais 2026/27 "
            "e depois normalizar estatisticas."
        )
    }
