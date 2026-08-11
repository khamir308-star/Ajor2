"""Hokm (حکم) 4-player card game engine — full rewrite with official rules.

Official Hokm rules (pagat.com):
- 4 players in 2 fixed partnerships (seats 0&2 vs 1&3)
- Standard 52-card deck, ranking: A K Q J 10 9 8 7 6 5 4 3 2
- Hâkem: first player dealt an Ace; leads first trick, declares trump
- Deal: 5-4-4 (pause after 5 for trump declaration)
- Play: must follow suit; trump wins over non-trump
- Scoring: 7 tricks = 1 point; kot (7-0 Hâkem team) = 2; kot (7-0 opponents) = 3
- First to 7 points wins the game
"""

from __future__ import annotations

import random
import time
from typing import Any

SUITS = ["s", "h", "d", "c"]
SUIT_ORDER = {suit: index for index, suit in enumerate(SUITS)}
SUIT_NAMES = {"s": "پیک ♠", "h": "دل ♥", "d": "خشت ♦", "c": "گشنیز ♣"}
SUIT_SYMBOLS = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
RANKS = list(range(14, 1, -1))  # 14=Ace ... 2
RANK_LABELS = {14: "A", 13: "K", 12: "Q", 11: "J"}
RANK_PERSIAN = {14: "آس", 13: "شاه", 12: "بی‌بی", 11: "سرباز"}
WIN_SCORE = 7  # امتیاز نهایی
WIN_TRICKS = 7  # دست‌های لازم برای بردن یک دست

TEAM_OF = [0, 1, 0, 1]  # seat -> team


def card_key(card: dict[str, Any]) -> str:
    return f"{card['s']}:{card['v']}"


def rank_label(v: int) -> str:
    return RANK_LABELS.get(v, str(v))


def rank_persian(v: int) -> str:
    return RANK_PERSIAN.get(v, str(v))


def card_display(card: dict[str, Any]) -> str:
    return f"{rank_persian(card['v'])} {SUIT_NAMES[card['s']]}"


