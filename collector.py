import requests
from collections import defaultdict
from datetime import datetime

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
TIMEOUT = 20


# =========================================================
# DOWNLOAD
# =========================================================

def download_json(url):
    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


# =========================================================
# FONTE
# =========================================================

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
        # BAD BEHAVIOUR
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
# UTILIDADES DO HISTÓRICO
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

        if team_name not in [home, away]:
            continue

        if venue == "home" and home != team_name:
            continue

        if venue == "away" and away != team_name:
            continue

        date_text = match.get("match_date")

        try:
            date_value = datetime.strptime(
                date_text,
                "%Y-%m-%d"
            )
        except Exception:
            continue

        team_matches.append({
            "date_value": date_value,
            "match": match
        })

    # Mais recentes primeiro
    team_matches.sort(
        key=lambda item: item["date_value"],
        reverse=True
    )

    selected = team_matches[:limit]

    games = []

    produced = defaultdict(list)
    conceded = defaultdict(list)

    # =====================================================
    # ANALISA JOGO POR JOGO
    # =====================================================

    for item in selected:

        match = item["match"]

        match_id = match.get("match_id")

        home = team_name_from_match(
            match,
            "home"
        )

        away = team_name_from_match(
            match,
            "away"
        )

        events = get_events(match_id)

        stats = analyze_events(events)

        team_stats = stats.get(team_name)

        opponent_name, opponent_stats = (
            find_opponent(
                stats,
                team_name
            )
        )

        # Nunca inventamos dado ausente
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
            "match_id": match_id,
            "date": match.get("match_date"),
            "home": home,
            "away": away,
            "venue": location,
            "opponent": opponent_name,

            "produced": dict(team_stats),
            "conceded": dict(opponent_stats)
        }

        games.append(game)

        for stat, value in team_stats.items():
            produced[stat].append(value)

        for stat, value in opponent_stats.items():
            conceded[stat].append(value)

    # =====================================================
    # MÉDIAS REAIS
    # =====================================================

    produced_averages = {}

    conceded_averages = {}

    for stat, values in produced.items():
        produced_averages[stat] = average(
            values
        )

    for stat, values in conceded.items():
        conceded_averages[stat] = average(
            values
        )

    # =====================================================
    # RESULTADO
    # =====================================================

    return {
        "team": team_name,

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

        "integrity": {
            "match_by_match":
                True,

            "missing_values_invented":
                False,

            "frequencies_from_averages":
                False
        }
    }
