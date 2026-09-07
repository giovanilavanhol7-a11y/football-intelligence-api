import os
import requests
from datetime import datetime, timedelta
from functools import lru_cache


# =========================================================
# CONFIGURAÇÃO
# =========================================================

SPORTMONKS_BASE_URL = "https://api.sportmonks.com/v3/football"
SPORTMONKS_API_TOKEN = os.getenv("SPORTMONKS_API_TOKEN")

TIMEOUT = 30
SEASON = "2026/27"

MIN_VALID_SAMPLE = 4
MIN_COVERAGE = 0.80
MIN_RECOMMENDATION_SCORE = 10.0

ACTIVE_STATS = ["goals", "corners", "yellow_cards", "red_cards"]

STAT_FIELDS = [
    "goals", "xg", "shots", "shots_on_target",
    "corners", "fouls_committed", "yellow_cards", "red_cards"
]

WINDOWS = (5, 10)

INTEGRITY_NOTE_2627 = (
    "Confidence Score mede força da evidência e não probabilidade calibrada. "
    "X/20 é referência ampla. Frequências X/5/X/10 não confirmadas não foram inventadas. "
    "Linhas de AMBAS baseadas apenas em médias recebem penalização até fecharmos "
    "Produziu × Cedeu jogo a jogo. Dado ausente permanece null e nunca é convertido "
    "em zero. Médias de Produzido × Cedido são usadas apenas como apoio e não são "
    "tratadas como taxa de acerto. Recortes Casa × Fora com amostra insuficiente não "
    "aumentam o Confidence Score. Somente mercados com Confidence Score mínimo de "
    "10/20 podem entrar no ranking de oportunidades."
)

MARKET_LINES = {
    "goals": [0.5, 1.5, 2.5],
    "corners": [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5],
    "yellow_cards": [0.5, 1.5, 2.5, 3.5, 4.5],
    "red_cards": [0.5],
}

CONFIRMED_TYPE_IDS = {
    34: "corners",
    52: "goals",
    83: "red_cards",
    84: "yellow_cards",
}

STAT_CODE_MAP = {
    "goals": "goals",
    "corners": "corners",
    "yellowcards": "yellow_cards",
    "yellow-cards": "yellow_cards",
    "redcards": "red_cards",
    "red-cards": "red_cards",
    "shots-total": "shots",
    "total-shots": "shots",
    "shots": "shots",
    "shots-on-target": "shots_on_target",
    "shots-ontarget": "shots_on_target",
    "fouls": "fouls_committed",
    "fouls-committed": "fouls_committed",
    "expected-goals": "xg",
    "expected-goals-xg": "xg",
    "xg": "xg",
}


# =========================================================
# UTILIDADES
# =========================================================

def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def normalize_number(value):
    if value is None:
        return None
    if is_number(value):
        return value
    try:
        text = str(value).strip()
        if not text:
            return None
        number = float(text.replace(",", "."))
        return int(number) if number.is_integer() else round(number, 3)
    except (TypeError, ValueError):
        return None


def empty_stats():
    return {field: None for field in STAT_FIELDS}


def normalize_stats(stats):
    stats = stats if isinstance(stats, dict) else {}
    return {field: normalize_number(stats.get(field)) for field in STAT_FIELDS}


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d")


def average(values):
    return round(sum(values) / len(values), 2) if values else None


def _safe_date(before_date):
    return before_date or datetime.utcnow().strftime("%Y-%m-%d")


# =========================================================
# SPORTMONKS
# =========================================================

def sportmonks_request(endpoint, params=None):
    if not SPORTMONKS_API_TOKEN:
        raise RuntimeError("SPORTMONKS_API_TOKEN não configurado no servidor.")

    query = dict(params or {})
    query["api_token"] = SPORTMONKS_API_TOKEN
    url = f"{SPORTMONKS_BASE_URL}/{endpoint.lstrip('/')}"

    response = requests.get(url, params=query, timeout=TIMEOUT)

    if response.status_code == 401:
        raise RuntimeError("Sportmonks recusou o token (HTTP 401).")
    if response.status_code == 403:
        raise RuntimeError("Sportmonks bloqueou este recurso para o plano atual (HTTP 403).")

    response.raise_for_status()
    return response.json()


def test_sportmonks_connection():
    if not SPORTMONKS_API_TOKEN:
        return {"connected": False, "authenticated": False, "reason": "token_not_configured"}
    try:
        payload = sportmonks_request("fixtures", {"per_page": 1})
        data = payload.get("data", [])
        return {
            "connected": True,
            "authenticated": True,
            "response_valid": isinstance(data, list),
            "fixtures_received": len(data) if isinstance(data, list) else 0,
        }
    except Exception as error:
        return {
            "connected": False,
            "authenticated": False,
            "reason": "connection_error",
            "error": str(error),
        }


def get_sportmonks_fixtures_by_date(date):
    parse_date(date)
    payload = sportmonks_request(f"fixtures/date/{date}", {"include": "participants;state"})
    data = payload.get("data", [])
    return data if isinstance(data, list) else []


@lru_cache(maxsize=512)
def get_sportmonks_fixture(fixture_id):
    payload = sportmonks_request(
        f"fixtures/{fixture_id}",
        {"include": "participants;state;scores;statistics.type"},
    )
    return payload.get("data")


