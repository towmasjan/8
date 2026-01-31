#!/usr/bin/env python3
"""
BETTING TIPS AGENT
=====================
Agent do analizy meczow pilkarskich i generowania typow bukmacherskich.

Wybrane ligi:
- Premier League
- Bundesliga
- Serie A

Autor: Claude AI
Stawka: 10 zl / typ
"""

import json
import sqlite3
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from enum import Enum
import random
import math

# ============================================
# KONFIGURACJA
# ============================================

class League(Enum):
    PREMIER_LEAGUE = ("premier_league", "Premier League", "ENG", "England")
    BUNDESLIGA = ("bundesliga", "Bundesliga", "GER", "Germany")
    SERIE_A = ("serie_a", "Serie A", "ITA", "Italy")

    def __init__(self, id: str, name: str, flag: str, country: str):
        self.id = id
        self.league_name = name
        self.flag = flag
        self.country = country


class BetType(Enum):
    HOME_WIN = ("1", "Wygrana gospodarzy")
    DRAW = ("X", "Remis")
    AWAY_WIN = ("2", "Wygrana gosci")
    HOME_OR_DRAW = ("1X", "Gospodarze lub remis")
    AWAY_OR_DRAW = ("X2", "Goscie lub remis")
    BTTS_YES = ("BTTS", "Obie strzela - TAK")
    BTTS_NO = ("BTTS_NO", "Obie strzela - NIE")
    OVER_25 = ("O2.5", "Powyzej 2.5 gola")
    OVER_35 = ("O3.5", "Powyzej 3.5 gola")
    UNDER_25 = ("U2.5", "Ponizej 2.5 gola")

    def __init__(self, code: str, description: str):
        self.code = code
        self.description = description


CONFIG = {
    "unit_size": 10,           # PLN na typ
    "max_daily_tips": 3,       # Max typow dziennie
    "min_confidence": 0.65,    # Min 65% pewnosci
    "min_value": 0.05,         # Min 5% value
    "min_odds": 1.40,
    "max_odds": 3.50,
}


# ============================================
# STRUKTURY DANYCH
# ============================================

@dataclass
class TeamStats:
    """Statystyki druzyny"""
    name: str
    position: int = 0
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0
    form: List[str] = field(default_factory=list)  # ['W','W','D','L','W']
    home_form: List[str] = field(default_factory=list)
    away_form: List[str] = field(default_factory=list)
    injuries: List[str] = field(default_factory=list)

    @property
    def form_score(self) -> float:
        """Wynik formy 0-1 (ostatnie 5 meczow)"""
        if not self.form:
            return 0.5
        points = {'W': 3, 'D': 1, 'L': 0}
        recent = self.form[-5:]
        return sum(points.get(r, 0) for r in recent) / 15

    @property
    def goals_per_game(self) -> float:
        return self.goals_for / max(self.played, 1)

    @property
    def conceded_per_game(self) -> float:
        return self.goals_against / max(self.played, 1)

    @property
    def clean_sheet_rate(self) -> float:
        """Procent meczow bez straty gola"""
        if not self.played:
            return 0
        # Przyblizenie na podstawie strzelonych/straconych
        return max(0, 1 - (self.goals_against / self.played / 2))


@dataclass
class Match:
    """Mecz do analizy"""
    id: str
    league: League
    home_team: TeamStats
    away_team: TeamStats
    kickoff: datetime
    venue: str = ""

    # Kursy
    odds_home: float = 0.0
    odds_draw: float = 0.0
    odds_away: float = 0.0
    odds_btts_yes: float = 0.0
    odds_over_25: float = 0.0

    # H2H
    h2h_home_wins: int = 0
    h2h_draws: int = 0
    h2h_away_wins: int = 0
    h2h_total_goals: float = 0.0

    # Wynik (po meczu)
    result_home: Optional[int] = None
    result_away: Optional[int] = None

    def __str__(self):
        return f"{self.home_team.name} vs {self.away_team.name}"


@dataclass
class BettingTip:
    """Wygenerowany typ"""
    match: Match
    bet_type: BetType
    odds: float
    confidence: float  # 0-1
    value: float       # % przewagi nad bukmacherem
    stake: float       # PLN
    reasoning: List[str]
    timestamp: datetime = field(default_factory=datetime.now)

    # Wynik (po rozliczeniu)
    result: Optional[str] = None  # 'WIN', 'LOSS', 'VOID'
    profit: Optional[float] = None

    @property
    def potential_return(self) -> float:
        return self.stake * self.odds

    @property
    def confidence_stars(self) -> str:
        stars = int(self.confidence * 5)
        return "*" * max(1, min(5, stars))

    @property
    def value_indicator(self) -> str:
        if self.value >= 0.15:
            return "[WYSOKI]"
        elif self.value >= 0.08:
            return "[SREDNI]"
        return "[NISKI]"


