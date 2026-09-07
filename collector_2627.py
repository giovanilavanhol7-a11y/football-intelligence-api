import os
import requests
from datetime import datetime, timedelta


# =========================================================
# CONFIGURAÇÃO
# =========================================================

SPORTMONKS_BASE_URL = "https://api.sportmonks.com/v3/football"
SPORTMONKS_API_TOKEN = os.getenv("SPORTMONKS_API_TOKEN")

TIMEOUT = 30
SEASON = "2026/27"

MIN_VALID_SAMPLE = 4
MIN_COVERAGE = 0.80

# Estatísticas que realmente entram na análise agora.
ACTIVE_STATS = [
    "goals",
    "corners",
    "yellow_cards",
    "red_cards"
]

# Estrutura reservada para expansão futura.
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

INTEGRITY_NOTE_2627 = (
    "Confidence Score mede força da evidência e não probabilidade calibrada. "
    "X/20 é referência ampla. Frequências X/5/X/10 não confirmadas não foram "
    "inventadas. Linhas de AMBAS baseadas apenas em médias recebem penalização "
    "até fecharmos Produziu × Cedeu jogo a jogo."
)


# =========================================================
# LINHAS
# =========================================================

MARKET_LINES = {
    "goals": [
        0.5,
        1.5,
        2.5
    ],

    "corners": [
        2.5,
        3.5,
        4.5,
        5.5,
        6.5,
        7.5,
        8.5,
        9.5
    ],

    "yellow_cards": [
        0.5,
        1.5,
        2.5,
        3.5,
        4.5
    ],

    "red_cards": [
        0.5
    ]
}


# =========================================================
# MAPEAMENTO SPORTMONKS
# =========================================================

CONFIRMED_TYPE_IDS = {
    34: "corners",
    52: "goals",
    83: "red_cards",
    84: "yellow_cards"
}


STAT_CODE_MAP = {
    "goals": "goals",
    "corners": "corners",

    "yellowcards": "yellow_cards",
    "yellow-cards": "yellow_cards",

    "redcards": "red_cards",
    "red-cards": "red_cards",

    # Preparado para futuras fontes/planos.
    "shots-total": "shots",
    "total-shots": "shots",
    "shots": "shots",

    "shots-on-target": "shots_on_target",
    "shots-ontarget": "shots_on_target",

    "fouls": "fouls_committed",
    "fouls-committed": "fouls_committed",

    "expected-goals": "xg",
    "expected-goals-xg": "xg",
    "xg": "xg"
}


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


def parse_date(value):
    return datetime.strptime(
        value,
        "%Y-%m-%d"
    )


def average(values):
    if not values:
        return None

    return round(
        sum(values) / len(values),
        2
    )


# =========================================================
# CLIENTE SPORTMONKS
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

    if response.status_code == 401:
        raise RuntimeError(
            "Sportmonks recusou o token (HTTP 401)."
        )

    if response.status_code == 403:
        raise RuntimeError(
            "Sportmonks bloqueou este recurso para o plano atual (HTTP 403)."
        )

    response.raise_for_status()

    return response.json()


# =========================================================
# CONEXÃO
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

        return {
            "connected": True,
            "authenticated": True,
            "response_valid": isinstance(
                data,
                list
            ),
            "fixtures_received": (
                len(data)
                if isinstance(data, list)
                else 0
            )
        }

    except Exception as error:
        return {
            "connected": False,
            "authenticated": False,
            "reason": "connection_error",
            "error": str(error)
        }


# =========================================================
# FIXTURES
# =========================================================

def get_sportmonks_fixtures_by_date(date):
    parse_date(date)

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


def get_team_fixtures_between(
    team_id,
    start_date,
    end_date
):
    parse_date(start_date)
    parse_date(end_date)

    payload = sportmonks_request(
        (
            f"fixtures/between/"
            f"{start_date}/"
            f"{end_date}/"
            f"{team_id}"
        ),
        {
            "include": "participants;state",
            "order": "desc",
            "per_page": 50
        }
    )

    data = payload.get("data", [])

    if not isinstance(data, list):
        return []

    return data


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

    if not isinstance(participants, list):
        participants = []

    for participant in participants:
        if not isinstance(
            participant,
            dict
        ):
            continue

        meta = participant.get(
            "meta",
            {}
        )

        if not isinstance(meta, dict):
            meta = {}

        location = meta.get(
            "location"
        )

        item = {
            "id":
                participant.get("id"),

            "name":
                participant.get("name"),

            "short_code":
                participant.get(
                    "short_code"
                )
        }

        if location == "home":
            home = item

        elif location == "away":
            away = item

    return home, away


