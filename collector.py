import requests
from collections import defaultdict
from datetime import datetime

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
TIMEOUT = 20

# Quantidade mínima para uma amostra ser considerada válida
MIN_VALID_SAMPLE = 5


# =========================================================
# DOWNLOAD / FONTE
# =========================================================

def download_json(url):
    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def get_competitions():
    return download_json(
        f"{BASE_URL}/competitions.json"
    )


def get_matches(competition_id, season_id):
    return download_json(
        f"{BASE_URL}/matches/{competition_id}/{season_id}.json"
    )


def get_events(match_id):
    return download_json(
        f"{BASE_URL}/events/{match_id}.json"
    )


# =========================================================
# ESTRUTURA DAS ESTATÍSTICAS
# =========================================================

def empty_team_stats():
    return {
        "goals": 0,
        "xg": 0.0,
        "shots": 0,
        "shots_on_target": 0,
        "corners": 0,
        "fouls_committed": 0,
        "yellow_cards": 0,
        "red_cards": 0
    }


# =========================================================
# ANALISADOR DE EVENTOS
# =========================================================

def analyze_events(events):

    teams = defaultdict(empty_team_stats)

    for event in events:

        team_data = event.get("team")

        if not team_data:
            continue

        team = team_data.get("name")

        if not team:
            continue

        _ = teams[team]

        event_type = (
            event.get("type", {})
            .get("name", "")
        )

        # =================================================
        # FINALIZAÇÕES
        # =================================================

        if event_type == "Shot":

            teams[team]["shots"] += 1

            shot = event.get("shot", {})

            outcome = (
                shot.get("outcome", {})
                .get("name")
            )

            shot_type = (
                shot.get("type", {})
                .get("name")
            )

            xg = shot.get("statsbomb_xg")

            if isinstance(xg, (int, float)):
                teams[team]["xg"] += xg

            if outcome == "Goal":
                teams[team]["goals"] += 1

            if outcome in [
                "Goal",
                "Saved",
                "Saved to Post"
            ]:
                teams[team]["shots_on_target"] += 1

            # Corner executado diretamente como finalização
            if shot_type == "Corner":
                teams[team]["corners"] += 1

        # =================================================
        # GOL CONTRA A FAVOR
        # =================================================

        elif event_type == "Own Goal For":
            teams[team]["goals"] += 1

        # =================================================
        # ESCANTEIOS
        # =================================================

        elif event_type == "Pass":

            pass_data = event.get("pass", {})

            pass_type = (
                pass_data.get("type", {})
                .get("name")
            )

            if pass_type == "Corner":
                teams[team]["corners"] += 1

        # =================================================
        # FALTAS
        # =================================================

        elif event_type == "Foul Committed":

            foul = event.get(
                "foul_committed",
                {}
            )

            advantage = foul.get("advantage")

            foul_type = (
                foul.get("type", {})
                .get("name")
            )

            valid_foul = (
                advantage is not True
                and foul_type != "Offside"
            )

            if valid_foul:
                teams[team]["fouls_committed"] += 1

            card = (
                foul.get("card", {})
                .get("name")
            )

            if card in [
                "Yellow Card",
                "Second Yellow"
            ]:
                teams[team]["yellow_cards"] += 1

            if card in [
                "Red Card",
                "Second Yellow"
            ]:
                teams[team]["red_cards"] += 1

        # =================================================
        # BAD BEHAVIOUR / CARTÕES
        # =================================================

        elif event_type == "Bad Behaviour":

            behaviour = event.get(
                "bad_behaviour",
                {}
            )

            card = (
                behaviour.get("card", {})
                .get("name")
            )

            if card in [
                "Yellow Card",
                "Second Yellow"
            ]:
                teams[team]["yellow_cards"] += 1

            if card in [
                "Red Card",
                "Second Yellow"
            ]:
                teams[team]["red_cards"] += 1

    result = {}

    for team, stats in teams.items():

        stats["xg"] = round(
            stats["xg"],
            2
        )

        result[team] = stats

    return result


# =========================================================
# ANALISAR UMA PARTIDA
# =========================================================

def analyze_match(match_id):

    events = get_events(match_id)

    stats = analyze_events(events)

    return {
        "match_id": match_id,
        "source": "StatsBomb Open Data",
        "events_received": len(events),
        "teams": stats
    }


# =========================================================
# UTILIDADES
# =========================================================

def team_name_from_match(match, side):

    if side == "home":
        return (
            match.get("home_team", {})
            .get("home_team_name")
        )

    return (
        match.get("away_team", {})
        .get("away_team_name")
    )