# ============================================
# BAZA DANYCH
# ============================================

class Database:
    """Baza SQLite do sledzenia historii typow"""

    def __init__(self, path: str = "betting_history.db"):
        self.path = path
        self.conn = sqlite3.connect(path)
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()

        # Tabela typow
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                league TEXT NOT NULL,
                match TEXT NOT NULL,
                bet_type TEXT NOT NULL,
                odds REAL NOT NULL,
                stake REAL NOT NULL,
                confidence REAL NOT NULL,
                value REAL NOT NULL,
                reasoning TEXT,
                result TEXT,
                profit REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Tabela statystyk
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                tips_count INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_stake REAL DEFAULT 0,
                total_return REAL DEFAULT 0,
                profit REAL DEFAULT 0,
                roi REAL DEFAULT 0
            )
        ''')

        self.conn.commit()

    def save_tip(self, tip: BettingTip) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO tips (date, league, match, bet_type, odds, stake, confidence, value, reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            tip.timestamp.strftime("%Y-%m-%d"),
            tip.match.league.league_name,
            str(tip.match),
            tip.bet_type.code,
            tip.odds,
            tip.stake,
            tip.confidence,
            tip.value,
            json.dumps(tip.reasoning, ensure_ascii=False)
        ))
        self.conn.commit()
        return cursor.lastrowid

    def update_result(self, tip_id: int, result: str, profit: float):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE tips SET result = ?, profit = ? WHERE id = ?
        ''', (result, profit, tip_id))
        self.conn.commit()

    def get_stats(self, days: int = 30) -> Dict:
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'LOSS' THEN 1 ELSE 0 END) as losses,
                SUM(stake) as total_stake,
                SUM(COALESCE(profit, 0)) as total_profit
            FROM tips
            WHERE date >= ? AND result IS NOT NULL
        ''', (since,))

        row = cursor.fetchone()
        if not row or not row[0]:
            return {
                "total": 0,
                "wins": 0,
                "losses": 0,
                "roi": 0,
                "total_stake": 0,
                "total_profit": 0,
                "success_rate": 0
            }

        total, wins, losses, stake, profit = row
        wins = wins or 0
        losses = losses or 0
        stake = stake or 0
        profit = profit or 0

        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "total_stake": stake,
            "total_profit": profit,
            "roi": (profit / stake * 100) if stake else 0,
            "success_rate": (wins / total * 100) if total else 0
        }

    def get_recent_tips(self, limit: int = 10) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT date, league, match, bet_type, odds, stake, confidence, result, profit
            FROM tips
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))

        columns = ['date', 'league', 'match', 'bet_type', 'odds', 'stake', 'confidence', 'result', 'profit']
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self):
        self.conn.close()


# ============================================
# ANALIZA MECZOW
# ============================================

class MatchAnalyzer:
    """Analizator meczow - oblicza prawdopodobienstwa i value"""

    # Wagi dla roznych czynnikow
    WEIGHTS = {
        "form": 0.25,
        "home_advantage": 0.15,
        "position": 0.15,
        "h2h": 0.15,
        "goals": 0.15,
        "injuries": 0.10,
        "motivation": 0.05,
    }

    def analyze(self, match: Match) -> Dict[BetType, Tuple[float, float, List[str]]]:
        """
        Analizuje mecz i zwraca prawdopodobienstwa dla kazdego typu zakladu.
        Returns: {BetType: (probability, value, [reasons])}
        """
        results = {}

        # 1. Analiza 1X2
        home_prob, draw_prob, away_prob, reasons_1x2 = self._analyze_1x2(match)

        # Oblicz value dla kazdego wyniku
        if match.odds_home > 0:
            implied_home = 1 / match.odds_home
            value_home = home_prob - implied_home
            results[BetType.HOME_WIN] = (home_prob, value_home, reasons_1x2["home"])

        if match.odds_draw > 0:
            implied_draw = 1 / match.odds_draw
            value_draw = draw_prob - implied_draw
            results[BetType.DRAW] = (draw_prob, value_draw, reasons_1x2["draw"])

        if match.odds_away > 0:
            implied_away = 1 / match.odds_away
            value_away = away_prob - implied_away
            results[BetType.AWAY_WIN] = (away_prob, value_away, reasons_1x2["away"])

        # Double chance
        results[BetType.HOME_OR_DRAW] = (
            home_prob + draw_prob,
            0,  # Value obliczony osobno
            reasons_1x2["home"] + ["Zabezpieczenie remisem"]
        )
        results[BetType.AWAY_OR_DRAW] = (
            away_prob + draw_prob,
            0,
            reasons_1x2["away"] + ["Zabezpieczenie remisem"]
        )

        # 2. Analiza BTTS
        btts_prob, btts_reasons = self._analyze_btts(match)
        if match.odds_btts_yes > 0:
            implied_btts = 1 / match.odds_btts_yes
            value_btts = btts_prob - implied_btts
            results[BetType.BTTS_YES] = (btts_prob, value_btts, btts_reasons)
        results[BetType.BTTS_NO] = (1 - btts_prob, 0, ["Slabe ataki lub mocne obrony"])

        # 3. Analiza Over/Under
        over_25_prob, over_reasons = self._analyze_over_under(match, 2.5)
        if match.odds_over_25 > 0:
            implied_over = 1 / match.odds_over_25
            value_over = over_25_prob - implied_over
            results[BetType.OVER_25] = (over_25_prob, value_over, over_reasons)
        results[BetType.UNDER_25] = (1 - over_25_prob, 0, ["Defensywne nastawienie druzyn"])

        over_35_prob, _ = self._analyze_over_under(match, 3.5)
        results[BetType.OVER_35] = (over_35_prob, 0, ["Bardzo ofensywne druzyny"])

        return results

    def _analyze_1x2(self, match: Match) -> Tuple[float, float, float, Dict]:
        """Analiza prawdopodobienstw 1X2"""
        home = match.home_team
        away = match.away_team

        reasons = {"home": [], "draw": [], "away": []}

        # Bazowe prawdopodobienstwa na podstawie kursow
        if match.odds_home and match.odds_draw and match.odds_away:
            total = 1/match.odds_home + 1/match.odds_draw + 1/match.odds_away
            base_home = (1/match.odds_home) / total
            base_draw = (1/match.odds_draw) / total
            base_away = (1/match.odds_away) / total
        else:
            base_home, base_draw, base_away = 0.45, 0.25, 0.30

        # Modyfikatory
        home_mod = 0
        away_mod = 0

        # 1. Forma (25%)
        form_diff = home.form_score - away.form_score
        if form_diff > 0.2:
            home_mod += 0.08
            reasons["home"].append(f"Lepsza forma: {home.form_score:.0%} vs {away.form_score:.0%}")
        elif form_diff < -0.2:
            away_mod += 0.08
            reasons["away"].append(f"Lepsza forma gosci: {away.form_score:.0%}")

        # 2. Przewaga wlasnego boiska (15%)
        home_mod += 0.05
        reasons["home"].append("Przewaga wlasnego boiska")

        # 3. Pozycja w tabeli (15%)
        pos_diff = away.position - home.position
        if pos_diff > 5:
            home_mod += 0.06
            reasons["home"].append(f"Wyzsza pozycja w tabeli ({home.position} vs {away.position})")
        elif pos_diff < -5:
            away_mod += 0.06
            reasons["away"].append(f"Wyzsza pozycja gosci ({away.position})")

        # 4. H2H (15%)
        total_h2h = match.h2h_home_wins + match.h2h_draws + match.h2h_away_wins
        if total_h2h > 0:
            h2h_home_rate = match.h2h_home_wins / total_h2h
            h2h_away_rate = match.h2h_away_wins / total_h2h
            if h2h_home_rate > 0.5:
                home_mod += 0.04
                reasons["home"].append(f"Korzystne H2H: {match.h2h_home_wins}W-{match.h2h_draws}D-{match.h2h_away_wins}L")
            elif h2h_away_rate > 0.5:
                away_mod += 0.04
                reasons["away"].append(f"Korzystne H2H dla gosci")

        # 5. Bilans bramkowy (15%)
        home_goal_diff = home.goals_per_game - home.conceded_per_game
        away_goal_diff = away.goals_per_game - away.conceded_per_game
        if home_goal_diff > away_goal_diff + 0.5:
            home_mod += 0.05
            reasons["home"].append(f"Lepszy bilans bramkowy: {home_goal_diff:+.1f} vs {away_goal_diff:+.1f}")
        elif away_goal_diff > home_goal_diff + 0.5:
            away_mod += 0.05
            reasons["away"].append(f"Lepszy bilans bramkowy gosci")

        # 6. Kontuzje (10%)
        if len(home.injuries) > 2:
            home_mod -= 0.04
            reasons["away"].append(f"Kontuzje gospodarzy: {len(home.injuries)} graczy")
        if len(away.injuries) > 2:
            away_mod -= 0.04
            reasons["home"].append(f"Kontuzje gosci: {len(away.injuries)} graczy")

        # Oblicz finalne prawdopodobienstwa
        home_prob = min(0.85, max(0.10, base_home + home_mod - away_mod * 0.5))
        away_prob = min(0.85, max(0.10, base_away + away_mod - home_mod * 0.5))
        draw_prob = 1 - home_prob - away_prob
        draw_prob = min(0.40, max(0.15, draw_prob))

        # Normalizacja
        total = home_prob + draw_prob + away_prob
        home_prob /= total
        draw_prob /= total
        away_prob /= total

        # Powody dla remisu
        if abs(home.form_score - away.form_score) < 0.1:
            reasons["draw"].append("Wyrownane formy druzyn")
        if abs(home.position - away.position) <= 3:
            reasons["draw"].append("Podobne pozycje w tabeli")

        return home_prob, draw_prob, away_prob, reasons

    def _analyze_btts(self, match: Match) -> Tuple[float, List[str]]:
        """Analiza prawdopodobienstwa BTTS"""
        home = match.home_team
        away = match.away_team
        reasons = []

        # Bazowe prawdopodobienstwo
        home_scores = home.goals_per_game
        away_scores = away.goals_per_game
        home_concedes = home.conceded_per_game
        away_concedes = away.conceded_per_game

        # Prawdopodobienstwo ze gospodarz strzeli
        prob_home_scores = min(0.95, (home_scores + away_concedes) / 3)

        # Prawdopodobienstwo ze gosc strzeli
        prob_away_scores = min(0.95, (away_scores + home_concedes) / 3)

        # BTTS = oba strzela
        btts_prob = prob_home_scores * prob_away_scores

        if home_scores > 1.5:
            reasons.append(f"{home.name} strzela srednio {home_scores:.1f} gola/mecz")
        if away_scores > 1.3:
            reasons.append(f"{away.name} strzela srednio {away_scores:.1f} gola/mecz")
        if home_concedes > 1.2:
            reasons.append(f"{home.name} traci srednio {home_concedes:.1f} gola/mecz")
        if away_concedes > 1.2:
            reasons.append(f"{away.name} traci srednio {away_concedes:.1f} gola/mecz")

        return btts_prob, reasons

    def _analyze_over_under(self, match: Match, line: float) -> Tuple[float, List[str]]:
        """Analiza Over/Under"""
        home = match.home_team
        away = match.away_team
        reasons = []

        # Oczekiwana liczba goli
        expected_goals = (
            home.goals_per_game +
            away.goals_per_game +
            home.conceded_per_game * 0.3 +
            away.conceded_per_game * 0.3
        ) / 2

        # H2H gole
        if match.h2h_total_goals > 0:
            expected_goals = (expected_goals + match.h2h_total_goals) / 2
            if match.h2h_total_goals > line:
                reasons.append(f"Srednio {match.h2h_total_goals:.1f} goli w H2H")

        # Prawdopodobienstwo over (uproszczone Poisson)
        if expected_goals > line:
            over_prob = 0.5 + (expected_goals - line) * 0.15
        else:
            over_prob = 0.5 - (line - expected_goals) * 0.15

        over_prob = min(0.85, max(0.15, over_prob))

        if expected_goals > 2.5:
            reasons.append(f"Wysoka srednia goli: {expected_goals:.1f}")
        if home.goals_per_game + away.goals_per_game > 3:
            reasons.append(f"Ofensywne druzyny: {home.goals_per_game:.1f} + {away.goals_per_game:.1f} goli/mecz")

        return over_prob, reasons


# ============================================
# GENERATOR TYPOW
# ============================================

class TipGenerator:
    """Generuje najlepsze typy na podstawie analizy"""

    def __init__(self, analyzer: MatchAnalyzer, config: Dict = None):
        self.analyzer = analyzer
        self.config = config or CONFIG

    def generate_tips(self, matches: List[Match], max_tips: int = 3) -> List[BettingTip]:
        """Generuje najlepsze typy z listy meczow"""
        all_tips = []

        for match in matches:
            analysis = self.analyzer.analyze(match)

            for bet_type, (prob, value, reasons) in analysis.items():
                # Filtruj wedlug kryteriow
                if prob < self.config["min_confidence"]:
                    continue
                if value < self.config["min_value"]:
                    continue

                odds = self._get_odds_for_bet(match, bet_type)
                if not odds or odds < self.config["min_odds"] or odds > self.config["max_odds"]:
                    continue

                tip = BettingTip(
                    match=match,
                    bet_type=bet_type,
                    odds=odds,
                    confidence=prob,
                    value=value,
                    stake=self.config["unit_size"],
                    reasoning=reasons
                )
                all_tips.append(tip)

        # Sortuj po value * confidence (expected value)
        all_tips.sort(key=lambda t: t.value * t.confidence, reverse=True)

        # Zwroc najlepsze typy (max 1 na mecz)
        selected = []
        seen_matches = set()

        for tip in all_tips:
            if len(selected) >= max_tips:
                break
            if tip.match.id in seen_matches:
                continue

            selected.append(tip)
            seen_matches.add(tip.match.id)

        return selected

    def _get_odds_for_bet(self, match: Match, bet_type: BetType) -> Optional[float]:
        """Pobiera kurs dla danego typu zakladu"""
        odds_map = {
            BetType.HOME_WIN: match.odds_home,
            BetType.DRAW: match.odds_draw,
            BetType.AWAY_WIN: match.odds_away,
            BetType.BTTS_YES: match.odds_btts_yes,
            BetType.OVER_25: match.odds_over_25,
            BetType.HOME_OR_DRAW: self._calculate_double_chance_odds(match.odds_home, match.odds_draw),
            BetType.AWAY_OR_DRAW: self._calculate_double_chance_odds(match.odds_away, match.odds_draw),
        }
        return odds_map.get(bet_type)

    def _calculate_double_chance_odds(self, odds1: float, odds2: float) -> Optional[float]:
        """Oblicza kurs double chance na podstawie kursow skladowych"""
        if not odds1 or not odds2:
            return None
        prob1 = 1 / odds1
        prob2 = 1 / odds2
        combined_prob = prob1 + prob2
        # Dodaj marze bukmachera (~5%)
        return 1 / (combined_prob * 1.05)


# ============================================
# POBIERANIE DANYCH (SYMULACJA)
# ============================================

class DataFetcher:
    """Pobiera dane o meczach - symulacja z przykladowymi danymi"""

    # Przykladowe dane druzyn dla kazdej ligi
    TEAMS_DATA = {
        League.PREMIER_LEAGUE: [
            ("Arsenal", 1, 20, 14, 4, 2, 45, 18),
            ("Liverpool", 2, 20, 13, 5, 2, 42, 16),
            ("Manchester City", 3, 20, 12, 5, 3, 40, 20),
            ("Chelsea", 4, 20, 11, 5, 4, 38, 22),
            ("Tottenham", 5, 20, 10, 4, 6, 35, 25),
            ("Manchester United", 6, 20, 9, 5, 6, 28, 24),
            ("Newcastle", 7, 20, 8, 6, 6, 30, 26),
            ("Brighton", 8, 20, 8, 5, 7, 32, 30),
            ("Aston Villa", 9, 20, 7, 6, 7, 28, 28),
            ("West Ham", 10, 20, 6, 6, 8, 25, 30),
            ("Brentford", 11, 20, 5, 8, 7, 26, 29),
            ("Crystal Palace", 12, 20, 5, 7, 8, 22, 28),
            ("Fulham", 13, 20, 5, 6, 9, 24, 32),
            ("Bournemouth", 14, 20, 4, 7, 9, 20, 33),
            ("Wolves", 15, 20, 4, 6, 10, 18, 32),
            ("Everton", 16, 20, 4, 5, 11, 16, 30),
            ("Nottingham Forest", 17, 20, 3, 6, 11, 15, 34),
            ("Luton", 18, 20, 3, 4, 13, 18, 40),
            ("Burnley", 19, 20, 2, 5, 13, 14, 42),
            ("Sheffield United", 20, 20, 1, 4, 15, 12, 48),
        ],
        League.BUNDESLIGA: [
            ("Bayern Munich", 1, 18, 13, 3, 2, 48, 18),
            ("Bayer Leverkusen", 2, 18, 13, 4, 1, 42, 14),
            ("Borussia Dortmund", 3, 18, 11, 4, 3, 38, 22),
            ("RB Leipzig", 4, 18, 10, 4, 4, 35, 20),
            ("Stuttgart", 5, 18, 10, 3, 5, 36, 24),
            ("Eintracht Frankfurt", 6, 18, 8, 5, 5, 30, 26),
            ("Freiburg", 7, 18, 7, 6, 5, 25, 24),
            ("Hoffenheim", 8, 18, 7, 5, 6, 28, 28),
            ("Werder Bremen", 9, 18, 6, 5, 7, 26, 30),
            ("Wolfsburg", 10, 18, 6, 4, 8, 24, 28),
            ("Union Berlin", 11, 18, 5, 5, 8, 20, 28),
            ("Augsburg", 12, 18, 5, 4, 9, 22, 34),
            ("Monchengladbach", 13, 18, 4, 5, 9, 22, 32),
            ("Bochum", 14, 18, 3, 6, 9, 18, 32),
            ("Mainz", 15, 18, 3, 5, 10, 16, 30),
            ("Koln", 16, 18, 2, 5, 11, 14, 36),
            ("Heidenheim", 17, 18, 2, 4, 12, 15, 38),
            ("Darmstadt", 18, 18, 1, 3, 14, 12, 44),
        ],
        League.SERIE_A: [
            ("Inter Milan", 1, 19, 15, 3, 1, 48, 12),
            ("Juventus", 2, 19, 12, 6, 1, 35, 14),
            ("AC Milan", 3, 19, 11, 4, 4, 36, 22),
            ("Napoli", 4, 19, 10, 5, 4, 38, 20),
            ("Atalanta", 5, 19, 10, 4, 5, 40, 26),
            ("Roma", 6, 19, 9, 5, 5, 32, 24),
            ("Lazio", 7, 19, 9, 4, 6, 30, 24),
            ("Bologna", 8, 19, 8, 6, 5, 28, 22),
            ("Fiorentina", 9, 19, 8, 5, 6, 30, 26),
            ("Torino", 10, 19, 6, 7, 6, 24, 24),
            ("Monza", 11, 19, 5, 7, 7, 22, 28),
            ("Genoa", 12, 19, 5, 6, 8, 22, 30),
            ("Lecce", 13, 19, 4, 7, 8, 18, 28),
            ("Sassuolo", 14, 19, 4, 5, 10, 20, 36),
            ("Empoli", 15, 19, 3, 7, 9, 16, 30),
            ("Udinese", 16, 19, 3, 6, 10, 18, 34),
            ("Cagliari", 17, 19, 3, 5, 11, 18, 38),
            ("Frosinone", 18, 19, 2, 5, 12, 16, 42),
            ("Verona", 19, 19, 2, 4, 13, 15, 40),
            ("Salernitana", 20, 19, 1, 3, 15, 12, 48),
        ],
    }

    def __init__(self):
        self.teams_cache: Dict[League, Dict[str, TeamStats]] = {}
        self._init_teams()

    def _init_teams(self):
        """Inicjalizuje cache druzyn"""
        for league, teams_data in self.TEAMS_DATA.items():
            self.teams_cache[league] = {}
            for data in teams_data:
                name, pos, played, wins, draws, losses, gf, ga = data
                team = TeamStats(
                    name=name,
                    position=pos,
                    played=played,
                    wins=wins,
                    draws=draws,
                    losses=losses,
                    goals_for=gf,
                    goals_against=ga,
                    points=wins * 3 + draws,
                    form=self._generate_form(wins, draws, losses),
                )
                self.teams_cache[league][name] = team

    def _generate_form(self, wins: int, draws: int, losses: int) -> List[str]:
        """Generuje forme na podstawie ogolnych statystyk"""
        total = wins + draws + losses
        if total == 0:
            return []

        form = []
        for _ in range(5):
            r = random.random()
            if r < wins / total:
                form.append('W')
            elif r < (wins + draws) / total:
                form.append('D')
            else:
                form.append('L')
        return form

    def get_team(self, league: League, name: str) -> Optional[TeamStats]:
        """Pobiera statystyki druzyny"""
        return self.teams_cache.get(league, {}).get(name)

    def get_upcoming_matches(self, league: League, days: int = 7) -> List[Match]:
        """Pobiera nadchodzace mecze (symulacja)"""
        teams = list(self.teams_cache.get(league, {}).values())
        if len(teams) < 2:
            return []

        matches = []
        random.shuffle(teams)

        # Generuj pare meczow
        for i in range(0, min(len(teams) - 1, 6), 2):
            home_team = teams[i]
            away_team = teams[i + 1]

            # Generuj kursy na podstawie pozycji
            pos_diff = away_team.position - home_team.position
            base_home_prob = 0.45 + pos_diff * 0.02
            base_home_prob = max(0.25, min(0.70, base_home_prob))

            # Dodaj marze bukmachera
            margin = 1.08
            odds_home = margin / base_home_prob
            odds_away = margin / (1 - base_home_prob - 0.25)
            odds_draw = margin / 0.25

            match = Match(
                id=f"{league.id}_{i}",
                league=league,
                home_team=home_team,
                away_team=away_team,
                kickoff=datetime.now() + timedelta(days=random.randint(1, days)),
                venue=f"{home_team.name} Stadium",
                odds_home=round(odds_home, 2),
                odds_draw=round(odds_draw, 2),
                odds_away=round(odds_away, 2),
                odds_btts_yes=round(random.uniform(1.6, 2.0), 2),
                odds_over_25=round(random.uniform(1.7, 2.1), 2),
                h2h_home_wins=random.randint(1, 4),
                h2h_draws=random.randint(0, 3),
                h2h_away_wins=random.randint(0, 3),
                h2h_total_goals=round(random.uniform(2.0, 3.5), 1),
            )
            matches.append(match)

        return matches


# ============================================
# FORMATOWANIE WYJSCIA
# ============================================

class OutputFormatter:
    """Formatuje wyjscie typow"""

    @staticmethod
    def format_tip(tip: BettingTip, index: int = 1) -> str:
        """Formatuje pojedynczy typ"""
        lines = [
            "=" * 60,
            f"  TYP #{index}: {tip.match.league.flag} {tip.match.league.league_name}",
            "=" * 60,
            f"",
            f"  {tip.match}",
            f"  Data: {tip.match.kickoff.strftime('%Y-%m-%d %H:%M')}",
            f"",
            f"  ZAKLAD: {tip.bet_type.code} - {tip.bet_type.description}",
            f"  Kurs: {tip.odds:.2f}",
            f"  Stawka: {tip.stake:.0f} PLN",
            f"  Potencjalna wygrana: {tip.potential_return:.2f} PLN",
            f"",
            f"  Pewnosc: {tip.confidence:.0%} {tip.confidence_stars}",
            f"  Value: {tip.value:.1%} {tip.value_indicator}",
            f"",
            f"  UZASADNIENIE:",
        ]

        for reason in tip.reasoning:
            lines.append(f"    - {reason}")

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def format_daily_summary(tips: List[BettingTip], stats: Dict) -> str:
        """Formatuje podsumowanie dnia"""
        lines = [
            "",
            "#" * 60,
            "  PODSUMOWANIE DNIA",
            "#" * 60,
            "",
            f"  Liczba typow: {len(tips)}",
            f"  Laczna stawka: {sum(t.stake for t in tips):.0f} PLN",
            f"  Potencjalny zwrot: {sum(t.potential_return for t in tips):.2f} PLN",
            "",
        ]

        if stats["total"] > 0:
            lines.extend([
                "  STATYSTYKI (ostatnie 30 dni):",
                f"    Skutecznosc: {stats['success_rate']:.1f}%",
                f"    ROI: {stats['roi']:+.1f}%",
                f"    Profit: {stats['total_profit']:+.2f} PLN",
                "",
            ])

        lines.append("#" * 60)
        return "\n".join(lines)

    @staticmethod
    def format_header() -> str:
        """Formatuje naglowek"""
        return """
############################################################
      BETTING TIPS AGENT - Typy Bukmacherskie
############################################################
  Ligi: Premier League | Bundesliga | Serie A
  Stawka bazowa: 10 PLN / typ
  Max typow dziennie: 3
############################################################
"""


# ============================================
# GLOWNA KLASA AGENTA
# ============================================

class BettingAgent:
    """Glowny agent do generowania typow"""

    def __init__(self, db_path: str = "betting_history.db"):
        self.db = Database(db_path)
        self.fetcher = DataFetcher()
        self.analyzer = MatchAnalyzer()
        self.generator = TipGenerator(self.analyzer)
        self.formatter = OutputFormatter()

    def run(self, leagues: List[League] = None) -> List[BettingTip]:
        """Uruchamia agenta i generuje typy"""
        if leagues is None:
            leagues = [League.PREMIER_LEAGUE, League.BUNDESLIGA, League.SERIE_A]

        print(self.formatter.format_header())

        # Pobierz mecze ze wszystkich lig
        all_matches = []
        for league in leagues:
            matches = self.fetcher.get_upcoming_matches(league)
            all_matches.extend(matches)
            print(f"  Pobrano {len(matches)} meczow z {league.league_name}")

        print()

        # Generuj typy
        tips = self.generator.generate_tips(
            all_matches,
            max_tips=CONFIG["max_daily_tips"]
        )

        # Wyswietl typy
        for i, tip in enumerate(tips, 1):
            print(self.formatter.format_tip(tip, i))
            # Zapisz do bazy
            self.db.save_tip(tip)

        # Podsumowanie
        stats = self.db.get_stats()
        print(self.formatter.format_daily_summary(tips, stats))

        return tips

    def show_stats(self, days: int = 30):
        """Wyswietla statystyki"""
        stats = self.db.get_stats(days)

        print(f"""
############################################################
  STATYSTYKI ({days} dni)
############################################################
  Liczba typow: {stats['total']}
  Wygrane: {stats['wins']} ({stats['success_rate']:.1f}%)
  Przegrane: {stats['losses']}

  Stawki: {stats['total_stake']:.0f} PLN
  Profit: {stats['total_profit']:+.2f} PLN
  ROI: {stats['roi']:+.1f}%
############################################################
""")

    def show_recent_tips(self, limit: int = 10):
        """Wyswietla ostatnie typy"""
        tips = self.db.get_recent_tips(limit)

        print(f"\n{'='*60}")
        print(f"  OSTATNIE {limit} TYPOW")
        print(f"{'='*60}\n")

        for tip in tips:
            result_str = tip['result'] or 'PENDING'
            profit_str = f"{tip['profit']:+.2f} PLN" if tip['profit'] is not None else "-"

            print(f"  {tip['date']} | {tip['league']}")
            print(f"  {tip['match']}")
            print(f"  {tip['bet_type']} @ {tip['odds']:.2f} | {result_str} | {profit_str}")
            print()

    def close(self):
        """Zamyka polaczenia"""
        self.db.close()


# ============================================
# CLI INTERFACE
# ============================================

def main():
    """Glowna funkcja CLI"""
    import sys

    agent = BettingAgent()

    try:
        if len(sys.argv) > 1:
            command = sys.argv[1].lower()

            if command == "stats":
                days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
                agent.show_stats(days)

            elif command == "history":
                limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
                agent.show_recent_tips(limit)

            elif command == "tips":
                # Filtruj po ligach
                leagues = []
                for arg in sys.argv[2:]:
                    arg_lower = arg.lower()
                    if "premier" in arg_lower or "epl" in arg_lower:
                        leagues.append(League.PREMIER_LEAGUE)
                    elif "bund" in arg_lower or "ger" in arg_lower:
                        leagues.append(League.BUNDESLIGA)
                    elif "serie" in arg_lower or "ita" in arg_lower:
                        leagues.append(League.SERIE_A)

                agent.run(leagues if leagues else None)

            elif command == "help":
                print("""
Betting Tips Agent - Uzycie:
  python betting_tips_agent.py          - Generuj dzisiejsze typy
  python betting_tips_agent.py tips     - Generuj typy (wszystkie ligi)
  python betting_tips_agent.py tips epl - Generuj typy (tylko Premier League)
  python betting_tips_agent.py stats    - Pokaz statystyki (30 dni)
  python betting_tips_agent.py stats 7  - Pokaz statystyki (7 dni)
  python betting_tips_agent.py history  - Pokaz ostatnie typy
  python betting_tips_agent.py help     - Pokaz pomoc
                """)

            else:
                print(f"Nieznana komenda: {command}")
                print("Uzyj 'python betting_tips_agent.py help' dla pomocy")

        else:
            # Domyslnie generuj typy
            agent.run()

    finally:
        agent.close()


if __name__ == "__main__":
    main()
