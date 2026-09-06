from datetime import datetime

SEASON = "2026/27"

INTEGRITY_NOTE_2627 = (
    "Dados 2026/27 somente podem entrar na Football Intelligence API "
    "quando forem confirmados por uma fonte de dados válida. "
    "Valores ausentes permanecem null/None. "
    "Nenhuma frequência X/5 ou X/10 é criada a partir de médias."
)


# =========================================================
# PADRÃO OFICIAL DE ESTATÍSTICAS 2026/27
# =========================================================

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


def empty_stats():
    """
    Para dados atuais usamos None em vez de zero.

    Zero significa que a estatística foi confirmada como zero.
    None significa que o dado não foi fornecido/confirmado.
    """
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


# =========================================================
# VALIDAÇÃO
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

        if text == "":
            return None

        number = float(
            text.replace(",", ".")
        )

        if number.is_integer():
            return int(number)

        return round(number, 3)

    except (TypeError, ValueError):
        return None


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
# PARTIDA PADRONIZADA
# =========================================================

def normalize_match(match):
    """
    Transforma uma partida 2026/27 no padrão interno
    da Football Intelligence API.
    """

    if not isinstance(match, dict):
        return None

    match_id = match.get("match_id")

    date = match.get("date")

    competition = match.get("competition")

    home_team = match.get("home_team")
    away_team = match.get("away_team")

    if (
        match_id is None
        or not date
        or not home_team
        or not away_team
    ):
        return None

    try:
        datetime.strptime(
            date,
            "%Y-%m-%d"
        )
    except (TypeError, ValueError):
        return None

    home_stats = normalize_stats(
        match.get("home_stats", {})
    )

    away_stats = normalize_stats(
        match.get("away_stats", {})
    )

    return {
        "match_id": str(match_id),

        "season": SEASON,

        "competition":
            competition,

        "date":
            date,

        "kick_off":
            match.get("kick_off"),

        "status":
            match.get("status"),

        "home_team":
            home_team,

        "away_team":
            away_team,

        "home_score":
            normalize_number(
                match.get("home_score")
            ),

        "away_score":
            normalize_number(
                match.get("away_score")
            ),

        "home_stats":
            home_stats,

        "away_stats":
            away_stats,

        "source":
            match.get("source"),

        "source_match_id":
            match.get("source_match_id"),

        "updated_at":
            match.get("updated_at")
    }


# =========================================================
# CONTROLE DE COMPLETUDE
# =========================================================

def stats_coverage(stats):
    if not isinstance(stats, dict):
        return {
            "available": 0,
            "total": len(STAT_FIELDS),
            "coverage": 0.0
        }

    available = sum(
        1
        for field in STAT_FIELDS
        if is_number(
            stats.get(field)
        )
    )

    total = len(STAT_FIELDS)

    return {
        "available":
            available,

        "total":
            total,

        "coverage":
            round(
                available / total * 100,
                1
            )
    }


def match_coverage(match):
    if not isinstance(match, dict):
        return {
            "home": None,
            "away": None,
            "complete": False
        }

    home = stats_coverage(
        match.get(
            "home_stats",
            {}
        )
    )

    away = stats_coverage(
        match.get(
            "away_stats",
            {}
        )
    )

    complete = (
        home["coverage"] == 100.0
        and
        away["coverage"] == 100.0
    )

    return {
        "home":
            home,

        "away":
            away,

        "complete":
            complete
    }


# =========================================================
# PRODUZIDO × CEDIDO
# =========================================================

def team_view(match, team_name):
    """
    Converte uma partida para:
    produzido pelo time
    +
    cedido ao adversário.
    """

    if not isinstance(match, dict):
        return None

    home = match.get("home_team")
    away = match.get("away_team")

    if team_name == home:
        produced = match.get(
            "home_stats",
            {}
        )

        conceded = match.get(
            "away_stats",
            {}
        )

        venue = "home"
        opponent = away

    elif team_name == away:
        produced = match.get(
            "away_stats",
            {}
        )

        conceded = match.get(
            "home_stats",
            {}
        )

        venue = "away"
        opponent = home

    else:
        return None

    return {
        "match_id":
            match.get("match_id"),

        "date":
            match.get("date"),

        "competition":
            match.get("competition"),

        "team":
            team_name,

        "opponent":
            opponent,

        "venue":
            venue,

        "produced":
            normalize_stats(
                produced
            ),

        "conceded":
            normalize_stats(
                conceded
            )
    }


