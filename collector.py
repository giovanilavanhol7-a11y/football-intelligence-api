import requests
from collections import defaultdict
from datetime import datetime

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
TIMEOUT = 20

# =========================================================
# REGRAS DE INTEGRIDADE DA AMOSTRA
# =========================================================

MIN_VALID_SAMPLE = 4
MIN_COVERAGE = 0.80

INTEGRITY_NOTE = (
    "Confidence Score mede força da evidência e não probabilidade calibrada. "
    "X/20 é referência ampla. Frequências X/5/X/10 não confirmadas não foram "
    "inventadas. Linhas de AMBAS baseadas apenas em médias recebem penalização "
    "até fecharmos Produziu × Cedeu jogo a jogo."
)


# =========================================================
# FONTE
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
        f"{BASE_URL}/matches/"
        f"{competition_id}/{season_id}.json"
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

        event_type = event.get(
            "type", {}
        ).get("name", "")

        # -------------------------------------------------
        # FINALIZAÇÕES
        # -------------------------------------------------

        if event_type == "Shot":
            teams[team]["shots"] += 1

            shot = event.get("shot", {})

            outcome = shot.get(
                "outcome", {}
            ).get("name")

            shot_type = shot.get(
                "type", {}
            ).get("name")

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
            pass_type = event.get(
                "pass", {}
            ).get(
                "type", {}
            ).get("name")

            if pass_type == "Corner":
                teams[team]["corners"] += 1

        # -------------------------------------------------
        # FALTAS / CARTÕES
        # -------------------------------------------------

        elif event_type == "Foul Committed":
            foul = event.get(
                "foul_committed", {}
            )

            advantage = foul.get("advantage")

            foul_type = foul.get(
                "type", {}
            ).get("name")

            if (
                advantage is not True
                and foul_type != "Offside"
            ):
                teams[team][
                    "fouls_committed"
                ] += 1

            card = foul.get(
                "card", {}
            ).get("name")

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

        elif event_type == "Bad Behaviour":
            card = event.get(
                "bad_behaviour", {}
            ).get(
                "card", {}
            ).get("name")

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
        return match.get(
            "home_team", {}
        ).get("home_team_name")

    return match.get(
        "away_team", {}
    ).get("away_team_name")


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
# LINHAS DE MERCADO
# =========================================================