@lru_cache(maxsize=128)
def _get_team_fixtures_between_cached(team_id, start_date, end_date):
    payload = sportmonks_request(
        f"fixtures/between/{start_date}/{end_date}/{team_id}",
        {
            "include": "participants;state",
            "order": "desc",
            "per_page": 50,
        },
    )
    data = payload.get("data", [])
    return tuple(data) if isinstance(data, list) else tuple()


def get_team_fixtures_between(team_id, start_date, end_date):
    parse_date(start_date)
    parse_date(end_date)
    return list(_get_team_fixtures_between_cached(int(team_id), start_date, end_date))


# =========================================================
# FIXTURES / NORMALIZAÇÃO
# =========================================================

def extract_participants(fixture):
    home = away = None
    participants = fixture.get("participants", [])
    if not isinstance(participants, list):
        participants = []

    for participant in participants:
        if not isinstance(participant, dict):
            continue
        meta = participant.get("meta", {})
        meta = meta if isinstance(meta, dict) else {}
        item = {
            "id": participant.get("id"),
            "name": participant.get("name"),
            "short_code": participant.get("short_code"),
        }
        if meta.get("location") == "home":
            home = item
        elif meta.get("location") == "away":
            away = item
    return home, away


def normalize_sportmonks_fixture(fixture):
    if not isinstance(fixture, dict):
        return None
    home, away = extract_participants(fixture)
    state = fixture.get("state", {})
    state = state if isinstance(state, dict) else {}
    starting_at = fixture.get("starting_at")

    return {
        "match_id": fixture.get("id"),
        "source_match_id": fixture.get("id"),
        "source": "Sportmonks",
        "season": SEASON,
        "league_id": fixture.get("league_id"),
        "season_id": fixture.get("season_id"),
        "date": starting_at[:10] if starting_at else None,
        "kick_off": starting_at,
        "status": (
            state.get("developer_name")
            or state.get("state")
            or state.get("short_name")
        ),
        "name": fixture.get("name"),
        "home_team": home,
        "away_team": away,
        "result_info": fixture.get("result_info"),
    }


def fixtures_2627_by_date(date):
    fixtures = []
    for raw in get_sportmonks_fixtures_by_date(date):
        normalized = normalize_sportmonks_fixture(raw)
        if normalized:
            fixtures.append(normalized)
    return {
        "season": SEASON,
        "date": date,
        "source": "Sportmonks",
        "total": len(fixtures),
        "fixtures": fixtures,
    }


def normalize_stat_code(value):
    if value is None:
        return None
    return str(value).strip().lower().replace("_", "-").replace(" ", "-")


def identify_stat_field(stat):
    if not isinstance(stat, dict):
        return None
    type_id = stat.get("type_id")
    if type_id in CONFIRMED_TYPE_IDS:
        return CONFIRMED_TYPE_IDS[type_id]

    stat_type = stat.get("type", {})
    if not isinstance(stat_type, dict):
        return None

    for raw in (stat_type.get("code"), stat_type.get("developer_name")):
        code = normalize_stat_code(raw)
        if code in STAT_CODE_MAP:
            return STAT_CODE_MAP[code]
    return None


def parse_fixture_statistics(fixture):
    home_stats, away_stats = empty_stats(), empty_stats()
    recognized, unrecognized = [], []

    statistics = fixture.get("statistics", [])
    if not isinstance(statistics, list):
        statistics = []

    for stat in statistics:
        if not isinstance(stat, dict):
            continue

        field = identify_stat_field(stat)
        stat_type = stat.get("type", {})
        stat_type = stat_type if isinstance(stat_type, dict) else {}
        data = stat.get("data", {})
        data = data if isinstance(data, dict) else {}

        type_id = stat.get("type_id")
        code = stat_type.get("code")
        developer_name = stat_type.get("developer_name")
        location = stat.get("location")
        value = normalize_number(data.get("value"))

        if not field:
            unrecognized.append({
                "type_id": type_id,
                "code": code,
                "developer_name": developer_name,
                "location": location,
                "value": value,
            })
            continue

        recognized.append({
            "field": field,
            "type_id": type_id,
            "code": code,
            "location": location,
            "value": value,
        })

        if location == "home":
            home_stats[field] = value
        elif location == "away":
            away_stats[field] = value

    return {
        "home": home_stats,
        "away": away_stats,
        "recognized": recognized,
        "unrecognized": unrecognized,
    }


def normalize_fixture_with_stats(fixture):
    basic = normalize_sportmonks_fixture(fixture)
    if basic is None:
        return None

    parsed = parse_fixture_statistics(fixture)
    home_team, away_team = basic.get("home_team"), basic.get("away_team")

    return {
        **basic,
        "teams": {
            "home": {
                "team": home_team.get("name") if isinstance(home_team, dict) else None,
                "team_id": home_team.get("id") if isinstance(home_team, dict) else None,
                "stats": parsed["home"],
            },
            "away": {
                "team": away_team.get("name") if isinstance(away_team, dict) else None,
                "team_id": away_team.get("id") if isinstance(away_team, dict) else None,
                "stats": parsed["away"],
            },
        },
        "stat_parser": {
            "recognized": parsed["recognized"],
            "unrecognized": parsed["unrecognized"],
        },
    }