def sort_hand(hand: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """گروه‌بندی خال‌ها و چیدن هر خال از بزرگ به کوچک.

    ترتیب ثابت خال‌ها فقط برای نمایش است؛ قدرت کارت همچنان در
    ``trick_value`` تعیین می‌شود.
    """
    return sorted(hand, key=lambda card: (SUIT_ORDER.get(card["s"], 99), -int(card["v"])))


def make_deck() -> list[dict[str, Any]]:
    deck = [{"s": s, "v": v} for s in SUITS for v in RANKS]
    random.shuffle(deck)
    return deck


def trick_value(card: dict[str, Any], led_suit: str, trump_suit: str | None) -> int:
    """محاسبه ارزش کارت در یک دست."""
    if trump_suit and card["s"] == trump_suit:
        return card["v"] + 100  # حکم همیشه بالاتر
    if card["s"] != led_suit:
        return 0  # غیر از خال زمینه و غیر حکم = بی‌ارزش
    return card["v"]


class HokmGame:
    """یک اتاق حکم ۴ نفره — ۲ انسان + ۲ ربات."""

    def __init__(self, room_id: str, seat_a: int, user_a: int, name_a: str,
                 seat_b: int | None = None, user_b: int | None = None,
                 name_b: str | None = None, difficulty: str = "medium"):
        self.room_id = room_id
        self.seats: dict[int, int | None] = {seat_a: user_a}
        self.names: dict[int, str] = {seat_a: name_a}
        if seat_b is not None:
            self.seats[seat_b] = user_b
            if name_b:
                self.names[seat_b] = name_b
        self.human_seats: list[int] = [seat_a] + ([seat_b] if seat_b is not None else [])
        self.difficulty = difficulty

        # وضعیت بازی
        self.phase = "waiting"  # waiting -> dealing -> bid -> play -> done
        self.hands: dict[int, list[dict[str, Any]]] = {0: [], 1: [], 2: [], 3: []}
        self.dealer = random.randint(0, 3)
        self.hakem: int | None = None
        self.trump_suit: str | None = None
        self.trump_declared = False

        # وضعیت بازی
        self.turn: int | None = None
        self.led_suit: str | None = None
        self.trick: list[dict[str, Any]] = []  # {seat, card}
        self.trick_leader: int | None = None
        self.tricks_taken = [0, 0]  # per team
        self.current_round = 0

        # نتیجه
        self.scores = [0, 0]  # امتیاز کل هر تیم
        self.winner_team: int | None = None
        self.is_bam = False
        self.is_koot = False
        self.hand_winner_team: int | None = None

        # متفرقه
        self.updated_at = time.time()
        self.created_at = time.time()
        self.log: list[str] = []

    # ========== وضعیت عمومی ==========

    def public_state(self, viewer_seat: int) -> dict[str, Any]:
        state: dict[str, Any] = {
            "room": self.room_id,
            "phase": self.phase,
            "your_seat": viewer_seat,
            "teammate": self._teammate(viewer_seat),
            "seat_names": {str(k): v for k, v in self.names.items()},
            "human_seats": self.human_seats,
            "dealer": self.dealer,
            "hakem": self.hakem,
            "trump_suit": self.trump_suit,
            "trump_name": SUIT_NAMES.get(self.trump_suit, "") if self.trump_suit else None,
            "trump_symbol": SUIT_SYMBOLS.get(self.trump_suit, "") if self.trump_suit else None,
            "turn": self.turn,
            "led_suit": self.led_suit,
            "trick": [{"seat": t["seat"], "card": t["card"]} for t in self.trick],
            "trick_leader": self.trick_leader,
            "tricks_taken": self.tricks_taken,
            "hand_count": {str(k): len(v) for k, v in self.hands.items()},
            "scores": self.scores,
            "current_round": self.current_round,
            "winner_team": self.winner_team,
            "hand_winner_team": self.hand_winner_team,
            "is_bam": self.is_bam,
            "is_koot": self.is_koot,
            "log": self.log[-40:],
            "updated_at": self.updated_at,
        }
        if viewer_seat in self.hands:
            state["hand"] = self.hands[viewer_seat]
        return state

    def _teammate(self, seat: int) -> int:
        return (seat + 2) % 4

    def _opponent_team(self, seat: int) -> int:
        return 1 - TEAM_OF[seat]

    # ========== شروع و پخش کارت ==========

    def start(self) -> None:
        if len(self.human_seats) < 2:
            return
        self.phase = "dealing"
        self._deal_first_round()
        self.updated_at = time.time()

    def _deal_first_round(self) -> None:
        """پخش ۵ کارت اول به هر بازیکن + تعیین حاکم."""
        deck = make_deck()
        self.hands = {0: [], 1: [], 2: [], 3: []}
        self.trump_declared = False
        self.trump_suit = None

        # پخش ۵ کارت اول
        idx = 0
        start_seat = (self.dealer + 1) % 4
        for _ in range(5):
            for i in range(4):
                p = (start_seat + i) % 4
                self.hands[p].append(deck[idx])
                idx += 1

        # تعیین حاکم: اولین کسی که آس داره
        for p in range(4):
            self.hands[p] = sort_hand(self.hands[p])
            if any(c["v"] == 14 for c in self.hands[p]):
                self.hakem = p
                break

        if self.hakem is None:
            # اگه هیچکس آس نداشت، قوی‌ترین دست
            self.hakem = max(range(4), key=lambda p: sum(c["v"] for c in self.hands[p]))

        self.names.setdefault(self.hakem, f"ربات {self.hakem}")
        self.add_log(f"👑 حاکم: {self.names[self.hakem]} (صندلی {self.hakem})")

        # ذخیره بقیه کارت‌ها برای بعد از اعلام حکم
        self._remaining_deck = deck[idx:]
        self._remaining_start_seat = start_seat

        if self.hakem in self.human_seats:
            self.phase = "bid"  # منتظر اعلام حکم توسط انسان
            self.add_log(f"🎯 {self.names[self.hakem]} باید حکم اعلام کنه (فقط ۵ کارت اول)")
        else:
            # ربات حاکمه — خودش حکم رو اعلام می‌کنه
            self._ai_declare_trump()

    def declare_trump(self, seat: int, suit: str) -> bool:
        """اعلام حکم توسط حاکم انسان."""
        if self.phase != "bid" or self.hakem != seat:
            return False
        if suit not in SUITS:
            return False
        self.trump_suit = suit
        self.trump_declared = True
        self.add_log(f"🎯 حکم: {SUIT_NAMES[suit]} {SUIT_SYMBOLS[suit]}")
        self._deal_remaining()
        return True

    def _ai_declare_trump(self) -> None:
        """ربات حاکم حکم رو اعلام می‌کنه."""
        hand = self.hands[self.hakem]
        best_suit = self._best_trump_suit(hand)
        self.trump_suit = best_suit
        self.trump_declared = True
        self.add_log(f"🎯 حکم: {SUIT_NAMES[best_suit]} {SUIT_SYMBOLS[best_suit]}")
        self._deal_remaining()

    def _best_trump_suit(self, hand: list[dict[str, Any]]) -> str:
        """بهترین خال برای حکم — بر اساس تعداد و قدرت."""
        per_suit: dict[str, list[dict[str, Any]]] = {}
        for c in hand:
            per_suit.setdefault(c["s"], []).append(c)
        best = {"suit": "s", "score": 0}
        for s in SUITS:
            cards = per_suit.get(s, [])
            count = len(cards)
            honors = sum(1 for c in cards if c["v"] >= 11)
            aces = sum(1 for c in cards if c["v"] == 14)
            score = count * 3 + honors * 2 + aces * 4
            if score > best["score"]:
                best = {"suit": s, "score": score}
        return best["suit"]

    def _deal_remaining(self) -> None:
        """پخش بقیه کارت‌ها (۴+۴ = ۸ کارت به هر نفر) بعد از اعلام حکم."""
        remaining = self._remaining_deck
        start_seat = self._remaining_start_seat
        idx = 0
        # ۲ دور، هر دور ۴ کارت به هر بازیکن
        for _ in range(2):
            for _ in range(4):
                for i in range(4):
                    p = (start_seat + i) % 4
                    if idx < len(remaining):
                        self.hands[p].append(remaining[idx])
                        idx += 1
        for p in range(4):
            self.hands[p] = sort_hand(self.hands[p])

        self.current_round = 1
        self.phase = "play"
        self.tricks_taken = [0, 0]
        self.start_trick(self.hakem)  # حاکم اول بازی می‌کنه
        self.add_log(f"🏁 شروع بازی! هر تیمی زودتر {WIN_TRICKS} دست بگیره برنده‌ست!")
        self.updated_at = time.time()

    # ========== مدیریت دست‌ها ==========

    def start_trick(self, leader: int) -> None:
        self.trick = []
        self.trick_leader = leader
        self.turn = leader
        self.led_suit = None
        self.add_log(f"— دست {self.current_round}: {self.names.get(leader, 'بازیکن')} شروع می‌کنه —")
        self.updated_at = time.time()

    def legal_moves(self, seat: int) -> list[dict[str, Any]]:
        """کارت‌های مجاز برای بازی."""
        hand = self.hands.get(seat, [])
        if not self.led_suit:
            return list(hand)  # اول بازی — هر کارتی
        suit_cards = [c for c in hand if c["s"] == self.led_suit]
        return suit_cards if suit_cards else list(hand)  # اگه خال نداره، هر کارتی

    def play(self, seat: int, card: dict[str, Any]) -> bool:
        """بازی کردن یک کارت."""
        if self.phase != "play" or self.turn != seat:
            return False
        idx = next((i for i, c in enumerate(self.hands[seat])
                     if card_key(c) == card_key(card)), None)
        if idx is None:
            return False
        # بررسی follow suit
        if self.led_suit and card["s"] != self.led_suit:
            has_suit = any(c["s"] == self.led_suit for c in self.hands[seat])
            if has_suit:
                return False  # باید خال زمینه رو بازی کنه

        card = self.hands[seat].pop(idx)
        if self.led_suit is None:
            self.led_suit = card["s"]
        self.trick.append({"seat": seat, "card": card})
        who = self.names.get(seat, "بازیکن")
        self.add_log(f"{who}: {card_display(card)}")
        self.updated_at = time.time()

        if len(self.trick) == 4:
            self._finish_trick()
        else:
            self.turn = (self.turn + 1) % 4
        return True

    def _trick_winner(self) -> int:
        """تعیین برنده دست."""
        best_idx, best_val = 0, -1
        for i, t in enumerate(self.trick):
            v = trick_value(t["card"], self.led_suit or t["card"]["s"], self.trump_suit)
            if v > best_val:
                best_val, best_idx = v, i
        return self.trick[best_idx]["seat"]

    def _finish_trick(self) -> None:
        winner = self._trick_winner()
        team = TEAM_OF[winner]
        self.tricks_taken[team] += 1
        self.add_log(
            f"🏆 {self.names.get(winner, 'بازیکن')} دست رو برد! "
            f"({self.tricks_taken[0]} - {self.tricks_taken[1]})"
        )
        self.trick = []
        self.led_suit = None
        self.current_round += 1

        total = sum(self.tricks_taken)

        # بررسی بام (هر ۱۳ دست)
        if total == 13:
            if self.tricks_taken[0] == 13 or self.tricks_taken[1] == 13:
                self.is_bam = True
            self._end_hand()
            return

        # بررسی برد (۷ دست)
        if self.tricks_taken[0] >= WIN_TRICKS or self.tricks_taken[1] >= WIN_TRICKS:
            self._end_hand()
            return

        self.start_trick(winner)

    def _end_hand(self) -> None:
        """پایان یک دست و محاسبه امتیاز."""
        hakem_team = TEAM_OF[self.hakem]
        if self.tricks_taken[0] >= WIN_TRICKS:
            self.hand_winner_team = 0
        else:
            self.hand_winner_team = 1

        loser_team = 1 - self.hand_winner_team
        self.is_koot = self.tricks_taken[loser_team] == 0

        # محاسبه امتیاز
        if self.is_koot:
            if self.hand_winner_team == hakem_team:
                points = 2  # کُت حاکم
                self.add_log(f"👑 کُت! تیم {self.hand_winner_team} (حاکم) ۷-۰ برد! (+۲ امتیاز)")
            else:
                points = 3  # کُت حریف
                self.add_log(f"👑 کُت! تیم {self.hand_winner_team} حاکم رو ۷-۰ برد! (+۳ امتیاز)")
        elif self.is_bam:
            points = 1
            self.add_log(f"🔥 بام! تیم {self.hand_winner_team} هر ۱۳ دست رو برد!")
        else:
            points = 1
            self.add_log(f"🏁 تیم {self.hand_winner_team} با {max(self.tricks_taken)} دست برد! (+۱ امتیاز)")

        self.scores[self.hand_winner_team] += points
        self.add_log(f"📊 امتیازات: تیم ۰ = {self.scores[0]} | تیم ۱ = {self.scores[1]}")

        # بررسی برد نهایی
        if self.scores[self.hand_winner_team] >= WIN_SCORE:
            self.winner_team = self.hand_winner_team
            self.phase = "done"
            self.add_log(f"🎉 تیم {self.winner_team} برنده بازی شد!")
        else:
            # دست بعدی
            self.phase = "dealing"
            self.updated_at = time.time()

    def next_hand(self) -> None:
        """شروع دست بعدی."""
        hakem_team = TEAM_OF[self.hakem]
        if self.hand_winner_team != hakem_team:
            # حاکم عوض شد
            self.dealer = self.hakem
            self.hakem = (self.hakem + 1) % 4
        else:
            # حاکم موند
            self.dealer = (self.hakem - 1) % 4
        self.hand_winner_team = None
        self.is_bam = False
        self.is_koot = False
        self.tricks_taken = [0, 0]
        self.current_round = 0
        self._deal_first_round()

    # ========== هوش مصنوعی ==========

    def ai_move(self, seat: int) -> dict[str, Any] | None:
        """حرکت هوشمند ربات."""
        if self.phase != "play" or self.turn != seat:
            return None
        legal = self.legal_moves(seat)
        if not legal:
            return None
        card = self._ai_choose(seat, legal)
        self.play(seat, card)
        return card

    def _ai_choose(self, seat: int, legal: list[dict[str, Any]]) -> dict[str, Any]:
        if self.difficulty == "easy":
            return random.choice(legal)
        if self.led_suit is None:
            return self._ai_lead(seat)
        suit_cards = [c for c in legal if c["s"] == self.led_suit]
        if suit_cards:
            return self._ai_follow(seat, suit_cards)
        return self._ai_void(seat)

    def _ai_lead(self, seat: int) -> dict[str, Any]:
        """حرکت اول ربات — بازی با قوی‌ترین خال."""
        hand = self.hands[seat]
        per_suit: dict[str, list[dict[str, Any]]] = {}
        for c in hand:
            per_suit.setdefault(c["s"], []).append(c)

        # اول سعی کن حکم بکشه اگه حاکم هستی
        if self.trump_suit and per_suit.get(self.trump_suit):
            trumps = per_suit[self.trump_suit]
            if len(trumps) >= 3:
                return max(trumps, key=lambda c: c["v"])

        # بازی با خال کم‌تعداد
        non_trump = {s: cs for s, cs in per_suit.items() if s != self.trump_suit}
        if non_trump:
            best_suit = min(non_trump, key=lambda s: len(non_trump[s]))
            return max(non_trump[best_suit], key=lambda c: c["v"])

        return max(hand, key=lambda c: c["v"])

    def _ai_follow(self, seat: int, suit_cards: list[dict[str, Any]]) -> dict[str, Any]:
        """وقتی خال زمینه رو داری."""
        current_best = -1
        partner_winning = False
        for t in self.trick:
            v = trick_value(t["card"], self.led_suit or "", self.trump_suit)
            if v > current_best:
                current_best = v
            if TEAM_OF[t["seat"]] == TEAM_OF[seat] and v == current_best:
                partner_winning = True

        winners = [c for c in suit_cards
                   if trick_value(c, self.led_suit or "", self.trump_suit) > current_best]

        if winners:
            # اگه هم‌تیمیت برنده‌ست، کارت ضعیف بازی کن
            if partner_winning:
                return min(suit_cards, key=lambda c: c["v"])
            return min(winners, key=lambda c: c["v"])

        # نمی‌تونی ببری — ضعیف‌ترین کارت
        return min(suit_cards, key=lambda c: c["v"])

    def _ai_void(self, seat: int) -> dict[str, Any]:
        """وقتی خال زمینه رو نداری."""
        hand = self.hands[seat]

        # بررسی اگه هم‌تیمیت برنده‌ست
        partner_winning = False
        current_best = -1
        for t in self.trick:
            v = trick_value(t["card"], self.led_suit or "", self.trump_suit)
            if v > current_best:
                current_best = v
                partner_winning = TEAM_OF[t["seat"]] == TEAM_OF[seat]

        # اگه می‌تونی حکم بزنی
        if self.trump_suit:
            trumps = [c for c in hand if c["s"] == self.trump_suit]
            if trumps and not partner_winning:
                # ببین کسی بالاتر حکم زده
                trump_on_table = [t["card"] for t in self.trick if t["card"]["s"] == self.trump_suit]
                if trump_on_table:
                    my_best = max(trumps, key=lambda c: c["v"])
                    table_best = max(trump_on_table, key=lambda c: c["v"])
                    if my_best["v"] > table_best["v"]:
                        return min(trumps, key=lambda c: c["v"])  # حکم بزن
                else:
                    return min(trumps, key=lambda c: c["v"])  # حکم بزن

        # کارت بی‌ارزش بازی کن
        non_trump = [c for c in hand if c["s"] != self.trump_suit]
        if non_trump:
            return min(non_trump, key=lambda c: c["v"])
        return min(hand, key=lambda c: c["v"])

    def add_log(self, msg: str) -> None:
        self.log.append(msg)
        if len(self.log) > 80:
            self.log = self.log[-80:]
