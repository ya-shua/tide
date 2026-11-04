"""想念是主动开口的第一动力：想得厉害就该说话，不该被算术卡住。"""
import unittest

from tide import inner_voice

BASE = {"grievance": 0, "tone": "neutral"}
CFG = {"urgency_threshold": 60, "longing_gate": 88}


def decide(needs, **kw):
    args = dict(quiet=False, unanswered=0, last_proactive_at=0, now=10_000)
    args.update(kw)
    return inner_voice.decide(needs, BASE, CFG, **args)


class TestLongingDrivesReachingOut(unittest.TestCase):
    def test_thinking_of_you_alone_is_enough(self):
        res = decide({"longing": 100, "boredom": 0, "energy": 0})
        self.assertTrue(res["should_send"], res["reason"])
        self.assertTrue(res["craving"])

    def test_just_above_the_hard_gate(self):
        self.assertTrue(decide({"longing": 88})["should_send"])

    def test_under_the_gate_still_needs_company(self):
        res = decide({"longing": 70})
        self.assertFalse(res["should_send"], res["reason"])

    def test_old_math_would_have_failed(self):
        # 0.5 * 100 = 50 < 60：这就是原来想满也不开口的原因
        old = inner_voice.urgency({"longing": 100, "boredom": 0, "energy": 0},
                                  BASE, {"longing": 0.5})
        self.assertLess(old, 60)
        new = inner_voice.urgency({"longing": 100, "boredom": 0, "energy": 0}, BASE)
        self.assertGreaterEqual(new, 70)


class TestLongingStillHasManners(unittest.TestCase):
    def test_quiet_hours_hold_it_back(self):
        res = decide({"longing": 100}, quiet=True)
        self.assertFalse(res["should_send"])
        self.assertIn("勿扰", res["reason"])

    def test_ignored_twice_means_stop(self):
        res = decide({"longing": 100}, unanswered=2)
        self.assertFalse(res["should_send"])

    def test_grievance_holds_it_back(self):
        bond = {"grievance": 95, "tone": "cool"}
        res = inner_voice.decide({"longing": 100}, bond, CFG, quiet=False,
                                 unanswered=0, last_proactive_at=0, now=10_000)
        self.assertFalse(res["should_send"])

    def test_cooldown(self):
        res = decide({"longing": 100}, last_proactive_at=9_900, now=10_000)
        self.assertFalse(res["should_send"])
        self.assertIn("冷却", res["reason"])


class TestBoredomIsOnlySecondary(unittest.TestCase):
    def test_boredom_alone_is_not_enough(self):
        res = decide({"boredom": 95, "energy": 0})
        self.assertFalse(res["should_send"])

    def test_boredom_still_contributes(self):
        low = inner_voice.urgency({"longing": 0, "boredom": 0}, BASE)
        high = inner_voice.urgency({"longing": 0, "boredom": 90}, BASE)
        self.assertGreater(high, low)


if __name__ == "__main__":
    unittest.main()