def analyze_fixture_2627(fixture_id):
    fixture = get_sportmonks_fixture(fixture_id)
    return normalize_fixture_with_stats(fixture) if fixture else None


# =========================================================
# COBERTURA / VISÃO DO TIME
# =========================================================

def stats_coverage(stats):
    stats = stats if isinstance(stats, dict) else {}
    available = sum(1 for field in STAT_FIELDS if is_number(stats.get(field)))
    total = len(STAT_FIELDS)
    return {
        "available": available,
        "total": total,
        "coverage": round(available / total * 100, 1),
    }


def match_coverage(match):
    teams = match.get("teams", {}) if isinstance(match, dict) else {}
    home, away = teams.get("home", {}), teams.get("away", {})
    return {
        "home": stats_coverage(home.get("stats", {}) if isinstance(home, dict) else {}),
        "away": stats_coverage(away.get("stats", {}) if isinstance(away, dict) else {}),
    }


def team_view(match, team_id):
    if not isinstance(match, dict):
        return None

    teams = match.get("teams", {})
    home, away = teams.get("home", {}), teams.get("away", {})
    home = home if isinstance(home, dict) else {}
    away = away if isinstance(away, dict) else {}

    if home.get("team_id") == team_id:
        own, opponent, venue = home, away, "home"
    elif away.get("team_id") == team_id:
        own, opponent, venue = away, home, "away"
    else:
        return None

    return {
        "match_id": match.get("match_id"),
        "date": match.get("date"),
        "venue": venue,
        "team": own.get("team"),
        "team_id": team_id,
        "opponent": opponent.get("team"),
        "opponent_id": opponent.get("team_id"),
        "produced": normalize_stats(own.get("stats", {})),
        "conceded": normalize_stats(opponent.get("stats", {})),
    }


# =========================================================
# MÉDIAS / FREQUÊNCIAS / QUALIDADE
# =========================================================

def valid_values(history, side, field):
    values = []
    for match in history:
        stats = match.get(side, {})
        if isinstance(stats, dict) and is_number(stats.get(field)):
            values.append(stats[field])
    return values


def history_averages(history):
    result = {"produced": {}, "conceded": {}}
    for field in ACTIVE_STATS:
        for side in ("produced", "conceded"):
            values = valid_values(history, side, field)
            result[side][field] = {"average": average(values), "sample": len(values)}
    return result


def calculate_hit_rate(history, side, field, line):
    values = valid_values(history, side, field)
    if not values:
        return {"line": line, "hits": None, "sample": 0, "rate": None}
    hits = sum(1 for value in values if value > line)
    return {
        "line": line,
        "hits": hits,
        "sample": len(values),
        "rate": round(hits / len(values) * 100, 1),
    }


def build_frequencies(history):
    result = {}
    for field in ACTIVE_STATS:
        result[field] = {"produced": [], "conceded": []}
        for line in MARKET_LINES.get(field, []):
            result[field]["produced"].append(
                calculate_hit_rate(history, "produced", field, line)
            )
            result[field]["conceded"].append(
                calculate_hit_rate(history, "conceded", field, line)
            )
    return result


def sample_quality(actual, requested):
    if requested <= 0:
        return {
            "valid": False, "matches": actual, "requested": requested,
            "coverage": None, "status": "insufficient_data",
        }
    ratio = actual / requested
    valid = actual >= MIN_VALID_SAMPLE and ratio >= MIN_COVERAGE
    return {
        "valid": valid,
        "matches": actual,
        "requested": requested,
        "coverage": round(ratio * 100, 1),
        "status": "valid" if valid else "insufficient_data",
    }


def metric_side_quality(history, side, field, requested):
    actual = len(valid_values(history, side, field))
    ratio = actual / requested if requested > 0 else 0
    valid = actual >= MIN_VALID_SAMPLE and ratio >= MIN_COVERAGE
    return {
        "valid": valid,
        "sample": actual,
        "requested": requested,
        "coverage": round(ratio * 100, 1),
        "status": "valid" if valid else "insufficient_data",
    }


def metric_quality(history, field, requested):
    produced = metric_side_quality(history, "produced", field, requested)
    conceded = metric_side_quality(history, "conceded", field, requested)
    valid = produced["valid"] and conceded["valid"]
    return {
        "valid": valid,
        "produced": produced,
        "conceded": conceded,
        "status": "valid" if valid else "insufficient_data",
    }


def build_metric_quality(history, requested):
    return {field: metric_quality(history, field, requested) for field in ACTIVE_STATS}


# =========================================================
# COLETA ÚNICA ATÉ 10 JOGOS
# =========================================================