# =========================================================
# NORMALIZAÇÃO BÁSICA
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

    if not isinstance(state, dict):
        state = {}

    starting_at = fixture.get(
        "starting_at"
    )

    return {
        "match_id":
            fixture.get("id"),

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

        "date": (
            starting_at[:10]
            if starting_at
            else None
        ),

        "kick_off":
            starting_at,

        "status": (
            state.get("developer_name")
            or state.get("state")
            or state.get("short_name")
        ),

        "name":
            fixture.get("name"),

        "home_team":
            home,

        "away_team":
            away,

        "result_info":
            fixture.get("result_info")
    }


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
# IDENTIFICAÇÃO DAS ESTATÍSTICAS
# =========================================================

def normalize_stat_code(value):
    if value is None:
        return None

    return (
        str(value)
        .strip()
        .lower()
        .replace("_", "-")
        .replace(" ", "-")
    )


def identify_stat_field(stat):
    if not isinstance(stat, dict):
        return None

    type_id = stat.get(
        "type_id"
    )

    if type_id in CONFIRMED_TYPE_IDS:
        return CONFIRMED_TYPE_IDS[
            type_id
        ]

    stat_type = stat.get(
        "type",
        {}
    )

    if not isinstance(
        stat_type,
        dict
    ):
        return None

    code = normalize_stat_code(
        stat_type.get("code")
    )

    if code in STAT_CODE_MAP:
        return STAT_CODE_MAP[
            code
        ]

    developer_name = normalize_stat_code(
        stat_type.get(
            "developer_name"
        )
    )

    if developer_name in STAT_CODE_MAP:
        return STAT_CODE_MAP[
            developer_name
        ]

    return None


# =========================================================
# PARSER
# =========================================================

def parse_fixture_statistics(fixture):
    home_stats = empty_stats()
    away_stats = empty_stats()

    statistics = fixture.get(
        "statistics",
        []
    )

    if not isinstance(
        statistics,
        list
    ):
        statistics = []

    recognized = []
    unrecognized = []

    for stat in statistics:
        if not isinstance(stat, dict):
            continue

        field = identify_stat_field(
            stat
        )

        stat_type = stat.get(
            "type",
            {}
        )

        if not isinstance(
            stat_type,
            dict
        ):
            stat_type = {}

        type_id = stat.get(
            "type_id"
        )

        code = stat_type.get(
            "code"
        )

        developer_name = stat_type.get(
            "developer_name"
        )

        location = stat.get(
            "location"
        )

        data = stat.get(
            "data",
            {}
        )

        if not isinstance(data, dict):
            data = {}

        value = normalize_number(
            data.get("value")
        )

        if not field:
            unrecognized.append({
                "type_id":
                    type_id,
                "code":
                    code,
                "developer_name":
                    developer_name,
                "location":
                    location,
                "value":
                    value
            })
            continue

        recognized.append({
            "field":
                field,
            "type_id":
                type_id,
            "code":
                code,
            "location":
                location,
            "value":
                value
        })

        if location == "home":
            home_stats[field] = value

        elif location == "away":
            away_stats[field] = value

    return {
        "home":
            home_stats,

        "away":
            away_stats,

        "recognized":
            recognized,

        "unrecognized":
            unrecognized
    }


# =========================================================
# PARTIDA NORMALIZADA
# =========================================================

def normalize_fixture_with_stats(fixture):
    basic = normalize_sportmonks_fixture(
        fixture
    )

    if basic is None:
        return None

    parsed = parse_fixture_statistics(
        fixture
    )

    home_team = basic.get(
        "home_team"
    )

    away_team = basic.get(
        "away_team"
    )

    return {
        **basic,

        "teams": {
            "home": {
                "team": (
                    home_team.get("name")
                    if isinstance(
                        home_team,
                        dict
                    )
                    else None
                ),

                "team_id": (
                    home_team.get("id")
                    if isinstance(
                        home_team,
                        dict
                    )
                    else None
                ),

                "stats":
                    parsed["home"]
            },

            "away": {
                "team": (
                    away_team.get("name")
                    if isinstance(
                        away_team,
                        dict
                    )
                    else None
                ),

                "team_id": (
                    away_team.get("id")
                    if isinstance(
                        away_team,
                        dict
                    )
                    else None
                ),

                "stats":
                    parsed["away"]
            }
        },

        "stat_parser": {
            "recognized":
                parsed["recognized"],

            "unrecognized":
                parsed["unrecognized"]
        }
    }