def find_opponent(stats, team_name):

    for name, values in stats.items():

        if name != team_name:
            return name, values

    return None, None


def average(values):

    if not values:
        return None

    return round(
        sum(values) / len(values),
        2
    )


# =========================================================
# LINHAS PARA FREQUÊNCIAS
# =========================================================

FREQUENCY_LINES = {

    "goals": [
        0.5,
        1.5,
        2.5
    ],

    "shots": [
        7.5,
        8.5,
        9.5,
        10.5,
        11.5,
        12.5
    ],

    "shots_on_target": [
        1.5,
        2.5,
        3.5,
        4.5,
        5.5,
        6.5
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

    "fouls_committed": [
        7.5,
        8.5,
        9.5,
        10.5,
        11.5,
        12.5
    ],

    "yellow_cards": [
        0.5,
        1.5,
        2.5,
        3.5,
        4.5
    ]
}


# =========================================================
# FREQUÊNCIAS
# =========================================================

def calculate_frequency(values, line):

    valid_values = [
        value
        for value in values
        if isinstance(value, (int, float))
    ]

    total = len(valid_values)

    if total == 0:
        return {
            "hits": 0,
            "sample": 0,
            "rate": None
        }

    hits = sum(
        1
        for value in valid_values
        if value > line
    )

    return {
        "hits": hits,
        "sample": total,
        "rate": round(
            (hits / total) * 100,
            1
        )
    }


def build_frequencies(stat_values):

    result = {}

    for stat, lines in FREQUENCY_LINES.items():

        values = stat_values.get(
            stat,
            []
        )

        result[stat] = {}

        for line in lines:

            label = f"over_{line}"

            result[stat][label] = (
                calculate_frequency(
                    values,
                    line
                )
            )

    return result


# =========================================================
# FREQUÊNCIAS DO TOTAL DA PARTIDA
# =========================================================

def build_match_total_frequencies(games):

    total_values = defaultdict(list)

    for game in games:

        produced = game.get(
            "produced",
            {}
        )

        conceded = game.get(
            "conceded",
            {}
        )

        for stat in FREQUENCY_LINES.keys():

            produced_value = produced.get(stat)
            conceded_value = conceded.get(stat)

            if (
                isinstance(
                    produced_value,
                    (int, float)
                )
                and isinstance(
                    conceded_value,
                    (int, float)
                )
            ):

                total_values[stat].append(
                    produced_value
                    + conceded_value
                )

    return build_frequencies(
        total_values
    )


# =========================================================
# QUALIDADE / INTEGRIDADE DA AMOSTRA
# =========================================================

def evaluate_sample(
    matches_analyzed,
    requested_matches
):

    if not isinstance(
        matches_analyzed,
        int
    ):
        return {
            "status": "insufficient_data",
            "valid": False,
            "matches": 0,
            "requested": requested_matches,
            "coverage": 0.0
        }

    if (
        not isinstance(
            requested_matches,
            int
        )
        or requested_matches <= 0
    ):
        return {
            "status": "insufficient_data",
            "valid": False,
            "matches": matches_analyzed,
            "requested": requested_matches,
            "coverage": None
        }

    coverage = round(
        (
            matches_analyzed
            / requested_matches
        ) * 100,
        1
    )

    valid = (
        matches_analyzed >= MIN_VALID_SAMPLE
        and
        matches_analyzed >= requested_matches
    )

    return {
        "status":
            "valid"
            if valid
            else "insufficient_data",

        "valid":
            valid,

        "matches":
            matches_analyzed,

        "requested":
            requested_matches,

        "coverage":
            coverage
    }


def evaluate_history_sample(history):

    return evaluate_sample(
        history.get(
            "matches_analyzed",
            0
        ),
        history.get(
            "requested_matches",
            0
        )
    )


# =========================================================
# HISTÓRICO DE UM TIME
# =========================================================

def analyze_team_history(
    competition_id,
    season_id,
    team_name,
    limit=10,
    venue="all"
):

    matches = get_matches(
        competition_id,
        season_id
    )

    team_matches = []

    # =====================================================
    # LOCALIZA PARTIDAS DO TIME
    # =====================================================

    for match in matches:

        home = team_name_from_match(
            match,
            "home"
        )

        away = team_name_from_match(
            match,
            "away"
        )

        if team_name not in [
            home,
            away
        ]:
            continue

        if (
            venue == "home"
            and home != team_name
        ):
            continue

        if (
            venue == "away"
            and away != team_name
        ):
            continue

        date_text = match.get(
            "match_date"
        )

        try:

            date_value = datetime.strptime(
                date_text,
                "%Y-%m-%d"
            )

        except Exception:
            continue

        team_matches.append({
            "date_value":
                date_value,

            "match":
                match
        })

    # Mais recentes primeiro
    team_matches.sort(
        key=lambda item:
            item["date_value"],
        reverse=True
    )

    selected = team_matches[
        :limit
    ]

    games = []

    produced = defaultdict(list)
    conceded = defaultdict(list)

    # =====================================================
    # ANALISA JOGO POR JOGO
    # =====================================================

    for item in selected:

        match = item["match"]

        match_id = match.get(
            "match_id"
        )

        home = team_name_from_match(
            match,
            "home"
        )

        away = team_name_from_match(
            match,
            "away"
        )

        events = get_events(
            match_id
        )

        stats = analyze_events(
            events
        )

        team_stats = stats.get(
            team_name
        )

        opponent_name, opponent_stats = (
            find_opponent(
                stats,
                team_name
            )
        )

        # Nunca inventar dado ausente
        if (
            team_stats is None
            or opponent_stats is None
        ):
            continue

        location = (
            "home"
            if home == team_name
            else "away"
        )

        game = {
            "match_id":
                match_id,

            "date":
                match.get(
                    "match_date"
                ),

            "home":
                home,

            "away":
                away,

            "venue":
                location,

            "opponent":
                opponent_name,

            "produced":
                dict(team_stats),

            "conceded":
                dict(opponent_stats)
        }

        games.append(game)

        for stat, value in (
            team_stats.items()
        ):

            if isinstance(
                value,
                (int, float)
            ):
                produced[
                    stat
                ].append(value)

        for stat, value in (
            opponent_stats.items()
        ):

            if isinstance(
                value,
                (int, float)
            ):
                conceded[
                    stat
                ].append(value)

    # =====================================================
    # MÉDIAS
    # =====================================================

    produced_averages = {}

    conceded_averages = {}

    for stat, values in (
        produced.items()
    ):

        produced_averages[
            stat
        ] = average(values)

    for stat, values in (
        conceded.items()
    ):

        conceded_averages[
            stat
        ] = average(values)

    # =====================================================
    # QUALIDADE DA AMOSTRA
    # =====================================================

    sample_quality = evaluate_sample(
        len(games),
        limit
    )

    # =====================================================
    # RESULTADO
    # =====================================================

    return {
        "team":
            team_name,

        "competition_id":
            competition_id,

        "season_id":
            season_id,

        "requested_matches":
            limit,

        "matches_analyzed":
            len(games),

        "venue":
            venue,

        "sample_quality":
            sample_quality,

        "games":
            games,

        "averages": {
            "produced":
                produced_averages,

            "conceded":
                conceded_averages
        },

        "frequencies": {

            "produced":
                build_frequencies(
                    produced
                ),

            "conceded":
                build_frequencies(
                    conceded
                ),

            "match_total":
                build_match_total_frequencies(
                    games
                )
        },

        "integrity": {
            "match_by_match":
                True,

            "missing_values_invented":
                False,

            "frequencies_from_averages":
                False,

            "frequency_denominator":
                "actual_valid_games",

            "insufficient_sample_can_recommend":
                False
        }
    }


# =========================================================
# PRODUZIDO × CEDIDO
# =========================================================

def cross_stat(
    produced_average,
    opponent_conceded_average
):

    if (
        not isinstance(
            produced_average,
            (int, float)
        )
        or not isinstance(
            opponent_conceded_average,
            (int, float)
        )
    ):
        return None

    return round(
        (
            produced_average
            + opponent_conceded_average
        ) / 2,
        2
    )


def build_cross(
    team_history,
    opponent_history
):

    result = {}

    team_produced = (
        team_history
        .get("averages", {})
        .get("produced", {})
    )

    opponent_conceded = (
        opponent_history
        .get("averages", {})
        .get("conceded", {})
    )

    team_sample = (
        evaluate_history_sample(
            team_history
        )
    )

    opponent_sample = (
        evaluate_history_sample(
            opponent_history
        )
    )

    cross_valid = (
        team_sample["valid"]
        and opponent_sample["valid"]
    )

    for stat in [
        "goals",
        "xg",
        "shots",
        "shots_on_target",
        "corners",
        "fouls_committed",
        "yellow_cards"
    ]:

        produced_value = (
            team_produced.get(stat)
        )

        conceded_value = (
            opponent_conceded.get(stat)
        )

        projection = cross_stat(
            produced_value,
            conceded_value
        )

        result[stat] = {

            "team_produced_average":
                produced_value,

            "opponent_conceded_average":
                conceded_value,

            "cross_average":
                projection,

            "sample_valid":
                cross_valid,

            "confidence":
                (
                    "eligible"
                    if cross_valid
                    else "insufficient_data"
                )
        }

    return result


# =========================================================
# QUALIDADE DO PRÉ-JOGO
# =========================================================

def evaluate_prematch_samples(
    home_general,
    away_general,
    home_at_home,
    away_at_away
):

    samples = {

        "home_general":
            evaluate_history_sample(
                home_general
            ),

        "away_general":
            evaluate_history_sample(
                away_general
            ),

        "home_at_home":
            evaluate_history_sample(
                home_at_home
            ),

        "away_at_away":
            evaluate_history_sample(
                away_at_away
            )
    }

    general_valid = (
        samples[
            "home_general"
        ]["valid"]
        and
        samples[
            "away_general"
        ]["valid"]
    )

    home_away_valid = (
        samples[
            "home_at_home"
        ]["valid"]
        and
        samples[
            "away_at_away"
        ]["valid"]
    )

    return {

        "samples":
            samples,

        "general_cross": {
            "valid":
                general_valid,

            "confidence":
                (
                    "eligible"
                    if general_valid
                    else "insufficient_data"
                )
        },

        "home_away_cross": {
            "valid":
                home_away_valid,

            "confidence":
                (
                    "eligible"
                    if home_away_valid
                    else "insufficient_data"
                )
        },

        "integrity_rule":
            (
                "Amostras incompletas podem ser "
                "exibidas, mas nao podem gerar "
                "confianca ou recomendacao."
            )
    }


# =========================================================
# ANÁLISE PRÉ-JOGO CASA × FORA
# =========================================================

def analyze_prematch(
    competition_id,
    season_id,
    home_team,
    away_team,
    limit=5
):

    # =====================================================
    # MANDANTE — GERAL
    # =====================================================

    home_general = analyze_team_history(
        competition_id,
        season_id,
        home_team,
        limit=limit,
        venue="all"
    )

    # =====================================================
    # VISITANTE — GERAL
    # =====================================================

    away_general = analyze_team_history(
        competition_id,
        season_id,
        away_team,
        limit=limit,
        venue="all"
    )

    # =====================================================
    # MANDANTE — CASA
    # =====================================================

    home_at_home = analyze_team_history(
        competition_id,
        season_id,
        home_team,
        limit=limit,
        venue="home"
    )

    # =====================================================
    # VISITANTE — FORA
    # =====================================================

    away_at_away = analyze_team_history(
        competition_id,
        season_id,
        away_team,
        limit=limit,
        venue="away"
    )

    # =====================================================
    # CRUZAMENTO GERAL
    # =====================================================

    home_cross_general = build_cross(
        home_general,
        away_general
    )

    away_cross_general = build_cross(
        away_general,
        home_general
    )

    # =====================================================
    # CRUZAMENTO CASA × FORA
    # =====================================================

    home_cross_venue = build_cross(
        home_at_home,
        away_at_away
    )

    away_cross_venue = build_cross(
        away_at_away,
        home_at_home
    )

    # =====================================================
    # QUALIDADE DAS AMOSTRAS
    # =====================================================

    sample_quality = (
        evaluate_prematch_samples(
            home_general,
            away_general,
            home_at_home,
            away_at_away
        )
    )

    # =====================================================
    # RESULTADO
    # =====================================================

    return {

        "match": {
            "home":
                home_team,

            "away":
                away_team
        },

        "competition_id":
            competition_id,

        "season_id":
            season_id,

        "sample":
            limit,

        "sample_quality":
            sample_quality,

        "home": {

            "general":
                home_general,

            "home_only":
                home_at_home
        },

        "away": {

            "general":
                away_general,

            "away_only":
                away_at_away
        },

        "produced_x_conceded": {

            "general": {

                "home":
                    home_cross_general,

                "away":
                    away_cross_general
            },

            "home_away": {

                "home":
                    home_cross_venue,

                "away":
                    away_cross_venue
            }
        },

        "integrity": {

            "match_by_match":
                True,

            "missing_values_invented":
                False,

            "frequencies_from_averages":
                False,

            "cross_average_is_projection":
                True,

            "cross_average_is_hit_rate":
                False,

            "insufficient_sample_can_recommend":
                False
        }
    }