def collect_team_history_2627(team_id, season_id, limit=5, venue="all", before_date=None):
    if limit not in WINDOWS:
        raise ValueError("limit deve ser 5 ou 10")
    if venue not in ("all", "home", "away"):
        raise ValueError("venue deve ser all, home ou away")

    before_dt = parse_date(before_date) if before_date else datetime.utcnow()
    start_dt = before_dt - timedelta(days=365)
    end_dt = before_dt - timedelta(days=1)

    raw_fixtures = get_team_fixtures_between(
        team_id,
        start_dt.strftime("%Y-%m-%d"),
        end_dt.strftime("%Y-%m-%d"),
    )

    candidates = []
    for raw in raw_fixtures:
        if not isinstance(raw, dict) or raw.get("season_id") != season_id:
            continue
        state = raw.get("state", {})
        state = state if isinstance(state, dict) else {}
        state_code = (
            state.get("developer_name")
            or state.get("short_name")
            or state.get("state")
        )
        if state_code != "FT" or not raw.get("starting_at"):
            continue
        candidates.append(raw)

    candidates.sort(key=lambda item: item.get("starting_at") or "", reverse=True)

    history = []
    for candidate in candidates:
        fixture_id = candidate.get("id")
        if not fixture_id:
            continue
        complete = get_sportmonks_fixture(fixture_id)
        if not complete:
            continue
        normalized = normalize_fixture_with_stats(complete)
        view = team_view(normalized, team_id) if normalized else None
        if not view:
            continue
        if venue != "all" and view.get("venue") != venue:
            continue
        history.append(view)
        if len(history) >= limit:
            break

    return history


def analyze_team_history_2627(team_id, season_id, limit=5, venue="all", before_date=None):
    history = collect_team_history_2627(
        team_id, season_id, limit=limit, venue=venue, before_date=before_date
    )
    return {
        "season": SEASON,
        "season_id": season_id,
        "team_id": team_id,
        "limit": limit,
        "venue": venue,
        "before_date": before_date,
        "source": "Sportmonks",
        "active_stats": ACTIVE_STATS,
        "matches_analyzed": len(history),
        "sample_quality": sample_quality(len(history), limit),
        "metric_quality": build_metric_quality(history, limit),
        "averages": history_averages(history),
        "frequencies": build_frequencies(history),
        "matches": history,
        "integrity": {
            "future_matches_used": False,
            "missing_values_invented": False,
            "hit_rates_from_real_matches_only": True,
            "confidence_score_is_probability": False,
            "note": INTEGRITY_NOTE_2627,
        },
    }


# =========================================================
# PRODUZIDO × CEDIDO
# =========================================================

def cross_metric(produced_history, opponent_history, field):
    produced_values = valid_values(produced_history, "produced", field)
    conceded_values = valid_values(opponent_history, "conceded", field)
    pa, ca = average(produced_values), average(conceded_values)
    cross_average = round((pa + ca) / 2, 2) if pa is not None and ca is not None else None
    return {
        "produced_average": pa,
        "produced_sample": len(produced_values),
        "opponent_conceded_average": ca,
        "opponent_conceded_sample": len(conceded_values),
        "cross_average": cross_average,
        "is_hit_rate": False,
    }


def build_cross(team_history, opponent_history):
    return {
        field: cross_metric(team_history, opponent_history, field)
        for field in ACTIVE_STATS
    }


def cross_metric_quality(team_history, opponent_history, field, requested):
    ps = len(valid_values(team_history, "produced", field))
    cs = len(valid_values(opponent_history, "conceded", field))
    pc = ps / requested if requested > 0 else 0
    cc = cs / requested if requested > 0 else 0
    pv = ps >= MIN_VALID_SAMPLE and pc >= MIN_COVERAGE
    cv = cs >= MIN_VALID_SAMPLE and cc >= MIN_COVERAGE
    valid = pv and cv
    return {
        "valid": valid,
        "team_produced": {
            "valid": pv, "sample": ps, "requested": requested,
            "coverage": round(pc * 100, 1),
        },
        "opponent_conceded": {
            "valid": cv, "sample": cs, "requested": requested,
            "coverage": round(cc * 100, 1),
        },
        "status": "valid" if valid else "insufficient_data",
    }


def build_cross_quality(team_history, opponent_history, requested):
    return {
        field: cross_metric_quality(team_history, opponent_history, field, requested)
        for field in ACTIVE_STATS
    }


def build_market_evidence(home_general, away_general, home_home, away_away, requested):
    result = {}
    for field in ACTIVE_STATS:
        hg = cross_metric_quality(home_general, away_general, field, requested)
        ag = cross_metric_quality(away_general, home_general, field, requested)
        hv = cross_metric_quality(home_home, away_away, field, requested)
        av = cross_metric_quality(away_away, home_home, field, requested)

        general_valid = hg["valid"] and ag["valid"]
        venue_valid = hv["valid"] and av["valid"]
        evidence = "complete" if general_valid and venue_valid else (
            "partial" if general_valid else "insufficient"
        )

        result[field] = {
            "evidence": evidence,
            "eligible": evidence in ("complete", "partial"),
            "general_valid": general_valid,
            "home_away_valid": venue_valid,
            "home_general": hg,
            "away_general": ag,
            "home_at_home": hv,
            "away_at_away": av,
        }
    return result


# =========================================================
# SCORE 0–20
# =========================================================

def confidence_label(score):
    if score >= 17:
        return "FORTE"
    if score >= 14:
        return "BOA"
    if score >= 10:
        return "MODERADA"
    return "FRACA"


def frequency_for_line(history, side, field, line):
    return calculate_hit_rate(history, side, field, line)