def analyze_fixture_2627(
    fixture_id
):
    fixture = get_sportmonks_fixture(
        fixture_id
    )

    if not fixture:
        return None

    return normalize_fixture_with_stats(
        fixture
    )


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

    total = len(
        STAT_FIELDS
    )

    return {
        "available":
            available,

        "total":
            total,

        "coverage": round(
            available / total * 100,
            1
        )
    }


def match_coverage(match):
    teams = (
        match.get("teams", {})
        if isinstance(match, dict)
        else {}
    )

    home = teams.get(
        "home",
        {}
    )

    away = teams.get(
        "away",
        {}
    )

    return {
        "home":
            stats_coverage(
                home.get(
                    "stats",
                    {}
                )
                if isinstance(
                    home,
                    dict
                )
                else {}
            ),

        "away":
            stats_coverage(
                away.get(
                    "stats",
                    {}
                )
                if isinstance(
                    away,
                    dict
                )
                else {}
            )
    }


# =========================================================
# VISÃO DO TIME
# =========================================================

def team_view(
    match,
    team_id
):
    if not isinstance(match, dict):
        return None

    teams = match.get(
        "teams",
        {}
    )

    home = teams.get(
        "home",
        {}
    )

    away = teams.get(
        "away",
        {}
    )

    if not isinstance(home, dict):
        home = {}

    if not isinstance(away, dict):
        away = {}

    if home.get("team_id") == team_id:
        own = home
        opponent = away
        venue = "home"

    elif away.get("team_id") == team_id:
        own = away
        opponent = home
        venue = "away"

    else:
        return None

    return {
        "match_id":
            match.get("match_id"),

        "date":
            match.get("date"),

        "venue":
            venue,

        "team":
            own.get("team"),

        "team_id":
            team_id,

        "opponent":
            opponent.get("team"),

        "opponent_id":
            opponent.get("team_id"),

        "produced":
            normalize_stats(
                own.get(
                    "stats",
                    {}
                )
            ),

        "conceded":
            normalize_stats(
                opponent.get(
                    "stats",
                    {}
                )
            )
    }


# =========================================================
# VALORES / MÉDIAS
# =========================================================

def valid_values(
    history,
    side,
    field
):
    values = []

    for match in history:
        stats = match.get(
            side,
            {}
        )

        if not isinstance(
            stats,
            dict
        ):
            continue

        value = stats.get(
            field
        )

        if is_number(value):
            values.append(
                value
            )

    return values


def history_averages(history):
    result = {
        "produced": {},
        "conceded": {}
    }

    for field in ACTIVE_STATS:
        produced = valid_values(
            history,
            "produced",
            field
        )

        conceded = valid_values(
            history,
            "conceded",
            field
        )

        result["produced"][field] = {
            "average":
                average(produced),

            "sample":
                len(produced)
        }

        result["conceded"][field] = {
            "average":
                average(conceded),

            "sample":
                len(conceded)
        }

    return result


# =========================================================
# FREQUÊNCIAS REAIS
# =========================================================

def calculate_hit_rate(
    history,
    side,
    field,
    line
):
    values = valid_values(
        history,
        side,
        field
    )

    if not values:
        return {
            "line":
                line,

            "hits":
                None,

            "sample":
                0,

            "rate":
                None
        }

    hits = sum(
        1
        for value in values
        if value > line
    )

    return {
        "line":
            line,

        "hits":
            hits,

        "sample":
            len(values),

        "rate": round(
            hits / len(values) * 100,
            1
        )
    }


def build_frequencies(history):
    result = {}

    for field in ACTIVE_STATS:
        result[field] = {
            "produced": [],
            "conceded": []
        }

        for line in MARKET_LINES.get(
            field,
            []
        ):
            result[field][
                "produced"
            ].append(
                calculate_hit_rate(
                    history,
                    "produced",
                    field,
                    line
                )
            )

            result[field][
                "conceded"
            ].append(
                calculate_hit_rate(
                    history,
                    "conceded",
                    field,
                    line
                )
            )

    return result


