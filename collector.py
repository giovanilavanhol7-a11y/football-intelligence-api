import requests
from collections import defaultdict

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

TIMEOUT = 20


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


def empty_team_stats():
    return {
        "goals": 0,
        "shots": 0,
        "shots_on_target": 0,
        "corners": 0,
        "fouls_committed": 0,
        "yellow_cards": 0,
        "red_cards": 0
    }


def analyze_events(events):

    teams = defaultdict(empty_team_stats)

    for event in events:

        team_data = event.get("team")

        if not team_data:
            continue

        team = team_data.get("name")

        if not team:
            continue

        event_type = (
            event.get("type", {})
            .get("name", "")
        )

        # FINALIZAÇÕES
        if event_type == "Shot":

            teams[team]["shots"] += 1

            shot = event.get("shot", {})

            outcome = (
                shot.get("outcome", {})
                .get("name")
            )

            # GOL
            if outcome == "Goal":
                teams[team]["goals"] += 1

            # CHUTES NO GOL
            if outcome in [
                "Goal",
                "Saved",
                "Saved to Post"
            ]:
                teams[team]["shots_on_target"] += 1

        # ESCANTEIOS
        elif event_type == "Pass":

            play_pattern = (
                event.get("play_pattern", {})
                .get("name")
            )

            if play_pattern == "From Corner":
                teams[team]["corners"] += 1

        # FALTAS
        elif event_type == "Foul Committed":

            teams[team]["fouls_committed"] += 1

            foul = event.get(
                "foul_committed",
                {}
            )

            card = (
                foul.get("card", {})
                .get("name")
            )

            if card in [
                "Yellow Card",
                "Second Yellow"
            ]:
                teams[team]["yellow_cards"] += 1

            if card == "Red Card":
                teams[team]["red_cards"] += 1

        # CARTÕES EM BAD BEHAVIOUR
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

            if card == "Red Card":
                teams[team]["red_cards"] += 1

    return dict(teams)


def analyze_match(match_id):

    events = get_events(match_id)

    stats = analyze_events(events)

    return {
        "match_id": match_id,
        "source": "StatsBomb Open Data",
        "events_received": len(events),
        "teams": stats
    }
