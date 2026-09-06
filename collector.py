import requests
from collections import defaultdict
from datetime import datetime

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
TIMEOUT = 20


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
# ESTRUTURA
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
# EVENTOS
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

        # -------------------------------------------------
        # FINALIZAÇÕES
        # -------------------------------------------------

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

            if shot_type == "Corner":
                teams[team]["corners"] += 1

        # -------------------------------------------------
        # GOL CONTRA A FAVOR
        # -------------------------------------------------

        elif event_type == "Own Goal For":
            teams[team]["goals"] += 1

        # -------------------------------------------------
        # ESCANTEIOS
        # -------------------------------------------------

        elif event_type == "Pass":

            pass_data = event.get("pass", {})

            pass_type = (
                pass_data.get("type", {})
                .get("name")
            )

            if pass_type == "Corner":
                teams[team]["corners"] += 1

        # -------------------------------------------------
        # FALTAS
        # -------------------------------------------------

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

        # -------------------------------------------------
        # BAD BEHAVIOUR / CARTÕES
        # -------------------------------------------------

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
# UMA PARTIDA
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
# FREQUÊNCIAS
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

        stat_result = {}

        for line in lines:

            label = f"over_{line}"

            stat_result[label] = (
                calculate_frequency(
                    values,
                    line
                )
            )

        result[stat] = stat_result

    return result


# =========================================================
# FREQUÊNCIAS TOTAIS DA PARTIDA
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

        for stat in [
            "goals",
            "shots",
            "shots_on_target",
            "corners",
            "fouls_committed",
            "yellow_cards"
        ]:

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
# HISTÓRICO
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

    # -----------------------------------------------------
    # SELECIONA OS JOGOS
    # -----------------------------------------------------

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

            date_value = (
                datetime.strptime(
                    date_text,
                    "%Y-%m-%d"
                )
            )

        except Exception:
            continue

        team_matches.append({
            "date_value":
                date_value,

            "match":
                match
        })

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

    # -----------------------------------------------------
    # JOGO A JOGO
    # -----------------------------------------------------

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

        games.append(
            game
        )

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

    # -----------------------------------------------------
    # MÉDIAS
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # FREQUÊNCIAS REAIS
    # -----------------------------------------------------

    produced_frequencies = (
        build_frequencies(
            produced
        )
    )

    conceded_frequencies = (
        build_frequencies(
            conceded
        )
    )

    match_total_frequencies = (
        build_match_total_frequencies(
            games
        )
    )

    # -----------------------------------------------------
    # RESULTADO
    # -----------------------------------------------------

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
                produced_frequencies,

            "conceded":
                conceded_frequencies,

            "match_total":
                match_total_frequencies
        },

        "integrity": {
            "match_by_match":
                True,

            "missing_values_invented":
                False,

            "frequencies_from_averages":
                False,

            "frequency_denominator":
                "actual_valid_games"
        }
    }