# =========================================================
# QUALIDADE GERAL DA AMOSTRA
# =========================================================

def sample_quality(
    actual,
    requested
):
    if requested <= 0:
        return {
            "valid":
                False,

            "matches":
                actual,

            "requested":
                requested,

            "coverage":
                None,

            "status":
                "insufficient_data"
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
        "valid":
            valid,

        "matches":
            actual,

        "requested":
            requested,

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
# QUALIDADE POR ESTATÍSTICA
# =========================================================

def metric_side_quality(
    history,
    side,
    field,
    requested
):
    values = valid_values(
        history,
        side,
        field
    )

    actual = len(values)

    coverage_ratio = (
        actual / requested
        if requested > 0
        else 0
    )

    valid = (
        actual >= MIN_VALID_SAMPLE
        and
        coverage_ratio >= MIN_COVERAGE
    )

    return {
        "valid":
            valid,

        "sample":
            actual,

        "requested":
            requested,

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


def metric_quality(
    history,
    field,
    requested
):
    produced = metric_side_quality(
        history,
        "produced",
        field,
        requested
    )

    conceded = metric_side_quality(
        history,
        "conceded",
        field,
        requested
    )

    valid = (
        produced.get("valid") is True
        and
        conceded.get("valid") is True
    )

    return {
        "valid":
            valid,

        "produced":
            produced,

        "conceded":
            conceded,

        "status": (
            "valid"
            if valid
            else "insufficient_data"
        )
    }


def build_metric_quality(
    history,
    requested
):
    result = {}

    for field in ACTIVE_STATS:
        result[field] = metric_quality(
            history,
            field,
            requested
        )

    return result


# =========================================================
# HISTÓRICO 2026/27
# =========================================================

def collect_team_history_2627(
    team_id,
    season_id,
    limit=5,
    venue="all",
    before_date=None
):
    if limit not in [5, 10]:
        raise ValueError(
            "limit deve ser 5 ou 10"
        )

    if venue not in [
        "all",
        "home",
        "away"
    ]:
        raise ValueError(
            "venue deve ser all, home ou away"
        )

    if before_date is None:
        before_dt = datetime.utcnow()

    else:
        before_dt = parse_date(
            before_date
        )

    start_dt = (
        before_dt
        - timedelta(days=365)
    )

    end_dt = (
        before_dt
        - timedelta(days=1)
    )

    start_date = start_dt.strftime(
        "%Y-%m-%d"
    )

    end_date = end_dt.strftime(
        "%Y-%m-%d"
    )

    raw_fixtures = (
        get_team_fixtures_between(
            team_id,
            start_date,
            end_date
        )
    )

    candidates = []

    for raw in raw_fixtures:
        if not isinstance(
            raw,
            dict
        ):
            continue

        if raw.get(
            "season_id"
        ) != season_id:
            continue

        state = raw.get(
            "state",
            {}
        )

        if not isinstance(
            state,
            dict
        ):
            state = {}

        state_code = (
            state.get(
                "developer_name"
            )
            or state.get(
                "short_name"
            )
            or state.get(
                "state"
            )
        )

        if state_code != "FT":
            continue

        if not raw.get(
            "starting_at"
        ):
            continue

        candidates.append(
            raw
        )

    candidates.sort(
        key=lambda item:
            item.get(
                "starting_at"
            ) or "",
        reverse=True
    )

    history = []

    for candidate in candidates:
        fixture_id = candidate.get(
            "id"
        )

        if not fixture_id:
            continue

        complete = (
            get_sportmonks_fixture(
                fixture_id
            )
        )

        if not complete:
            continue

        normalized = (
            normalize_fixture_with_stats(
                complete
            )
        )

        if not normalized:
            continue

        view = team_view(
            normalized,
            team_id
        )

        if not view:
            continue

        if (
            venue != "all"
            and
            view.get("venue")
            != venue
        ):
            continue

        history.append(
            view
        )

        if len(history) >= limit:
            break

    return history


# =========================================================
# ANÁLISE DO HISTÓRICO
# =========================================================

def analyze_team_history_2627(
    team_id,
    season_id,
    limit=5,
    venue="all",
    before_date=None
):
    history = (
        collect_team_history_2627(
            team_id=team_id,
            season_id=season_id,
            limit=limit,
            venue=venue,
            before_date=before_date
        )
    )

    return {
        "season":
            SEASON,

        "season_id":
            season_id,

        "team_id":
            team_id,

        "limit":
            limit,

        "venue":
            venue,

        "before_date":
            before_date,

        "source":
            "Sportmonks",

        "active_stats":
            ACTIVE_STATS,

        "matches_analyzed":
            len(history),

        "sample_quality":
            sample_quality(
                len(history),
                limit
            ),

        "metric_quality":
            build_metric_quality(
                history,
                limit
            ),

        "averages":
            history_averages(
                history
            ),

        "frequencies":
            build_frequencies(
                history
            ),

        "matches":
            history,

        "integrity": {
            "future_matches_used":
                False,

            "missing_values_invented":
                False,

            "hit_rates_from_real_matches_only":
                True,

            "confidence_score_is_probability":
                False,

            "note":
                INTEGRITY_NOTE_2627
        }
    }


# =========================================================
# PRODUZIDO × CEDIDO
# =========================================================

def cross_metric(
    produced_history,
    opponent_history,
    field
):
    produced_values = valid_values(
        produced_history,
        "produced",
        field
    )

    conceded_values = valid_values(
        opponent_history,
        "conceded",
        field
    )

    produced_average = average(
        produced_values
    )

    conceded_average = average(
        conceded_values
    )

    cross_average = None

    if (
        produced_average is not None
        and
        conceded_average is not None
    ):
        cross_average = round(
            (
                produced_average
                + conceded_average
            ) / 2,
            2
        )

    return {
        "produced_average":
            produced_average,

        "produced_sample":
            len(produced_values),

        "opponent_conceded_average":
            conceded_average,

        "opponent_conceded_sample":
            len(conceded_values),

        "cross_average":
            cross_average,

        "is_hit_rate":
            False
    }


def build_cross(
    team_history,
    opponent_history
):
    result = {}

    for field in ACTIVE_STATS:
        result[field] = cross_metric(
            team_history,
            opponent_history,
            field
        )

    return result


# =========================================================
# VALIDAÇÃO DO CRUZAMENTO POR ESTATÍSTICA
# =========================================================

def cross_metric_quality(
    team_history,
    opponent_history,
    field,
    requested
):
    produced_values = valid_values(
        team_history,
        "produced",
        field
    )

    opponent_conceded_values = (
        valid_values(
            opponent_history,
            "conceded",
            field
        )
    )

    produced_sample = len(
        produced_values
    )

    opponent_sample = len(
        opponent_conceded_values
    )

    produced_coverage = (
        produced_sample / requested
        if requested > 0
        else 0
    )

    opponent_coverage = (
        opponent_sample / requested
        if requested > 0
        else 0
    )

    produced_valid = (
        produced_sample >= MIN_VALID_SAMPLE
        and
        produced_coverage >= MIN_COVERAGE
    )

    opponent_valid = (
        opponent_sample >= MIN_VALID_SAMPLE
        and
        opponent_coverage >= MIN_COVERAGE
    )

    valid = (
        produced_valid
        and
        opponent_valid
    )

    return {
        "valid":
            valid,

        "team_produced": {
            "valid":
                produced_valid,

            "sample":
                produced_sample,

            "requested":
                requested,

            "coverage": round(
                produced_coverage * 100,
                1
            )
        },

        "opponent_conceded": {
            "valid":
                opponent_valid,

            "sample":
                opponent_sample,

            "requested":
                requested,

            "coverage": round(
                opponent_coverage * 100,
                1
            )
        },

        "status": (
            "valid"
            if valid
            else "insufficient_data"
        )
    }


def build_cross_quality(
    team_history,
    opponent_history,
    requested
):
    result = {}

    for field in ACTIVE_STATS:
        result[field] = (
            cross_metric_quality(
                team_history,
                opponent_history,
                field,
                requested
            )
        )

    return result


# =========================================================
# EVIDÊNCIA POR MERCADO
# =========================================================

def build_market_evidence(
    home_general,
    away_general,
    home_home,
    away_away,
    requested
):
    result = {}

    for field in ACTIVE_STATS:
        home_general_quality = (
            cross_metric_quality(
                home_general,
                away_general,
                field,
                requested
            )
        )

        away_general_quality = (
            cross_metric_quality(
                away_general,
                home_general,
                field,
                requested
            )
        )

        home_venue_quality = (
            cross_metric_quality(
                home_home,
                away_away,
                field,
                requested
            )
        )

        away_venue_quality = (
            cross_metric_quality(
                away_away,
                home_home,
                field,
                requested
            )
        )

        general_valid = (
            home_general_quality[
                "valid"
            ]
            and
            away_general_quality[
                "valid"
            ]
        )

        venue_valid = (
            home_venue_quality[
                "valid"
            ]
            and
            away_venue_quality[
                "valid"
            ]
        )

        if (
            general_valid
            and
            venue_valid
        ):
            evidence = "complete"

        elif general_valid:
            evidence = "partial"

        else:
            evidence = "insufficient"

        result[field] = {
            "evidence":
                evidence,

            "eligible": (
                evidence
                in [
                    "complete",
                    "partial"
                ]
            ),

            "general_valid":
                general_valid,

            "home_away_valid":
                venue_valid,

            "home_general":
                home_general_quality,

            "away_general":
                away_general_quality,

            "home_at_home":
                home_venue_quality,

            "away_at_away":
                away_venue_quality
        }

    return result


# =========================================================
# PRÉ-JOGO 2026/27
# =========================================================

def analyze_prematch_2627(
    home_team_id,
    away_team_id,
    season_id,
    limit=5,
    before_date=None
):
    if limit not in [5, 10]:
        raise ValueError(
            "limit deve ser 5 ou 10"
        )

    # ---------------------------------------------
    # GERAL
    # ---------------------------------------------

    home_general = (
        collect_team_history_2627(
            team_id=home_team_id,
            season_id=season_id,
            limit=limit,
            venue="all",
            before_date=before_date
        )
    )

    away_general = (
        collect_team_history_2627(
            team_id=away_team_id,
            season_id=season_id,
            limit=limit,
            venue="all",
            before_date=before_date
        )
    )

    # ---------------------------------------------
    # CASA × FORA
    # ---------------------------------------------

    home_home = (
        collect_team_history_2627(
            team_id=home_team_id,
            season_id=season_id,
            limit=limit,
            venue="home",
            before_date=before_date
        )
    )

    away_away = (
        collect_team_history_2627(
            team_id=away_team_id,
            season_id=season_id,
            limit=limit,
            venue="away",
            before_date=before_date
        )
    )

    # ---------------------------------------------
    # QUALIDADE GERAL
    # ---------------------------------------------

    sample_quality_result = {
        "home_general":
            sample_quality(
                len(home_general),
                limit
            ),

        "away_general":
            sample_quality(
                len(away_general),
                limit
            ),

        "home_at_home":
            sample_quality(
                len(home_home),
                limit
            ),

        "away_at_away":
            sample_quality(
                len(away_away),
                limit
            )
    }

    # ---------------------------------------------
    # QUALIDADE POR ESTATÍSTICA
    # ---------------------------------------------

    metric_quality_result = {
        "home_general":
            build_metric_quality(
                home_general,
                limit
            ),

        "away_general":
            build_metric_quality(
                away_general,
                limit
            ),

        "home_at_home":
            build_metric_quality(
                home_home,
                limit
            ),

        "away_at_away":
            build_metric_quality(
                away_away,
                limit
            )
    }

    # ---------------------------------------------
    # EVIDÊNCIA POR MERCADO
    # ---------------------------------------------

    market_evidence = (
        build_market_evidence(
            home_general,
            away_general,
            home_home,
            away_away,
            limit
        )
    )

    eligible_stats = [
        field
        for field, data
        in market_evidence.items()
        if data.get(
            "eligible"
        ) is True
    ]

    blocked_stats = [
        field
        for field, data
        in market_evidence.items()
        if data.get(
            "eligible"
        ) is not True
    ]

    # ---------------------------------------------
    # PRODUZIDO × CEDIDO
    # ---------------------------------------------

    produced_x_conceded = {
        "general": {
            "home":
                build_cross(
                    home_general,
                    away_general
                ),

            "away":
                build_cross(
                    away_general,
                    home_general
                )
        },

        "home_away": {
            "home":
                build_cross(
                    home_home,
                    away_away
                ),

            "away":
                build_cross(
                    away_away,
                    home_home
                )
        }
    }

    # ---------------------------------------------
    # QUALIDADE DOS CRUZAMENTOS
    # ---------------------------------------------

    cross_quality = {
        "general": {
            "home":
                build_cross_quality(
                    home_general,
                    away_general,
                    limit
                ),

            "away":
                build_cross_quality(
                    away_general,
                    home_general,
                    limit
                )
        },

        "home_away": {
            "home":
                build_cross_quality(
                    home_home,
                    away_away,
                    limit
                ),

            "away":
                build_cross_quality(
                    away_away,
                    home_home,
                    limit
                )
        }
    }

    return {
        "season":
            SEASON,

        "season_id":
            season_id,

        "before_date":
            before_date,

        "limit":
            limit,

        "source":
            "Sportmonks",

        "active_stats":
            ACTIVE_STATS,

        "teams": {
            "home_team_id":
                home_team_id,

            "away_team_id":
                away_team_id
        },

        "sample_quality":
            sample_quality_result,

        "metric_quality":
            metric_quality_result,

        "market_evidence":
            market_evidence,

        "eligible_stats":
            eligible_stats,

        "blocked_stats":
            blocked_stats,

        "home": {
            "general": {
                "matches":
                    home_general,

                "averages":
                    history_averages(
                        home_general
                    ),

                "frequencies":
                    build_frequencies(
                        home_general
                    )
            },

            "home_only": {
                "matches":
                    home_home,

                "averages":
                    history_averages(
                        home_home
                    ),

                "frequencies":
                    build_frequencies(
                        home_home
                    )
            }
        },

        "away": {
            "general": {
                "matches":
                    away_general,

                "averages":
                    history_averages(
                        away_general
                    ),

                "frequencies":
                    build_frequencies(
                        away_general
                    )
            },

            "away_only": {
                "matches":
                    away_away,

                "averages":
                    history_averages(
                        away_away
                    ),

                "frequencies":
                    build_frequencies(
                        away_away
                    )
            }
        },

        "produced_x_conceded":
            produced_x_conceded,

        "cross_quality":
            cross_quality,

        "recommendation_gate": {
            "eligible_stats":
                eligible_stats,

            "blocked_stats":
                blocked_stats,

            "has_eligible_market":
                len(
                    eligible_stats
                ) > 0
        },

        "integrity": {
            "missing_values_invented":
                False,

            "future_matches_used":
                False,

            "hit_rates_from_real_matches_only":
                True,

            "cross_average_is_hit_rate":
                False,

            "confidence_score_is_probability":
                False,

            "note":
                INTEGRITY_NOTE_2627
        }
    }


# =========================================================
# COMPATIBILIDADE
# =========================================================

def get_team_history(
    matches,
    team_name,
    limit=5,
    venue="all"
):
    history = []

    for match in matches:
        teams = match.get(
            "teams",
            {}
        )

        home = teams.get(
            "home",
            {}
        )

        away = teams.get(
            "away",
            {}
        )

        team_id = None

        if home.get(
            "team"
        ) == team_name:
            team_id = home.get(
                "team_id"
            )

        elif away.get(
            "team"
        ) == team_name:
            team_id = away.get(
                "team_id"
            )

        if team_id is None:
            continue

        view = team_view(
            match,
            team_id
        )

        if not view:
            continue

        if (
            venue != "all"
            and
            view.get("venue")
            != venue
        ):
            continue

        history.append(
            view
        )

    history.sort(
        key=lambda item:
            item.get("date") or "",
        reverse=True
    )

    return history[:limit]


def build_team_summary(
    history,
    requested=5
):
    return {
        "matches_analyzed":
            len(history),

        "sample_quality":
            sample_quality(
                len(history),
                requested
            ),

        "metric_quality":
            build_metric_quality(
                history,
                requested
            ),

        "averages":
            history_averages(
                history
            ),

        "frequencies":
            build_frequencies(
                history
            ),

        "matches":
            history
    }


# =========================================================
# STATUS
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

        "season":
            SEASON,

        "mode":
            "2026_27",

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

        "active_analysis_stats":
            ACTIVE_STATS,

        "reserved_future_stats": [
            "xg",
            "shots",
            "shots_on_target",
            "fouls_committed"
        ],

        "confirmed_sportmonks_type_ids": {
            "34":
                "corners",

            "52":
                "goals",

            "83":
                "red_cards",

            "84":
                "yellow_cards"
        },

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
            "Validar market_evidence por estatística "
            "antes do Confidence Score."
        )
    }