def score_line_opportunity(
    team_history, opponent_history, team_venue_history, opponent_venue_history,
    field, line, requested
):
    gp = frequency_for_line(team_history, "produced", field, line)
    gc = frequency_for_line(opponent_history, "conceded", field, line)
    gq = cross_metric_quality(team_history, opponent_history, field, requested)

    if not gq["valid"]:
        return {"scoreable": False, "reason": "general_sample_insufficient"}

    pr, cr = gp.get("rate"), gc.get("rate")
    if pr is None or cr is None:
        return {"scoreable": False, "reason": "frequency_unavailable"}

    vp = frequency_for_line(team_venue_history, "produced", field, line)
    vc = frequency_for_line(opponent_venue_history, "conceded", field, line)
    vq = cross_metric_quality(
        team_venue_history, opponent_venue_history, field, requested
    )

    gcross = cross_metric(team_history, opponent_history, field)
    vcross = cross_metric(team_venue_history, opponent_venue_history, field)

    produced_component = pr / 100 * 4
    conceded_component = cr / 100 * 4

    pc = gq["team_produced"]["coverage"]
    cc = gq["opponent_conceded"]["coverage"]
    avg_coverage = (pc + cc) / 2
    coverage_component = avg_coverage / 100 * 4

    venue_component = 0.0
    vpr, vcr = vp.get("rate"), vc.get("rate")
    if vq["valid"] and vpr is not None and vcr is not None:
        venue_component = ((vpr + vcr) / 2) / 100 * 4

    margin_component = 0.0
    cross_avg = gcross.get("cross_average")
    if cross_avg is not None:
        margin = cross_avg - line
        if margin >= 2:
            margin_component = 4.0
        elif margin >= 1:
            margin_component = 3.0
        elif margin >= 0.5:
            margin_component = 2.0
        elif margin > 0:
            margin_component = 1.0

    raw_score = (
        produced_component + conceded_component + coverage_component
        + venue_component + margin_component
    )
    score = round(min(20.0, max(0.0, raw_score)), 1)

    return {
        "scoreable": True,
        "recommendation_eligible": score >= MIN_RECOMMENDATION_SCORE,
        "field": field,
        "line": line,
        "market": f"{field}_over_{line}",
        "confidence_score": score,
        "confidence_label": confidence_label(score),
        "evidence": {
            "general": {
                "team_produced": gp,
                "opponent_conceded": gc,
                "cross_average": cross_avg,
                "sample_valid": True,
            },
            "home_away": {
                "team_produced": vp,
                "opponent_conceded": vc,
                "cross_average": vcross.get("cross_average"),
                "sample_valid": vq["valid"],
            },
        },
        "score_components": {
            "team_produced_frequency": round(produced_component, 2),
            "opponent_conceded_frequency": round(conceded_component, 2),
            "general_sample_quality": round(coverage_component, 2),
            "home_away": round(venue_component, 2),
            "cross_average_margin": round(margin_component, 2),
            "total_before_cap": round(raw_score, 2),
            "general_produced_rate": pr,
            "general_opponent_conceded_rate": cr,
            "general_average_coverage": round(avg_coverage, 1),
            "venue_component_used": vq["valid"],
        },
        "integrity": {
            "score_is_probability": False,
            "cross_average_is_hit_rate": False,
            "small_venue_sample_promoted": False,
            "real_match_frequencies_only": True,
            "minimum_recommendation_score": MIN_RECOMMENDATION_SCORE,
        },
    }


def build_opportunity_ranking(
    home_team_id, away_team_id, home_general, away_general,
    home_home, away_away, market_evidence, requested
):
    evaluated, recommendations, discarded, blocked = [], [], [], []

    configs = [
        ("home", home_team_id, home_general, away_general, home_home, away_away),
        ("away", away_team_id, away_general, home_general, away_away, home_home),
    ]

    for side, team_id, tg, og, tv, ov in configs:
        for field in ACTIVE_STATS:
            for line in MARKET_LINES.get(field, []):
                result = score_line_opportunity(tg, og, tv, ov, field, line, requested)

                if not result.get("scoreable"):
                    blocked.append({
                        "side": side,
                        "team_id": team_id,
                        "field": field,
                        "line": line,
                        "market": f"{field}_over_{line}",
                        "reason": result.get("reason"),
                    })
                    continue

                result["side"] = side
                result["team_id"] = team_id
                evaluated.append(result)

                if result["recommendation_eligible"]:
                    recommendations.append(result)
                else:
                    low = dict(result)
                    low["discard_reason"] = "confidence_score_below_10"
                    discarded.append(low)

    def ranking_key(item):
        general = item.get("evidence", {}).get("general", {})
        pr = general.get("team_produced", {}).get("rate") or 0
        cr = general.get("opponent_conceded", {}).get("rate") or 0
        return (item.get("confidence_score", 0), (pr + cr) / 2, pr, cr)

    evaluated.sort(key=ranking_key, reverse=True)
    recommendations.sort(key=ranking_key, reverse=True)
    discarded.sort(key=ranking_key, reverse=True)
    top = recommendations[:10]

    return {
        "evaluated_total": len(evaluated) + len(blocked),
        "scored_total": len(evaluated),
        "recommendation_eligible_total": len(recommendations),
        "discarded_low_confidence_total": len(discarded),
        "blocked_total": len(blocked),
        "ranked_total": len(top),
        "minimum_recommendation_score": MIN_RECOMMENDATION_SCORE,
        "top_opportunities": top,
        "all_eligible_opportunities": recommendations,
        "evaluated": evaluated,
        "discarded_low_confidence": discarded,
        "blocked": blocked,
        "integrity": {
            "low_confidence_is_recommendation": False,
            "score_is_probability": False,
            "minimum_score_enforced": True,
            "minimum_score": MIN_RECOMMENDATION_SCORE,
        },
    }


