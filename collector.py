import requests
from collections import defaultdict

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
# ESTATÍSTICAS
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
# ANALISADOR
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

        # Garante a criação do time
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

            # xG
            xg = shot.get("statsbomb_xg")

            if isinstance(xg, (int, float)):
                teams[team]["xg"] += xg

            # Gol
            if outcome == "Goal":
                teams[team]["goals"] += 1

            # Chute no gol
            if outcome in [
                "Goal",
                "Saved",
                "Saved to Post"
            ]:
                teams[team]["shots_on_target"] += 1

            # Corner executado como finalização
            if shot_type == "Corner":
                teams[team]["corners"] += 1

        # =================================================
        # GOL CONTRA A FAVOR
        # =================================================

        elif event_type == "Own Goal For":

            teams[team]["goals"] += 1

        # =================================================
        # ESCANTEIO EXECUTADO COMO PASSE
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

            advantage = foul.get(
                "advantage"
            )

            foul_type = (
                foul.get("type", {})
                .get("name")
            )

            # StatsBomb:
            # não contar vantagem nem offside
            valid_foul = (
                advantage is not True
                and foul_type != "Offside"
            )

            if valid_foul:
                teams[team][
                    "fouls_committed"
                ] += 1

            # Cartão associado à falta
            card = (
                foul.get("card", {})
                .get("name")
            )

            if card in [
                "Yellow Card",
                "Second Yellow"
            ]:
                teams[team][
                    "yellow_cards"
                ] += 1

            if card in [
                "Red Card",
                "Second Yellow"
            ]:
                teams[team][
                    "red_cards"
                ] += 1

        # =================================================
        # CARTÕES — BAD BEHAVIOUR
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
                teams[team][
                    "yellow_cards"
                ] += 1

            if card in [
                "Red Card",
                "Second Yellow"
            ]:
                teams[team][
                    "red_cards"
                ] += 1

    # =====================================================
    # ARREDONDAMENTO xG
    # =====================================================

    result = {}

    for team, stats in teams.items():

        stats["xg"] = round(
            stats["xg"],
            2
        )

        result[team] = stats

    return result


# =========================================================
# PARTIDA
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
