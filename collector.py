import requests
from collections import defaultdict

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

TIMEOUT = 20


# =========================================================
# DOWNLOAD
# =========================================================

def download_json(url):
    response = requests.get(
        url,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    return response.json()


# =========================================================
# COMPETIÇÕES
# =========================================================

def get_competitions():
    return download_json(
        f"{BASE_URL}/competitions.json"
    )


# =========================================================
# PARTIDAS
# =========================================================

def get_matches(
    competition_id,
    season_id
):
    return download_json(
        f"{BASE_URL}/matches/"
        f"{competition_id}/"
        f"{season_id}.json"
    )


# =========================================================
# EVENTOS
# =========================================================

def get_events(match_id):
    return download_json(
        f"{BASE_URL}/events/"
        f"{match_id}.json"
    )


# =========================================================
# ESTRUTURA DE ESTATÍSTICAS
# =========================================================

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


# =========================================================
# ANALISADOR DE EVENTOS
# =========================================================

def analyze_events(events):

    teams = defaultdict(
        empty_team_stats
    )

    for event in events:

        # -----------------------------------------
        # TIME
        # -----------------------------------------

        team_data = event.get(
            "team"
        )

        if not team_data:
            continue

        team = team_data.get(
            "name"
        )

        if not team:
            continue

        # Garante que o time exista
        # mesmo que o evento atual não gere stat.
        _ = teams[team]

        # -----------------------------------------
        # TIPO DO EVENTO
        # -----------------------------------------

        event_type = (
            event
            .get("type", {})
            .get("name", "")
        )

        # =========================================
        # FINALIZAÇÕES
        # =========================================

        if event_type == "Shot":

            teams[team][
                "shots"
            ] += 1

            shot = event.get(
                "shot",
                {}
            )

            outcome = (
                shot
                .get("outcome", {})
                .get("name")
            )

            # -------------------------------------
            # GOLS
            # -------------------------------------

            if outcome == "Goal":

                teams[team][
                    "goals"
                ] += 1

            # -------------------------------------
            # CHUTES NO GOL
            # -------------------------------------

            if outcome in [
                "Goal",
                "Saved",
                "Saved to Post"
            ]:

                teams[team][
                    "shots_on_target"
                ] += 1

        # =========================================
        # ESCANTEIOS
        # =========================================
        #
        # IMPORTANTE:
        #
        # NÃO usamos:
        #
        # play_pattern == "From Corner"
        #
        # porque vários eventos posteriores
        # podem continuar pertencendo à jogada
        # iniciada no escanteio.
        #
        # Contamos somente a cobrança:
        #
        # pass.type.name == "Corner"
        # =========================================

        elif event_type == "Pass":

            pass_data = event.get(
                "pass",
                {}
            )

            pass_type = (
                pass_data
                .get("type", {})
                .get("name")
            )

            if pass_type == "Corner":

                teams[team][
                    "corners"
                ] += 1

        # =========================================
        # FALTAS COMETIDAS
        # =========================================

        elif event_type == "Foul Committed":

            teams[team][
                "fouls_committed"
            ] += 1

            foul = event.get(
                "foul_committed",
                {}
            )

            card = (
                foul
                .get("card", {})
                .get("name")
            )

            # -------------------------------------
            # AMARELO
            # -------------------------------------

            if card in [
                "Yellow Card",
                "Second Yellow"
            ]:

                teams[team][
                    "yellow_cards"
                ] += 1

            # -------------------------------------
            # VERMELHO
            # -------------------------------------

            if card in [
                "Red Card",
                "Second Yellow"
            ]:

                teams[team][
                    "red_cards"
                ] += 1

        # =========================================
        # BAD BEHAVIOUR / CARTÕES
        # =========================================

        elif event_type == "Bad Behaviour":

            behaviour = event.get(
                "bad_behaviour",
                {}
            )

            card = (
                behaviour
                .get("card", {})
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

    return dict(teams)


# =========================================================
# ANALISAR PARTIDA
# =========================================================

def analyze_match(match_id):

    events = get_events(
        match_id
    )

    stats = analyze_events(
        events
    )

    return {
        "match_id":
            match_id,

        "source":
            "StatsBomb Open Data",

        "events_received":
            len(events),

        "teams":
            stats
    }