# =========================================================
# MOTOR DUAL 5 + 10
# =========================================================

def _window(base, n):
    return base[:n]


def _window_block(history, requested):
    return {
        "matches_analyzed": len(history),
        "sample_quality": sample_quality(len(history), requested),
        "metric_quality": build_metric_quality(history, requested),
        "averages": history_averages(history),
        "frequencies": build_frequencies(history),
        "matches": history,
    }


def _rate(history, side, field, line):
    return calculate_hit_rate(history, side, field, line).get("rate")


def build_window_agreement(
    team5, opponent5, team10, opponent10, field, line
):
    q5 = cross_metric_quality(team5, opponent5, field, 5)
    q10 = cross_metric_quality(team10, opponent10, field, 10)

    if not q5["valid"] or not q10["valid"]:
        return {
            "available": False,
            "status": "insufficient_data",
            "last5_valid": q5["valid"],
            "last10_valid": q10["valid"],
            "bonus_applied": 0.0,
        }

    p5 = _rate(team5, "produced", field, line)
    c5 = _rate(opponent5, "conceded", field, line)
    p10 = _rate(team10, "produced", field, line)
    c10 = _rate(opponent10, "conceded", field, line)

    if None in (p5, c5, p10, c10):
        return {"available": False, "status": "frequency_unavailable", "bonus_applied": 0.0}

    avg5 = (p5 + c5) / 2
    avg10 = (p10 + c10) / 2
    gap = abs(avg5 - avg10)

    if avg5 >= 70 and avg10 >= 70 and gap <= 20:
        status, bonus = "strong_agreement", 1.5
    elif avg5 >= 60 and avg10 >= 60 and gap <= 25:
        status, bonus = "agreement", 1.0
    elif gap <= 20:
        status, bonus = "stable", 0.5
    else:
        status, bonus = "divergent", 0.0

    return {
        "available": True,
        "status": status,
        "last5_combined_rate": round(avg5, 1),
        "last10_combined_rate": round(avg10, 1),
        "difference_points": round(gap, 1),
        "bonus_applied": bonus,
        "note": "Últimos 5 estão contidos nos últimos 10; a concordância não é uma segunda probabilidade.",
    }


def build_dual_window_ranking(
    home_team_id, away_team_id,
    h5, a5, hh5, aa5,
    h10, a10, hh10, aa10
):
    # Base principal: últimos 5. A janela 10 só ajusta por consistência quando válida.
    base = build_opportunity_ranking(
        home_team_id, away_team_id, h5, a5, hh5, aa5,
        build_market_evidence(h5, a5, hh5, aa5, 5), 5
    )

    adjusted = []
    for item in base["evaluated"]:
        side, field, line = item["side"], item["field"], item["line"]

        if side == "home":
            agreement = build_window_agreement(h5, a5, h10, a10, field, line)
        else:
            agreement = build_window_agreement(a5, h5, a10, h10, field, line)

        new_item = dict(item)
        new_item["last5_confidence_score"] = item["confidence_score"]
        new_item["window_agreement_5x10"] = agreement

        # Bônus pequeno, limitado: não duplica os jogos 5 dentro dos 10.
        bonus = agreement.get("bonus_applied", 0.0)
        new_score = round(min(20.0, item["confidence_score"] + bonus), 1)
        new_item["confidence_score"] = new_score
        new_item["confidence_label"] = confidence_label(new_score)
        new_item["recommendation_eligible"] = new_score >= MIN_RECOMMENDATION_SCORE
        adjusted.append(new_item)

    def key(item):
        return (
            item.get("confidence_score", 0),
            item.get("last5_confidence_score", 0),
        )

    adjusted.sort(key=key, reverse=True)
    recommendations = [x for x in adjusted if x["recommendation_eligible"]]
    discarded = [x for x in adjusted if not x["recommendation_eligible"]]
    for x in discarded:
        x["discard_reason"] = "confidence_score_below_10"

    top = recommendations[:10]

    return {
        "mode": "dual_window_5_10",
        "base_window": 5,
        "consistency_window": 10,
        "evaluated_total": len(adjusted) + len(base["blocked"]),
        "scored_total": len(adjusted),
        "recommendation_eligible_total": len(recommendations),
        "discarded_low_confidence_total": len(discarded),
        "blocked_total": len(base["blocked"]),
        "ranked_total": len(top),
        "minimum_recommendation_score": MIN_RECOMMENDATION_SCORE,
        "top_opportunities": top,
        "all_eligible_opportunities": recommendations,
        "evaluated": adjusted,
        "discarded_low_confidence": discarded,
        "blocked": base["blocked"],
        "integrity": {
            "last5_and_last10_double_counted_as_independent_samples": False,
            "last10_used_only_when_valid": True,
            "last10_missing_is_fabricated": False,
            "score_is_probability": False,
            "minimum_score_enforced": True,
        },
    }