# =========================================================
# HISTÓRICO
# =========================================================

def get_team_history(
    matches,
    team_name,
    limit=5,
    venue="all"
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

    team_games = []

    for raw_match in matches:
        match = normalize_match(
            raw_match
        )

        if match is None:
            continue

        view = team_view(
            match,
            team_name
        )

        if view is None:
            continue

        if (
            venue != "all"
            and view["venue"] != venue
        ):
            continue

        team_games.append(
            view
        )

    team_games.sort(
        key=lambda game:
            game.get("date") or "",
        reverse=True
    )

    return team_games[:limit]


# =========================================================
# MÉDIAS SEM INVENTAR AUSÊNCIAS
# =========================================================

def valid_values(games, section, stat):
    values = []

    for game in games:
        value = (
            game
            .get(section, {})
            .get(stat)
        )

        if is_number(value):
            values.append(value)

    return values


def average(values):
    if not values:
        return None

    return round(
        sum(values) / len(values),
        2
    )


def history_averages(games):
    produced = {}
    conceded = {}

    for stat in STAT_FIELDS:
        produced_values = valid_values(
            games,
            "produced",
            stat
        )

        conceded_values = valid_values(
            games,
            "conceded",
            stat
        )

        produced[stat] = {
            "average":
                average(
                    produced_values
                ),

            "sample":
                len(
                    produced_values
                )
        }

        conceded[stat] = {
            "average":
                average(
                    conceded_values
                ),

            "sample":
                len(
                    conceded_values
                )
        }

    return {
        "produced":
            produced,

        "conceded":
            conceded
    }


# =========================================================
# FREQUÊNCIA JOGO A JOGO
# =========================================================

def calculate_hit_rate(
    games,
    section,
    stat,
    line
):
    values = valid_values(
        games,
        section,
        stat
    )

    sample = len(values)

    if sample == 0:
        return {
            "hits": 0,
            "sample": 0,
            "rate": None
        }

    hits = sum(
        1
        for value in values
        if value > line
    )

    return {
        "hits":
            hits,

        "sample":
            sample,

        "rate":
            round(
                hits / sample * 100,
                1
            )
    }


# =========================================================
# QUALIDADE DA AMOSTRA
# =========================================================

def sample_quality(
    actual,
    requested
):
    if (
        not isinstance(actual, int)
        or not isinstance(requested, int)
        or requested <= 0
    ):
        return {
            "valid": False,
            "coverage": None
        }

    coverage_ratio = (
        actual / requested
    )

    valid = (
        actual >= 4
        and
        coverage_ratio >= 0.80
    )

    return {
        "valid":
            valid,

        "matches":
            actual,

        "requested":
            requested,

        "coverage":
            round(
                coverage_ratio * 100,
                1
            ),

        "status":
            (
                "valid"
                if valid
                else
                "insufficient_data"
            )
    }


# =========================================================
# RESUMO DO TIME
# =========================================================

def build_team_summary(
    matches,
    team_name,
    limit=5,
    venue="all"
):
    games = get_team_history(
        matches=matches,
        team_name=team_name,
        limit=limit,
        venue=venue
    )

    return {
        "season":
            SEASON,

        "team":
            team_name,

        "venue":
            venue,

        "requested_matches":
            limit,

        "matches_analyzed":
            len(games),

        "sample_quality":
            sample_quality(
                len(games),
                limit
            ),

        "averages":
            history_averages(
                games
            ),

        "games":
            games,

        "integrity": {
            "missing_values_invented":
                False,

            "zero_means_confirmed_zero":
                True,

            "null_means_unavailable":
                True,

            "hit_rates_from_match_data_only":
                True,

            "integrity_note":
                INTEGRITY_NOTE_2627
        }
    }


# =========================================================
# STATUS DO COLETOR
# =========================================================

def collector_2627_status():
    return {
        "status":
            "ready",

        "season":
            SEASON,

        "mode":
            "2026_27",

        "data_source_connected":
            False,

        "storage_connected":
            False,

        "supported_stats":
            STAT_FIELDS,

        "integrity": {
            "missing_values_invented":
                False,

            "zero_is_missing":
                False,

            "null_is_missing":
                True,

            "minimum_valid_games":
                4,

            "minimum_coverage":
                0.80
        },

        "next_step":
            (
                "Conectar uma fonte real de dados "
                "2026/27 e armazenamento."
            )
    }