FREQUENCY_LINES = {
    "goals": [
        0.5, 1.5, 2.5
    ],

    "shots": [
        7.5, 8.5, 9.5,
        10.5, 11.5, 12.5
    ],

    "shots_on_target": [
        1.5, 2.5, 3.5,
        4.5, 5.5, 6.5
    ],

    "corners": [
        2.5, 3.5, 4.5,
        5.5, 6.5, 7.5,
        8.5, 9.5
    ],

    "fouls_committed": [
        7.5, 8.5, 9.5,
        10.5, 11.5, 12.5
    ],

    "yellow_cards": [
        0.5, 1.5, 2.5,
        3.5, 4.5
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
            hits / total * 100,
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
            result[stat][
                f"over_{line}"
            ] = calculate_frequency(
                values,
                line
            )

    return result


def build_match_total_frequencies(games):
    total_values = defaultdict(list)

    for game in games:
        produced = game.get(
            "produced", {}
        )

        conceded = game.get(
            "conceded", {}
        )

        for stat in FREQUENCY_LINES:
            a = produced.get(stat)
            b = conceded.get(stat)

            if (
                isinstance(a, (int, float))
                and isinstance(b, (int, float))
            ):
                total_values[stat].append(
                    a + b
                )

    return build_frequencies(
        total_values
    )


# =========================================================
# QUALIDADE DA AMOSTRA
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

    coverage_ratio = (
        matches_analyzed
        / requested_matches
    )

    coverage = round(
        coverage_ratio * 100,
        1
    )

    valid = (
        matches_analyzed >= MIN_VALID_SAMPLE
        and
        coverage_ratio >= MIN_COVERAGE
    )

    return {
        "status":
            "valid"
            if valid
            else "insufficient_data",

        "valid": valid,
        "matches": matches_analyzed,
        "requested": requested_matches,
        "coverage": coverage
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
# HISTÓRICO DO TIME
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
            "date_value": date_value,
            "match": match
        })

    team_matches.sort(
        key=lambda item:
            item["date_value"],
        reverse=True
    )

    selected = team_matches[:limit]

    games = []

    produced = defaultdict(list)
    conceded = defaultdict(list)

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
            "match_id": match_id,
            "date": match.get(
                "match_date"
            ),
            "home": home,
            "away": away,
            "venue": location,
            "opponent": opponent_name,
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

    produced_averages = {
        stat: average(values)
        for stat, values
        in produced.items()
    }

    conceded_averages = {
        stat: average(values)
        for stat, values
        in conceded.items()
    }

    sample_quality = evaluate_sample(
        len(games),
        limit
    )

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
        and
        opponent_sample["valid"]
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
            team_produced.get(
                stat
            )
        )

        conceded_value = (
            opponent_conceded.get(
                stat
            )
        )

        result[stat] = {
            "team_produced_average":
                produced_value,

            "opponent_conceded_average":
                conceded_value,

            "cross_average":
                cross_stat(
                    produced_value,
                    conceded_value
                ),

            "sample_valid":
                cross_valid,

            "confidence":
                (
                    "eligible"
                    if cross_valid
                    else
                    "insufficient_data"
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
        "samples": samples,

        "general_cross": {
            "valid":
                general_valid,
            "confidence":
                (
                    "eligible"
                    if general_valid
                    else
                    "insufficient_data"
                )
        },

        "home_away_cross": {
            "valid":
                home_away_valid,
            "confidence":
                (
                    "eligible"
                    if home_away_valid
                    else
                    "insufficient_data"
                )
        },

        "integrity_rule":
            (
                "Amostra valida exige no minimo "
                "4 jogos e pelo menos 80% de "
                "cobertura da amostra solicitada. "
                "Amostras insuficientes podem ser "
                "exibidas, mas nao podem gerar "
                "confianca ou recomendacao."
            )
    }


# =========================================================
# CONFIDENCE SCORE
# =========================================================

def confidence_label(score):
    if score is None:
        return "DADOS INSUFICIENTES"

    if score >= 17:
        return "FORTE"

    if score >= 14:
        return "BOA"

    if score >= 10:
        return "MODERADA"

    return "FRACA"


def frequency_points(rate):
    if not isinstance(
        rate,
        (int, float)
    ):
        return 0

    if rate >= 100:
        return 8

    if rate >= 80:
        return 7

    if rate >= 70:
        return 6

    if rate >= 60:
        return 5

    if rate >= 50:
        return 3

    if rate >= 40:
        return 2

    return 0


def projection_points(
    projection,
    line
):
    if not isinstance(
        projection,
        (int, float)
    ):
        return 0

    margin = (
        projection - line
    )

    if margin >= 3:
        return 6

    if margin >= 2:
        return 5

    if margin >= 1:
        return 4

    if margin >= 0.5:
        return 3

    if margin > 0:
        return 1

    return 0


def venue_points(
    general_rate,
    venue_rate
):
    if not isinstance(
        venue_rate,
        (int, float)
    ):
        return 0

    if venue_rate >= 80:
        return 4

    if venue_rate >= 60:
        return 3

    if venue_rate >= 50:
        return 2

    if (
        isinstance(
            general_rate,
            (int, float)
        )
        and
        venue_rate >= general_rate
    ):
        return 1

    return 0


def get_frequency(
    history,
    section,
    stat,
    line
):
    frequency = (
        history
        .get("frequencies", {})
        .get(section, {})
        .get(stat, {})
        .get(
            f"over_{line}"
        )
    )

    if not frequency:
        return {
            "hits": 0,
            "sample": 0,
            "rate": None
        }

    return frequency


# =========================================================
# OPORTUNIDADE INDIVIDUAL DE TIME
# =========================================================

def build_team_opportunity(
    team_name,
    side,
    stat,
    line,
    general_history,
    venue_history,
    opponent_general,
    opponent_venue,
    general_cross,
    venue_cross
):
    general_sample = (
        evaluate_history_sample(
            general_history
        )
    )

    venue_sample = (
        evaluate_history_sample(
            venue_history
        )
    )

    opponent_general_sample = (
        evaluate_history_sample(
            opponent_general
        )
    )

    opponent_venue_sample = (
        evaluate_history_sample(
            opponent_venue
        )
    )

    samples_valid = (
        general_sample["valid"]
        and
        venue_sample["valid"]
        and
        opponent_general_sample["valid"]
        and
        opponent_venue_sample["valid"]
    )

    general_frequency = (
        get_frequency(
            general_history,
            "produced",
            stat,
            line
        )
    )

    venue_frequency = (
        get_frequency(
            venue_history,
            "produced",
            stat,
            line
        )
    )

    opponent_conceded_general = (
        get_frequency(
            opponent_general,
            "conceded",
            stat,
            line
        )
    )

    opponent_conceded_venue = (
        get_frequency(
            opponent_venue,
            "conceded",
            stat,
            line
        )
    )

    general_projection = (
        general_cross
        .get(stat, {})
        .get("cross_average")
    )

    venue_projection = (
        venue_cross
        .get(stat, {})
        .get("cross_average")
    )

    if not samples_valid:
        return {
            "team":
                team_name,
            "side":
                side,
            "stat":
                stat,
            "market":
                f"over_{line}",
            "line":
                line,
            "eligible":
                False,
            "confidence_score":
                None,
            "confidence_label":
                "DADOS INSUFICIENTES",

            "evidence": {
                "team_general":
                    general_frequency,

                "team_venue":
                    venue_frequency,

                "opponent_conceded_general":
                    opponent_conceded_general,

                "opponent_conceded_venue":
                    opponent_conceded_venue,

                "general_projection":
                    general_projection,

                "venue_projection":
                    venue_projection
            },

            "reason":
                (
                    "Amostra insuficiente "
                    "para gerar recomendacao."
                )
        }

    rates = [
        general_frequency.get(
            "rate"
        ),
        venue_frequency.get(
            "rate"
        ),
        opponent_conceded_general.get(
            "rate"
        ),
        opponent_conceded_venue.get(
            "rate"
        )
    ]

    valid_rates = [
        rate
        for rate in rates
        if isinstance(
            rate,
            (int, float)
        )
    ]

    if len(valid_rates) < 4:
        return {
            "team":
                team_name,
            "side":
                side,
            "stat":
                stat,
            "market":
                f"over_{line}",
            "line":
                line,
            "eligible":
                False,
            "confidence_score":
                None,
            "confidence_label":
                "DADOS INSUFICIENTES",
            "reason":
                (
                    "Frequencias necessarias "
                    "nao estao completas."
                )
        }

    combined_rate = round(
        sum(valid_rates)
        / len(valid_rates),
        1
    )

    # Máximo:
    # frequência = 8
    # projeção = 6
    # casa/fora = 4
    # concordância = 2
    # TOTAL = 20

    score = 0

    frequency_score = (
        frequency_points(
            combined_rate
        )
    )

    projection_score = (
        projection_points(
            venue_projection,
            line
        )
    )

    venue_score = (
        venue_points(
            general_frequency.get(
                "rate"
            ),
            venue_frequency.get(
                "rate"
            )
        )
    )

    score += frequency_score
    score += projection_score
    score += venue_score

    agreement_points = 0

    if (
        isinstance(
            venue_projection,
            (int, float)
        )
        and
        venue_projection > line
    ):
        agreement_points += 1

    if (
        venue_frequency.get(
            "rate",
            0
        ) >= 60
        and
        opponent_conceded_venue.get(
            "rate",
            0
        ) >= 60
    ):
        agreement_points += 1

    score += agreement_points

    score = min(
        score,
        20
    )

    eligible = (
        combined_rate >= 50
        and
        isinstance(
            venue_projection,
            (int, float)
        )
        and
        venue_projection > line
        and
        score >= 10
    )

    return {
        "team":
            team_name,
        "side":
            side,
        "stat":
            stat,
        "market":
            f"over_{line}",
        "line":
            line,

        "eligible":
            eligible,

        "confidence_score":
            score,

        "confidence_label":
            confidence_label(
                score
            ),

        "combined_evidence_rate":
            combined_rate,

        "evidence": {
            "team_general":
                general_frequency,

            "team_venue":
                venue_frequency,

            "opponent_conceded_general":
                opponent_conceded_general,

            "opponent_conceded_venue":
                opponent_conceded_venue,

            "general_projection":
                general_projection,

            "venue_projection":
                venue_projection
        },

        "score_breakdown": {
            "frequency":
                frequency_score,

            "projection":
                projection_score,

            "venue":
                venue_score,

            "agreement":
                agreement_points
        }
    }


# =========================================================
# MOTOR DE OPORTUNIDADES
# =========================================================

def build_opportunities(
    home_team,
    away_team,
    home_general,
    away_general,
    home_at_home,
    away_at_away,
    home_cross_general,
    away_cross_general,
    home_cross_venue,
    away_cross_venue
):
    opportunities = []

    for stat, lines in (
        FREQUENCY_LINES.items()
    ):
        for line in lines:

            home_opportunity = (
                build_team_opportunity(
                    team_name=
                        home_team,

                    side=
                        "home",

                    stat=
                        stat,

                    line=
                        line,

                    general_history=
                        home_general,

                    venue_history=
                        home_at_home,

                    opponent_general=
                        away_general,

                    opponent_venue=
                        away_at_away,

                    general_cross=
                        home_cross_general,

                    venue_cross=
                        home_cross_venue
                )
            )

            away_opportunity = (
                build_team_opportunity(
                    team_name=
                        away_team,

                    side=
                        "away",

                    stat=
                        stat,

                    line=
                        line,

                    general_history=
                        away_general,

                    venue_history=
                        away_at_away,

                    opponent_general=
                        home_general,

                    opponent_venue=
                        home_at_home,

                    general_cross=
                        away_cross_general,

                    venue_cross=
                        away_cross_venue
                )
            )

            opportunities.append(
                home_opportunity
            )

            opportunities.append(
                away_opportunity
            )

    eligible = [
        item
        for item in opportunities
        if item.get(
            "eligible"
        ) is True
    ]

    eligible.sort(
        key=lambda item: (
            item.get(
                "confidence_score",
                0
            ),
            item.get(
                "combined_evidence_rate",
                0
            )
        ),
        reverse=True
    )

    blocked = [
        item
        for item in opportunities
        if item.get(
            "eligible"
        ) is False
    ]

    return {
        "top_opportunities":
            eligible[:10],

        "eligible_total":
            len(eligible),

        "evaluated_total":
            len(opportunities),

        "blocked_total":
            len(blocked),

        "confidence_scale": {
            "17_20":
                "FORTE",
            "14_16":
                "BOA",
            "10_13":
                "MODERADA",
            "0_9":
                "FRACA"
        },

        "integrity_note":
            INTEGRITY_NOTE
    }


# =========================================================
# ANÁLISE PRÉ-JOGO
# =========================================================

def analyze_prematch(
    competition_id,
    season_id,
    home_team,
    away_team,
    limit=5
):
    home_general = (
        analyze_team_history(
            competition_id,
            season_id,
            home_team,
            limit=limit,
            venue="all"
        )
    )

    away_general = (
        analyze_team_history(
            competition_id,
            season_id,
            away_team,
            limit=limit,
            venue="all"
        )
    )

    home_at_home = (
        analyze_team_history(
            competition_id,
            season_id,
            home_team,
            limit=limit,
            venue="home"
        )
    )

    away_at_away = (
        analyze_team_history(
            competition_id,
            season_id,
            away_team,
            limit=limit,
            venue="away"
        )
    )

    home_cross_general = (
        build_cross(
            home_general,
            away_general
        )
    )

    away_cross_general = (
        build_cross(
            away_general,
            home_general
        )
    )

    home_cross_venue = (
        build_cross(
            home_at_home,
            away_at_away
        )
    )

    away_cross_venue = (
        build_cross(
            away_at_away,
            home_at_home
        )
    )

    sample_quality = (
        evaluate_prematch_samples(
            home_general,
            away_general,
            home_at_home,
            away_at_away
        )
    )

    opportunities = (
        build_opportunities(
            home_team=
                home_team,

            away_team=
                away_team,

            home_general=
                home_general,

            away_general=
                away_general,

            home_at_home=
                home_at_home,

            away_at_away=
                away_at_away,

            home_cross_general=
                home_cross_general,

            away_cross_general=
                away_cross_general,

            home_cross_venue=
                home_cross_venue,

            away_cross_venue=
                away_cross_venue
        )
    )

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

        "opportunities":
            opportunities,

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
                False,

            "confidence_score_is_probability":
                False,

            "minimum_valid_games":
                MIN_VALID_SAMPLE,

            "minimum_coverage":
                MIN_COVERAGE,

            "integrity_note":
                INTEGRITY_NOTE
        }
    }