def analyze_prematch_dual_2627(home_team_id, away_team_id, season_id, before_date=None):
    # Quatro coletas-base de até 10; cache reaproveita fixtures repetidas.
    hg10 = collect_team_history_2627(home_team_id, season_id, 10, "all", before_date)
    ag10 = collect_team_history_2627(away_team_id, season_id, 10, "all", before_date)
    hh10 = collect_team_history_2627(home_team_id, season_id, 10, "home", before_date)
    aa10 = collect_team_history_2627(away_team_id, season_id, 10, "away", before_date)

    hg5, ag5, hh5, aa5 = (
        _window(hg10, 5), _window(ag10, 5), _window(hh10, 5), _window(aa10, 5)
    )

    ranking = build_dual_window_ranking(
        home_team_id, away_team_id,
        hg5, ag5, hh5, aa5,
        hg10, ag10, hh10, aa10
    )

    return {
        "season": SEASON,
        "season_id": season_id,
        "before_date": before_date,
        "source": "Sportmonks",
        "mode": "last5_plus_last10",
        "active_stats": ACTIVE_STATS,
        "teams": {"home_team_id": home_team_id, "away_team_id": away_team_id},
        "windows": {
            "last5": {
                "home": {
                    "general": _window_block(hg5, 5),
                    "home_only": _window_block(hh5, 5),
                },
                "away": {
                    "general": _window_block(ag5, 5),
                    "away_only": _window_block(aa5, 5),
                },
                "produced_x_conceded": {
                    "general": {
                        "home": build_cross(hg5, ag5),
                        "away": build_cross(ag5, hg5),
                    },
                    "home_away": {
                        "home": build_cross(hh5, aa5),
                        "away": build_cross(aa5, hh5),
                    },
                },
            },
            "last10": {
                "home": {
                    "general": _window_block(hg10, 10),
                    "home_only": _window_block(hh10, 10),
                },
                "away": {
                    "general": _window_block(ag10, 10),
                    "away_only": _window_block(aa10, 10),
                },
                "produced_x_conceded": {
                    "general": {
                        "home": build_cross(hg10, ag10),
                        "away": build_cross(ag10, hg10),
                    },
                    "home_away": {
                        "home": build_cross(hh10, aa10),
                        "away": build_cross(aa10, hh10),
                    },
                },
            },
        },
        "opportunity_ranking": ranking,
        "recommendation_gate": {
            "minimum_confidence_score": MIN_RECOMMENDATION_SCORE,
            "recommendation_eligible_total": ranking["recommendation_eligible_total"],
            "has_eligible_market": bool(ranking["top_opportunities"]),
        },
        "integrity": {
            "missing_values_invented": False,
            "future_matches_used": False,
            "hit_rates_from_real_matches_only": True,
            "last5_and_last10_are_independent_samples": False,
            "last10_requires_8_of_10_for_validity": True,
            "cross_average_is_hit_rate": False,
            "confidence_score_is_probability": False,
            "note": INTEGRITY_NOTE_2627,
        },
    }


# =========================================================
# PRÉ-JOGO LEGADO COMPATÍVEL
# =========================================================

def analyze_prematch_2627(home_team_id, away_team_id, season_id, limit=5, before_date=None):
    if limit not in WINDOWS:
        raise ValueError("limit deve ser 5 ou 10")

    hg = collect_team_history_2627(home_team_id, season_id, limit, "all", before_date)
    ag = collect_team_history_2627(away_team_id, season_id, limit, "all", before_date)
    hh = collect_team_history_2627(home_team_id, season_id, limit, "home", before_date)
    aa = collect_team_history_2627(away_team_id, season_id, limit, "away", before_date)

    sq = {
        "home_general": sample_quality(len(hg), limit),
        "away_general": sample_quality(len(ag), limit),
        "home_at_home": sample_quality(len(hh), limit),
        "away_at_away": sample_quality(len(aa), limit),
    }
    mq = {
        "home_general": build_metric_quality(hg, limit),
        "away_general": build_metric_quality(ag, limit),
        "home_at_home": build_metric_quality(hh, limit),
        "away_at_away": build_metric_quality(aa, limit),
    }
    evidence = build_market_evidence(hg, ag, hh, aa, limit)
    eligible_stats = [f for f, d in evidence.items() if d.get("eligible") is True]
    blocked_stats = [f for f, d in evidence.items() if d.get("eligible") is not True]

    ranking = build_opportunity_ranking(
        home_team_id, away_team_id, hg, ag, hh, aa, evidence, limit
    )

    return {
        "season": SEASON,
        "season_id": season_id,
        "before_date": before_date,
        "limit": limit,
        "source": "Sportmonks",
        "active_stats": ACTIVE_STATS,
        "teams": {"home_team_id": home_team_id, "away_team_id": away_team_id},
        "sample_quality": sq,
        "metric_quality": mq,
        "market_evidence": evidence,
        "eligible_stats": eligible_stats,
        "blocked_stats": blocked_stats,
        "home": {
            "general": {
                "matches": hg, "averages": history_averages(hg),
                "frequencies": build_frequencies(hg),
            },
            "home_only": {
                "matches": hh, "averages": history_averages(hh),
                "frequencies": build_frequencies(hh),
            },
        },
        "away": {
            "general": {
                "matches": ag, "averages": history_averages(ag),
                "frequencies": build_frequencies(ag),
            },
            "away_only": {
                "matches": aa, "averages": history_averages(aa),
                "frequencies": build_frequencies(aa),
            },
        },
        "produced_x_conceded": {
            "general": {"home": build_cross(hg, ag), "away": build_cross(ag, hg)},
            "home_away": {"home": build_cross(hh, aa), "away": build_cross(aa, hh)},
        },
        "cross_quality": {
            "general": {
                "home": build_cross_quality(hg, ag, limit),
                "away": build_cross_quality(ag, hg, limit),
            },
            "home_away": {
                "home": build_cross_quality(hh, aa, limit),
                "away": build_cross_quality(aa, hh, limit),
            },
        },
        "opportunity_ranking": ranking,
        "recommendation_gate": {
            "eligible_stats": eligible_stats,
            "blocked_stats": blocked_stats,
            "minimum_confidence_score": MIN_RECOMMENDATION_SCORE,
            "recommendation_eligible_total": ranking["recommendation_eligible_total"],
            "has_eligible_market": bool(ranking["top_opportunities"]),
        },
        "integrity": {
            "missing_values_invented": False,
            "future_matches_used": False,
            "hit_rates_from_real_matches_only": True,
            "cross_average_is_hit_rate": False,
            "confidence_score_is_probability": False,
            "low_confidence_markets_recommended": False,
            "minimum_recommendation_score": MIN_RECOMMENDATION_SCORE,
            "note": INTEGRITY_NOTE_2627,
        },
    }


# =========================================================
# COMPATIBILIDADE
# =========================================================

def get_team_history(matches, team_name, limit=5, venue="all"):
    history = []
    for match in matches:
        teams = match.get("teams", {})
        home, away = teams.get("home", {}), teams.get("away", {})
        team_id = None
        if home.get("team") == team_name:
            team_id = home.get("team_id")
        elif away.get("team") == team_name:
            team_id = away.get("team_id")
        if team_id is None:
            continue
        view = team_view(match, team_id)
        if view and (venue == "all" or view.get("venue") == venue):
            history.append(view)

    history.sort(key=lambda item: item.get("date") or "", reverse=True)
    return history[:limit]


def build_team_summary(history, requested=5):
    return {
        "matches_analyzed": len(history),
        "sample_quality": sample_quality(len(history), requested),
        "metric_quality": build_metric_quality(history, requested),
        "averages": history_averages(history),
        "frequencies": build_frequencies(history),
        "matches": history,
    }


# =========================================================
# STATUS
# =========================================================

def collector_2627_status():
    connection = test_sportmonks_connection()
    return {
        "status": "ready" if connection.get("connected") else "source_not_connected",
        "season": SEASON,
        "mode": "2026_27_dual_window",
        "data_source": "Sportmonks",
        "data_source_connected": connection.get("connected", False),
        "authenticated": connection.get("authenticated", False),
        "storage_connected": False,
        "active_analysis_stats": ACTIVE_STATS,
        "analysis_windows": [5, 10],
        "dual_window_engine": {
            "enabled": True,
            "last5_primary": True,
            "last10_consistency_check": True,
            "double_counts_5_and_10_as_independent": False,
        },
        "reserved_future_stats": ["xg", "shots", "shots_on_target", "fouls_committed"],
        "confirmed_sportmonks_type_ids": {
            "34": "corners", "52": "goals", "83": "red_cards", "84": "yellow_cards"
        },
        "confidence_engine": {
            "enabled": True,
            "maximum_score": 20,
            "minimum_recommendation_score": MIN_RECOMMENDATION_SCORE,
            "labels": {
                "17-20": "FORTE", "14-16.9": "BOA",
                "10-13.9": "MODERADA", "0-9.9": "FRACA",
            },
            "weak_markets_are_recommendations": False,
            "score_is_probability": False,
        },
        "ranking_engine": {
            "enabled": True,
            "top_limit": 10,
            "minimum_score": MIN_RECOMMENDATION_SCORE,
            "separates_low_confidence": True,
            "separates_insufficient_data": True,
        },
        "connection_test": connection,
        "integrity": {
            "missing_values_invented": False,
            "zero_is_missing": False,
            "null_is_missing": True,
            "minimum_valid_games": MIN_VALID_SAMPLE,
            "minimum_coverage": MIN_COVERAGE,
            "hit_rates_from_real_matches_only": True,
            "cross_average_is_probability": False,
            "confidence_score_is_probability": False,
            "small_home_away_sample_adds_score": False,
            "last10_requires_8_of_10_for_validity": True,
            "integrity_note": INTEGRITY_NOTE_2627,
        },
        "next_step": "Expor e validar o endpoint dual 5+10 em partida real.",
    }
